"""
Some functions shared across the handlers that are too Linaro-specific
to be included in sd-webhook-framework.
"""

import base64
import hashlib
import io
import random
import re
import select

import paramiko
import shared.custom_fields as custom_fields
import shared.globals
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd
import shared.shared_vault as shared_vault

MAILTO = "mailto:"

HOST_KEYS = {
    "login-us-east-1.linaro.org": (
        "AAAAB3NzaC1yc2EAAAADAQABAAABAQDb1gxcqZXsmAi6Y7D16VJ/99TRQX03sd1mwMls0k5NBbAmrseGTz221"
        "qivLZOkfc+fB8SlIIq48AeMumTDDFUcz1TICikJ0c4Vj4Kqdj/shiq/Bc7L9zqnVhb+xw/xculjuHc29Ffdw7"
        "mlsLN251mABg5MM2lJ99cg7r+bvPbQYvTTz8VxAYrILS4zIlTvKQ3hGCE/qni4PW3D4crvyDnQzF2iLvqocuY"
        "TkyRA+atYxYZHVEdvuwkGoCtpX4YXGov5VsqoCipEB7soYOAXtHw4gbMOj5JjTaEgjse46eW4E842mlVTxck0"
        "t6nqooQWigV8QVlMAoTu7PrtdjYnF9L1")
}

def ssh(host, user, key, timeout, command):
    """ Connect to the defined SSH host. """
    # Start by converting the (private) key into a RSAKey object. Use
    # StringIO to fake a file ...
    keyfile = io.StringIO(key)
    ssh_key = paramiko.RSAKey.from_private_key(keyfile)
    host_key = paramiko.RSAKey(data=base64.b64decode(HOST_KEYS[host]))
    client = paramiko.SSHClient()
    client.get_host_keys().add(host, "ssh-rsa", host_key)
    print("Connecting to %s to send command '%s'" % (host, command))
    client.connect(host, username=user, pkey=ssh_key, allow_agent=False, look_for_keys=False)
    stdout, stderr, result_code = exec_command(client, command, timeout)
    client.close()
    return (stdout, stderr, result_code)

def exec_command(ssh_client, command, timeout):
    """ Run a command over SSH and return the response """
    # https://stackoverflow.com/a/32758464/1233830
    stdin, stdout, stderr = ssh_client.exec_command(command)
    # get the shared channel for stdout/stderr/stdin
    channel = stdout.channel
    # we do not need stdin.
    stdin.close()
    # indicate that we're not going to write to that channel anymore
    channel.shutdown_write()
    # read stdout/stderr in order to prevent read block hangs
    stdout_chunks = []
    stdout_chunks.append(stdout.channel.recv(len(channel.in_buffer)))
    stderr_chunks = []
    stderr_chunks.append(stderr.channel.recv(len(channel.in_buffer)))
    # chunked read to prevent stalls
    while not channel.closed or channel.recv_ready() or channel.recv_stderr_ready():
        # stop if channel was closed prematurely
        got_chunk = False
        readq, _, _ = select.select([stdout.channel], [], [], timeout)
        for chan in readq:
            if chan.recv_ready():
                stdout_chunks.append(stdout.channel.recv(len(chan.in_buffer)))
                got_chunk = True
            if chan.recv_stderr_ready():
                # make sure to read stderr to prevent stall
                stderr_chunks.append(stderr.channel.recv_stderr(len(chan.in_stderr_buffer)))
                got_chunk = True
        #
        # 1) make sure that there are at least 2 cycles with no data in the input buffers in
        #    order to not exit too early (i.e. cat on a >200k file).
        # 2) if no data arrived in the last loop, check if we already received the exit code
        # 3) check if input buffers are empty
        # 4) exit the loop
        #
        if not got_chunk \
            and stdout.channel.exit_status_ready() \
            and not stderr.channel.recv_stderr_ready() \
            and not stdout.channel.recv_ready():
            # indicate that we're not going to read from this channel anymore
            stdout.channel.shutdown_read()
            # close the channel
            stdout.channel.close()
            break    # exit as remote side is finished and our bufferes are empty

    # close all the pseudofiles
    stdout.close()
    stderr.close()

    print("SSH status code:", stdout.channel.recv_exit_status())
    print("stdout:", b''.join(stdout_chunks).decode('utf-8'))
    print("stderr:", b''.join(stderr_chunks).decode('utf-8'))

    return (
        b''.join(stdout_chunks).decode('utf-8'),
        b''.join(stderr_chunks).decode('utf-8'),
        stdout.channel.recv_exit_status()
    )


