"""This code handles the delete LDAP group request type."""

import shared.globals
from shared import custom_fields, shared_ldap, shared_sd

import linaro_shared


def comment(ticket_data):
    """Triggered when a comment is posted."""
    last_comment, keyword = shared_sd.central_comment_handler([], ["help", "retry"])

    if last_comment is None or keyword == "help":
        shared_sd.post_comment(
            ("All bot commands must be internal comments and the first "
             "word/phrase in the comment.\r\n\r\n"
             "Valid commands are:\r\n"
             "* retry to ask the bot to process the request again after "
             "issues have been resolved."), False)
    elif keyword == "retry":
        shared_sd.transition_request_to("Open")
        create(ticket_data)
    elif linaro_shared.ok_to_process_public_comment(last_comment):
        shared_sd.deassign_ticket_if_appropriate(last_comment)


IT_BOT = (
    'uid=it.support.bot,ou=mail-contacts-unsynced,'
    'ou=accounts,dc=linaro,dc=org'
)


def create(ticket_data):
    """Triggered when the issue is created."""
    # Check that the email address provided (a) exists in LDAP and (b) is a
    # group.
    cf_group_email_address = custom_fields.get("Group Email Address")
    group_email_address = shared_sd.get_field(ticket_data, cf_group_email_address)
    if group_email_address is not None and "value" in group_email_address:
        group_email_address = group_email_address["value"]
    if group_email_address is not None:
        group_email_address = group_email_address.strip().lower().encode('utf-8')
    group_email_address, result = shared_ldap.find_group(
        group_email_address, ['owner', 'uniqueMember'])

    shared_sd.set_summary(f"Delete LDAP group for {group_email_address}")

    if result is None or len(result) == 0:
        shared_sd.post_comment(
            "Sorry but the group's email address can't be found in "
            "Linaro Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return
    if len(result) != 1:
        shared_sd.post_comment(
            "Sorry but, somehow, the group's email address appears more than "
            "once in Linaro Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    if len(result[0].uniqueMember.values) > 1:
        shared_sd.post_comment(
            "Sorry but only empty groups can be deleted.", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    # Need to check owners by unpacking the list as groups can be owners but
    # groups can be empty.
    owners = shared_ldap.flatten_list(result[0].owner.values)
    if owners is None or owners == []:
        got_owners = False
    else:
        got_owners = True

    cf_approvers = custom_fields.get("Approvers")
    if not got_owners:
        if shared_ldap.is_user_in_group("its", shared.globals.REPORTER):
            shared_sd.transition_request_to("In progress")
        else:
            shared_sd.post_comment(
                "This group has no owners. Asking IT Services to review your "
                "request.", True)
            it_members = shared_ldap.get_group_membership(
                "cn=its,ou=mailing,ou=groups,dc=linaro,dc=org")
            shared_sd.assign_approvers(it_members, cf_approvers)
            shared_sd.transition_request_to("Needs approval")
    elif shared_ldap.reporter_is_group_owner(result[0].owner.values):
        shared_sd.transition_request_to("In progress")
    elif IT_BOT in result[0].owner.values and \
            shared_ldap.is_user_in_group("its", shared.globals.REPORTER):
        shared_sd.transition_request_to("In progress")
    else:
        if not shared_ldap.is_user_in_group("employees", shared.globals.REPORTER):
            shared_sd.post_comment(
                "Sorry but only Linaro employees can use this Service "
                "Request.", True)
            shared_sd.resolve_ticket("Won't Do")
            return

        shared_sd.post_comment(
            "As you are not an owner of this group, the owners will be asked "
            "to approve or decline your request.", True)
        shared_sd.assign_approvers(result[0].owner.values, cf_approvers)
        shared_sd.transition_request_to("Needs approval")


def transition(status_to, ticket_data):
    """ Handle ticket transition """
    # If the status is "In Progress", trigger the membership change. This
    # status can only be reached from Open or Needs Approval.
    if status_to == "In Progress":
        cf_group_email_address = custom_fields.get("Group Email Address")
        group_email_address = shared_sd.get_field(ticket_data, cf_group_email_address)
        if group_email_address is not None and "value" in group_email_address:
            group_email_address = group_email_address["value"]
        if group_email_address is not None:
            group_email_address = group_email_address.strip().lower().encode('utf-8')
        group_dn = shared_ldap.find_single_object_from_email(group_email_address)
        delete_group(group_dn)


def delete_group(entry_dn):
    """ Delete both mail and security groups referenced by the mail group's dn """
    response = ""

    # Is the group a member of any other groups?
    other_groups = shared_ldap.find_matching_objects(
        f"(uniqueMember={entry_dn})",
        ["cn"],
        base="ou=mailing,ou=groups,dc=linaro,dc=org"
    )
    if other_groups is not None and len(other_groups) != 0:
        for group in other_groups:
            cn_value = group.cn.value
            response += f"Removing group as a member of {cn_value}\r\n"
            shared_ldap.remove_from_mailing_group(cn_value, entry_dn)

    # Is the group an owner of any other groups?
    owned_groups = shared_ldap.find_matching_objects(
        f"(owner={entry_dn})",
        ["cn"],
        base="ou=security,ou=groups,dc=linaro,dc=org"
    )
    if owned_groups is not None and len(owned_groups) != 0:
        for group in owned_groups:
            cn_value = group.cn.value
            response += f"Removing group as an owner of {cn_value}\r\n"
            shared_ldap.remove_owner_from_security_group(cn_value, entry_dn)

    count = delete_single_group(entry_dn)
    # Replace mailing with security.
    entry_dn = entry_dn.replace("ou=mailing", "ou=security")
    count += delete_single_group(entry_dn)

    if count != 0:
        linaro_shared.trigger_google_sync()

    if count == 2:
        response += "The group has been deleted."
    elif count == 1:
        response += (
            "One of the groups could not be deleted; ITS can investigate "
            "further if relevant."
        )
    else:
        response += (
            "Neither the mailing nor security groups could be deleted; ITS "
            "can investigate further if relevant."
        )

    shared_sd.post_comment(response, True)
    shared_sd.resolve_ticket()


def delete_single_group(entry_dn):
    """ Delete a single group """
    # Delete either the mailing or security group, as per the dn, and return an
    # integer so that we can easily count how many groups were deleted.
    try:
        shared_ldap.delete_object(entry_dn)
        return 1
    except Exception as exc:
        shared_sd.post_comment(
            f"Deleting {entry_dn} failed, error: {str(exc)}", False)
        return 0
