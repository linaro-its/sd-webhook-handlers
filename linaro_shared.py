"""
Some functions shared across the handlers that are too Linaro-specific
to be included in sd-webhook-framework.
"""

import base64
import hashlib
import os
import pwd
import random
import stat
import subprocess
import traceback

import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd
import shared.shared_vault as shared_vault


MAILTO = "mailto:"


def pem_path():
    """ Work out where the PEM file is located. """
    # Start by assuming that the PEM is in the rt_handlers folder
    script_directory = os.path.dirname(os.path.realpath(__file__))
    file_location = os.path.join(script_directory, "it-support-bot.pem")
    # If it isn't there, assume it is going to up a directory. That
    # will be owned by www-data (running the WSGI process) so will
    # be writeable if we need to retrieve it from Vault.
    if not os.path.exists(file_location):
        script_directory = os.path.dirname(script_directory)
        file_location = os.path.join(script_directory, "it-support-bot.pem")
    return file_location


def trigger_google_sync(level=""):
    """Connect to Linaro Login over SSH to trigger GCDS."""
    if not check_pem():
        return
    try:
        process = subprocess.Popen([
            'ssh',
            '-T',
            '-i%s' % pem_path(),
            'it-support-bot@login-us-east-1.linaro.org',
            level], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdoutdata, stderrdata = process.communicate()
        # process returns bytes so we need to convert to strings
        stdoutdata = stdoutdata.decode("utf-8")
        stderrdata = stderrdata.decode("utf-8")
        if stdoutdata == "" and stderrdata == "":
            shared_sd.post_comment(
                "Synchronisation to Google triggered. It may take up to 15 "
                "minutes before the changes are visible on Google.", True)
        else:
            if stdoutdata != "":
                shared_sd.post_comment(
                    "GCDS stdout = '%s'" %
                    stdoutdata, False)
            if stderrdata != "":
                shared_sd.post_comment(
                    "GCDS stderr = '%s'" %
                    stderrdata, False)
    # pylint: disable=broad-except
    except Exception as _:
        shared_sd.post_comment(
            "Got error while triggering GCDS: %s" % traceback.format_exc(),
            False)


def check_pem():
    """
    Make sure that the pem file is owned correctly and has the correct file
    permissions.
    """
    pem_location = pem_path()
    # If the PEM file doesn't exist, fetch it from the Vault and save it
    if not os.path.exists(pem_location):
        pem = shared_vault.get_secret("secret/misc/it-support-bot.pem")
        with open(pem_location, "w") as pem_file:
            pem_file.write(pem)
        os.chmod(pem_location, stat.S_IREAD | stat.S_IWRITE)
    result = os.stat(pem_location)
    # These shouldn't fail if we've just created the file but
    # may if the file was put in place through other means.
    if stat.S_IMODE(result.st_mode) != 384:  # 0600 octal
        shared_sd.post_comment(
            "BOT PEM file has incorrect permissions.", False)
        return False
    if pwd.getpwuid(result.st_uid).pw_name != "www-data":
        shared_sd.post_comment(
            "BOT PEM file has incorrect owner.", False)
        return False
    return True


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
        dept_team = "%s|%s" % (dept_team, dept_team)
    # LDAP doesn't allow brackets in search filters so we have to replace them.
    dept_team = dept_team.replace("(", "\\28")
    dept_team = dept_team.replace(")", "\\29")
    # Find someone with the specified dept_team combo.
    result = shared_ldap.find_matching_objects(
        "(departmentNumber=%s)" % dept_team,
        ['manager', 'title', 'mail'],
        base="ou=staff,ou=accounts,dc=linaro,dc=org")
    # That gets us a list but we only work on the first entry ...
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