def trigger_google_sync(level=""):
    """Connect to Linaro Login over SSH to trigger GCDS."""
    pem = shared_vault.get_secret("secret/misc/it-support-bot.pem")
    stdout_data, stderr_data, status_code = ssh(
        "login-us-east-1.linaro.org", "it-support-bot", pem, 100, level)
    if status_code == 0:
        shared_sd.post_comment(
            "Synchronisation to Google triggered. It may take up to 15 "
            "minutes before the changes are visible on Google.", True)
    else:
        shared_sd.post_comment(
            "Got non-zero status code from trigggering GCDS.", False)
        if stdout_data != "":
            shared_sd.post_comment("stdout:\r\n%s" % stdout_data, False)
        if stderr_data != "":
            shared_sd.post_comment("stderr:\r\n%s" % stderr_data, False)


def cleanup_if_markdown(email_address):
    """
    If the email address has been copied/pasted from elsewhere, it can sometimes
    get turned into a markdown version, e.g.:

    [<email>|mailto:<email>]

    and it is tricky for users to avoid that so we clean it up here.
    """
    if (email_address is None or
            email_address == "" or
            email_address[0] != '[' or
            email_address[-1] != ']' or
            '|' not in email_address):
        return email_address

    parts = email_address.split('|')
    if len(parts) != 2:
        return email_address
    # Make sure the second part is a mailto:
    part2 = parts[1]
    if (len(part2) <= len(MAILTO) or
            part2[:len(MAILTO)] != MAILTO):
        return email_address

    # Remove the trailing ] and return the email address
    return part2[len(MAILTO):-1]


def get_exec_from_dn(ldap_entry_dn):
    """
    Walk up the reporting structure until we get to someone who is in
    the Exec group. Return that someone.

    This function can fail to return a result if someone in the tree is
    in the process of leaving, i.e. they are recorded as a manager but
    are no longer an active account.
    """

    # Get the membership of the Exec group. Use the mailing list so that
    # we get the full DNs, thus making it easier to check.
    _, memb_result = shared_ldap.find_group("exec", ["uniqueMember"])
    members = memb_result[0].uniqueMember.values

    # Walk up the tree ...
    searching = True
    while searching:
        result = shared_ldap.get_object(ldap_entry_dn, ["manager"])
        if result is not None and result.manager.value is not None:
            ldap_entry_dn = result.manager.value
            if ldap_entry_dn in members:
                mgr_email = shared_ldap.get_object(result.manager.value, ["mail"])
                return mgr_email.mail.values[0]
            # otherwise loop to that person
        else:
            # The intermediate manager is leaving.
            searching = False
    return None


def get_director(dept_team):
    """ For a given dept/team, find the director. """
    # If there isn't a | in the team name, duplicate the team name with a | in
    # order to match against LDAP.
    if "|" not in dept_team:
        dept_team = f"{dept_team}|{dept_team}"
    # LDAP doesn't allow brackets in search filters so we have to replace them.
    dept_team = dept_team.replace("(", "\\28")
    dept_team = dept_team.replace(")", "\\29")
    # Find someone with the specified dept_team combo.
    result = shared_ldap.find_matching_objects(
        f"(departmentNumber={dept_team})",
        ['manager', 'title', 'mail'],
        base="ou=staff,ou=accounts,dc=linaro,dc=org")
    # That gets us a list but we only work on the first entry ...
    if result is None:
        print(f"get_director: failed to find anyone in department '{dept_team}'")
        return None
    result = result[0]
    # Now walk up the manager attribute until we get to a Director.
    while True:
        if result == []:
            return None

        # Just work off the first result returned and we'll iterate ...
        title = result.title.value
        if title is not None:
            title = title.lower()

        # Nasty hack to cope with Landing Teams ...
        if "director" in title or title == "vp developer services":
            return result.mail.value

        manager = result.manager.value
        if manager is None:
            # We've run out of staff structure
            return None

        # Walk up the tree
        result = shared_ldap.get_object(manager, ['manager', 'title', 'mail'])
        # ... and loop


