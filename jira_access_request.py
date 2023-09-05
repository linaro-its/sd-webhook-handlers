"""This code handles the jira access request type."""

import shared.globals
from shared import custom_fields, shared_ldap, shared_sd

import linaro_shared

CAPABILITIES = [
    "CREATE",
    "COMMENT",
    "TRANSITION"
]

def comment(ticket_data):
    """Triggered when a comment is posted."""
    this_comment, keyword = shared_sd.central_comment_handler([], ["help", "retry", "ignorequota"])

    if keyword == "ignorequota":
        shared_sd.transition_request_to("Open")
        create(ticket_data, False)
    elif keyword == "retry":
        # If the ticket has already been approved, the retry comment triggers granting of access.
        if shared_sd.get_current_status() == "In Progress":
            grant_jira_access()
            return
        # Otherwise, try starting afresh ... note that the workflow might not allow this!
        shared_sd.transition_request_to("Open")
        create(ticket_data)
    elif this_comment is None or keyword is None or keyword == "help":
        shared_sd.post_comment(
            ("All bot commands must be internal comments and the "
             "first word/phrase in the comment.\r\n\r\n"
             "Valid commands are:\r\n"
             "* ignorequota to allow the user to be granted access "
             "regardless of quota limits)\r\n"
             "* retry to ask the bot to process the request again after issues "
             "have been resolved."),
            False)
    elif this_comment['public'] and \
            shared_sd.user_is_bot(this_comment['author']) and \
            shared_sd.get_current_status() != "Resolved":
        shared_sd.deassign_ticket_if_appropriate(this_comment)

