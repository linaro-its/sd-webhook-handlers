""" Handler for Hackbox2 access requests. """

import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd

CAPABILITIES = [
    "CREATE",
    "COMMENT"
]

SAVE_TICKET_DATA = False


def comment(ticket_data):
    """ Comment handler """
    last_comment, keyword = shared_sd.central_comment_handler([], ["help", "retry"])

    if keyword == "help":
        shared_sd.post_comment("All bot commands must be internal comments and the first "
                               "word/phrase in the comment.\r\n\r\n"
                               "Valid commands are:\r\n"
                               "* retry to ask the bot to process the request again after "
                               "problems with the request have been resolved.",
                               False)
    elif keyword == "retry":
        create(ticket_data)
    elif last_comment is not None and last_comment['public']:
        shared_sd.deassign_ticket_if_appropriate(comment)

def create(ticket_data):
    """ Create handler. """
    # There aren't any fields in the form for us to process. This
    # is a simple case of checking that the requestor is a member of
    # staff and then adding them to the group that controls SSH access
    # to the system.
    email_address = shared_sd.reporter_email_address(ticket_data)
    account_dn = shared_ldap.find_from_email(email_address)
    valid_account = shared_ldap.is_dn_in_group("employees", account_dn) or \
        shared_ldap.is_dn_in_group("assignees", account_dn)
    if not valid_account:
        shared_sd.post_comment(
            "You must be a Linaro employee or assignee to use the "
            "hackbox2 service.",
            True)
        shared_sd.resolve_ticket(resolution_state="Won't Do")
        return
    if shared_ldap.is_dn_in_group("hackbox-users", account_dn):
        shared_sd.post_comment(
            "You appear to already have access.",
            True)
        shared_sd.resolve_ticket()
        return
    if shared_ldap.add_to_group("hackbox-users", account_dn):
        shared_sd.post_comment(
            "Access has been granted. Please ensure you read "
            "https://collaborate.linaro.org/display/IKB/Hackbox2 "
            "and associated documentation so that you fully understand "
            "what this service is, how to use it and what the limitations "
            "are.",
            True)
        shared_sd.resolve_ticket()
    else:
        shared_sd.post_comment(
            "A problem occurred while adding you to the permission list. "
            "It will be necessary to get IT Services to investigate.",
            True)
        # Deassign the ticket
        shared_sd.assign_issue_to(None)
        shared_sd.transition_request_to("Waiting for Support")