def make_password():
    """
    Make a new password. This is a pythonised version of the routine used
    by LAM Pro.
    """
    char_list = (
        '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-_'
    )
    password = ''
    for _ in range(0, 12):
        rand = random.randint(0, len(char_list)-1)
        password += char_list[rand]

    md5_hash = hashlib.md5()
    md5_hash.update(password.encode('utf-8'))
    return password, "{MD5}%s" % base64.encodebytes(md5_hash.digest()).decode('utf-8').strip()


def response_split(response):
    """
    Given a single or multi-line response, optionally with comma-separation,
    split into single responses.
    """

    # We use a Unicode regex string to allow us to include \xa0 which is &nbsp,
    # which can happen when the issue is edited by an agent.
    # Note that it is possible for responses to be empty, e.g. [u'']
    return re.split(u"[\r\n, \xa0]+", response)


def ok_to_process_public_comment(comment):
    """ Performs common checks to make sure the comment needs to be processed """
    if (shared_sd.get_current_status() == "Resolved" or
            not comment['public'] or
            shared_sd.user_is_bot(comment['author'])):
        return False

    # Ignore comments made by IT Services since they could be replying to
    # a comment from a user.
    commentator = shared_sd.get_user_field(comment["author"], "emailAddress")
    return not shared_ldap.is_user_in_group("its", commentator)


def get_dn_from_account_id(ticket_data, custom_field):
    """ Get a person's LDAP DN from their Atlassian account ID """
    person_anonymised = shared_sd.get_field(ticket_data, custom_field)
    # Find the person in LDAP
    ldap_dn = None
    if person_anonymised is not None:
        account_id = person_anonymised["accountId"]
        person = shared_sd.find_account_from_id(account_id)
        if person is not None:
            person_email = person["emailAddress"]
            ldap_dn = shared_ldap.find_single_object_from_email(person_email)
    return ldap_dn


def check_approval_assignee_member_engineer(ticket_data):
    """ Ensure that the ticket has the appropriate approval set up """
    # Get the details for the specified engineer
    cf_engineer = custom_fields.get("Assignee/Member Engineer")
    ldap_dn = get_dn_from_account_id(ticket_data, cf_engineer)
    if ldap_dn is None:
        shared_sd.post_comment(
            "Cannot find this person in Linaro Login", True)
        return

    ldap_search = shared_ldap.get_object(
        ldap_dn,
        ['description', 'departmentNumber', 'o', 'employeeType', 'manager'])
    if ldap_search is None:
        shared_sd.post_comment(
            "Cannot retrieve person's details from Linaro Login", True)
        return
    employee_type = ldap_search.employeeType.value
    if employee_type not in [
        "Assignee",
        "Member Engineer",
        "Affiliate Engineer"
        ]:
        shared_sd.post_comment(
            "This person is not an assignee, Member engineer or Affiliate engineer",
            True
        )
        return

    director = get_director(ldap_search.departmentNumber.value)
    if director is None:
        shared_sd.post_comment(
            "[~philip.colmer@linaro.org] Couldn't find the director for"
            f" {ldap_search.departmentNumber.value}'",
            False)
        return

    # Add the name to the summary if we haven't already
    summary = shared_sd.get_field(ticket_data, "summary")
    if summary is not None:
        name = ldap_search.description.value
        if not summary.endswith(name):
            shared_sd.set_summary(f"{summary}: {name}")

    # Get the manager for this person
    mgr_email = shared_ldap.get_manager_from_dn(ldap_search.manager.value)
    if mgr_email is None:
        # Fall back to getting Diane to approve the ticket
        mgr_email = "diane.cheshire@linaro.org"
    # If the ticket wasn't created by the manager, get the manager to approve
    # it.
    if mgr_email != shared.globals.REPORTER:
        shared_sd.post_comment(
            f"As you are not the manager for {ldap_search.description.value}, {mgr_email} "
            "will be asked to approve or decline your request.",
            True
        )
        cf_approvers = custom_fields.get("Approvers")
        shared_sd.assign_approvers([mgr_email], cf_approvers)
        shared_sd.transition_request_to("Needs approval")
    else:
        shared_sd.transition_request_to("In Progress")