def create(ticket_data, check_quota=True):
    """Triggered when a new JIRA access request issue is created."""
    cf_email_address = custom_fields.get("Email Address")
    email_address = shared_sd.get_field(ticket_data, cf_email_address)
    if email_address is not None:
        email_address = email_address.strip().lower()

    shared_sd.assign_issue_to(shared.globals.CONFIGURATION["bot_name"])
    shared_sd.set_summary(f"JIRA access request for {email_address}")

    # Check that the email address exists in LDAP already.
    result = shared_ldap.find_matching_objects(
        f"(mail={email_address})",
        attributes=['memberOf', 'uid', 'description', 'userPassword', 'employeeType'])
    if result is None or len(result) == 0:
        shared_sd.post_comment(
            ("Sorry but access to JIRA cannot be granted for this email address "
             "because it cannot be found on Linaro Login. Do you need to create "
             "the account first via "
             "https://servicedesk.linaro.org/servicedesk/customer/portal/3/create/120 ?"),
            True)
        shared_sd.resolve_ticket("Won't Do")
        return
    if len(result) > 1:
        shared_sd.post_comment(
            "Sorry but access to JIRA cannot be granted because this email address "
            "maps onto multiple accounts for some reason.", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    # So we should only have one result, so let's extract that
    person = result[0]

    # Do they already have access?
    for grp in person.memberOf:
        grp_name = grp.split(',', 1)[0].split('=')[1]
        if grp_name.startswith("jira-comment-") or grp_name.startswith("jira-approval-"):
            shared_sd.post_comment(
                "It looks like this person already has access to JIRA. "
                "If you need access to a specific JIRA project, please "
                "contact the appropriate project admninistrator or use "
                "https://servicedesk.linaro.org/servicedesk/customer/portal/3/create/61", True)
            shared_sd.resolve_ticket("Won't Do")
            return

    # Check that this is an account and not a contact. They won't be able to log in
    # if there isn't a password.
    if person.userPassword.value is None:
        shared_sd.post_comment(
            "This is a contact and not an account, i.e. there is no password present."
            " As a result, they would not be able to log onto JIRA."
            " To have a password added, please ask them to go to https://login.linaro.org"
            " and click on 'Forgot password?'. They will then get an email to take them"
            " through the password reset process.", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    # Check the OU that this account exists in.
    person_dn = person.entry_dn
    person_ou = person_dn.split(',', 1)[1]
    if person_ou == "ou=staff,ou=accounts,dc=linaro,dc=org":
        # Contractors don't get access automatically so check for them first.
        if person.employeeType.value is not None and person.employeeType.value == "Contractor":
            # Add them to jira-linaro-users
            shared_ldap.add_member_to_group("jira-linaro-users", person_dn)
            linaro_shared.trigger_google_sync()
            shared_sd.post_comment(
                f"Access to JIRA has been granted for {email_address}. "
                "Please note it may take up to an hour for JIRA to see this change.", True)
            shared_sd.resolve_ticket()
            return
        # otherwise ...
        shared_sd.post_comment(
            "Linaro staff, assignees and Member Engineers already have access to JIRA. "
            "If you need access to a specific JIRA project, please contact the appropriate "
            " project admninistrator or use "
            "https://servicedesk.linaro.org/servicedesk/customer/portal/3/create/61", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    # See if there is an approval group for this OU/company
    company = person_ou.split(',', 1)[0].split('=')[1]
    grp_result = shared_ldap.find_matching_objects(
        f"(cn=jira-approval-{company})",
        ["cn", "uniqueMember"],
        base="ou=mailing,ou=groups,dc=linaro,dc=org")
    if grp_result is None or len(grp_result) != 1:
        shared_sd.post_comment(
            "Sorry but this email address doesn't appear to belong to a Member company. "
            "IT Services will need to take over this request.", True)
        shared_sd.post_comment("To grant access, move state to Open then In Progress.", False)
        shared_sd.transition_request_to("Send to support", check_transition_name=True)
        return

    # Do we need to check the quota? The easiest way to determine the membership level
    # is to retrieve the corresponding comment group and figure it out from that.
    member_result = shared_ldap.find_matching_objects(
        f"(cn=jira-comment-*-{company})",
        ["cn", "uniqueMember"],
        base="ou=mailing,ou=groups,dc=linaro,dc=org")
    if member_result is None or len(member_result) != 1:
        shared_sd.post_comment(
            "Sorry but it has not been possible to determine the membership level for this Member. "
            "IT Services will need to take over this request.", True)
        shared_sd.post_comment("To grant access, move state to Open then In Progress.", False)
        shared_sd.transition_request_to("Send to support", check_transition_name=True)
        return

    if check_quota:
        group_level = member_result[0].cn.value.split('-')[2]
        count = len(member_result[0].uniqueMember.values)
        if (group_level == 'group' and count > 10) or (group_level == 'club' and count > 25):
            shared_sd.post_comment(
                f"Quota exceeded for this membership level: {group_level}; "
                f"current number of users = {count}\n"
                "Post a PRIVATE comment of 'ignorequota' when approved by Joe",
                False)
            shared_sd.post_comment(
                "Sorry but this request requires further action to be carried out by IT Services.",
                True)
            shared_sd.transition_request_to("Send to support", check_transition_name=True)
            return

    # Is the reporter an SC member for the company or one of the privileged few?
    if shared_ldap.is_user_in_group(f"jira-approval-{company}", shared.globals.REPORTER) or \
            shared_ldap.is_user_in_group("jira-approval-privileged", shared.globals.REPORTER) or \
            company == "arm":
        shared_sd.transition_request_to("In progress")
        return

    # Check that we've got SC members for this company that can approve the request!
    # There must always be at least one uniqueMember - the empty one - so if we only
    # have one, it is that one.
    if len(grp_result[0].uniqueMember.values) == 1 and grp_result[0].uniqueMember[0] == '':
        shared_sd.post_comment(
            "Sorry but there don't appear to be any Steering Committee members for the company "
            f"'{company}' so cannot get approval for this request. IT Services will need to "
            "take over this request.", True)
        shared_sd.post_comment("To grant access, move state to Open then In Progress.", False)
        shared_sd.transition_request_to("Send to support", check_transition_name=True)
        return

    shared_sd.post_comment(
        "The Steering Committee reps for this company have been asked to approve or "
        "decline this request. The bot will act automatically once their reply is received.", True)
    cf_approvers = custom_fields.get("Approvers")
    shared_sd.assign_approvers(grp_result[0].uniqueMember.values, custom_field=cf_approvers)
    shared_sd.transition_request_to("Needs approval")

def transition(status_to, ticket_data):
    """ Handle change of ticket status """
    _ = ticket_data # keep linter happy
    # If the status is "In Progress", trigger the membership change.
    # This status can only be reached from Open or Needs Approval.
    if status_to == "In Progress":
        grant_jira_access()

def grant_jira_access():
    """Grant access to JIRA for the specified person."""
    cf_email_address = custom_fields.get("Email Address")
    email_address = shared_sd.get_field(shared.globals.TICKET_DATA, cf_email_address)
    if email_address is not None:
        email_address = email_address.strip().lower()

    user_dn = shared_ldap.find_single_object_from_email(email_address)
    if user_dn is None:
        shared_sd.post_comment(
            f"It has not been possible to find {email_address} in Linaro Login.",
            True
        )
        shared_sd.resolve_ticket("Won't Do")
        return

    user_ou = user_dn.split(',', 1)[1]
    company = user_ou.split(',', 1)[0].split('=')[1]
    if company in ["the-rest", "external-community"]:
        # For non-members, put them in the jira-users group
        company_dn = "jira-users"
    else:
        member_result = shared_ldap.find_matching_objects(
            f"(cn=jira-comment-*-{company})",
            ["cn"],
            base="ou=mailing,ou=groups,dc=linaro,dc=org")
        # If there isn't a jira-comment group for this company, add them to jira-users
        if member_result is None or member_result == []:
            company_dn = "jira-users"
        else:
            company_dn = member_result[0].cn.value

    # It shouldn't be possible for multiple approvals to happen but be cautious anyway.
    if shared_ldap.is_user_in_group(company_dn, email_address):
        shared_sd.post_comment(
            f"Thank you for the additional approval; {email_address} has already been "
            "granted access to JIRA.", True)
    else:
        shared_ldap.add_member_to_group(company_dn, user_dn)
        linaro_shared.trigger_google_sync()
        shared_sd.post_comment(
            f"Access to JIRA has been granted for {email_address}. Please note it may take "
            "up to an hour for JIRA to see this change.", True)

    # Always resolve the ticket because comment commands will have re-opened it.
    shared_sd.resolve_ticket()
