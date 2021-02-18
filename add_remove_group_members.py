""" This code handles the add/remove users from group request type """

import shared.custom_fields as custom_fields
import shared.globals
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd
import linaro_shared

CAPABILITIES = [
    "COMMENT",
    "CREATE"
]

IT_BOT = (
    'uid=it.support.bot,ou=mail-contacts-unsynced,'
    'ou=accounts,dc=linaro,dc=org'
)

def comment(ticket_data):
    """ Triggered when a comment is posted """
    last_comment, keyword = shared_sd.central_comment_handler(
        ["add", "remove"], ["help", "retry"], False)

    if keyword == "help":
        shared_sd.post_comment(
            ("All bot commands must be internal comments and the first"
             " word/phrase in the comment.\r\n\r\n"
             "Valid commands are:\r\n"
             "* retry to ask the bot to process the request again after issues"
             " have been resolved."),
            False)
        return

    if keyword == "retry":
        shared_sd.transition_request_to("Open")
        create(ticket_data)
        return

    current_status = shared_sd.get_current_status()
    if (last_comment['public'] and
            last_comment['author']['name'] != shared.globals.CONFIGURATION["bot_name"] and
            current_status != "Resolved"):
        if keyword is None or not process_public_comment(ticket_data, last_comment, keyword):
            shared_sd.post_comment(
                "Current status is %s" % current_status,
                False)
            shared_sd.post_comment(
                "Your comment has not been recognised as an instruction to the"
                " bot so the ticket will be left for IT Services to review.",
                True)
            shared_sd.deassign_ticket_if_appropriate(last_comment)

def process_public_comment(ticket_data, last_comment, keyword):
    """ Logic to process a public comment """
    shared_sd.assign_issue_to(shared.globals.CONFIGURATION["bot_name"])
    # If the original reporter IS a group owner, we will only accept comments
    # from the same person and those comments will be add/remove commands.
    #
    # Otherwise, deassign and let IT work on what was said.
    _, result = get_group_details(ticket_data)
    # Make sure that the group still exists because this is all asynchronous
    # and anything could have happened!
    if not group_sanity_check(result):
        return True
    if "owner" in result[0] and shared_ldap.reporter_is_group_owner(
            result[0].owners.values):
        if keyword in ("add", "remove"):
            distinguished = result[0].entry_dn
            grp_name = shared_ldap.extract_id_from_dn(distinguished)
            changes = last_comment["body"].split("\n")
            batch_process_membership_changes(grp_name, changes, False)
            return True
    return False

def create(ticket_data):
    """ Triggered when the issue is created """
    cf_approvers = custom_fields.get("Approvers")
    group_email_address, result = get_group_details(ticket_data)

    shared_sd.set_summary(
        "Add/Remove group members for %s" % group_email_address)
    shared_sd.assign_issue_to(shared.globals.CONFIGURATION["bot_name"])
    if not group_sanity_check(result):
        return

    group_obj = result[0]
    if "owner" not in group_obj:
        if shared_ldap.is_user_in_group("its", shared.globals.REPORTER):
            shared_sd.transition_request_to("In progress")
            return

        shared_sd.post_comment(
            "This group has no owners. Asking IT Services to review your"
            " request.", True)
        it_members = shared_ldap.get_group_membership(
            "cn=its,ou=mailing,ou=groups,dc=linaro,dc=org")
        shared_sd.assign_approvers(it_members, cf_approvers)
        return

    if IT_BOT in group_obj.owner.values:
        shared_sd.post_comment(
            "Sorry but the membership of this group is maintained"
            " automatically.", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    if shared_ldap.reporter_is_group_owner(group_obj.owner.values):
        shared_sd.transition_request_to("In progress")
        return

    shared_sd.post_comment(
        "As you are not an owner of this group, the owners will be asked"
        " to approve or decline your request.", True)
    shared_sd.assign_approvers(group_obj.owner.values, cf_approvers)

def transition(status_to, ticket_data):
    """
    If the status is "In Progress", trigger the membership change. This
    status can only be reached from Open or Needs Approval.
    """
    if status_to == "In Progress":
        _, result = get_group_details(ticket_data)
        action_group_membership_change(result[0], ticket_data)

def action_group_membership_change(group_obj, ticket_data):
    """ Apply the membership changes from the ticket """
    grp_name = shared_ldap.extract_id_from_dn(group_obj)
    cf_group_member_email_addresses = custom_fields.get(
        "Group member email addresses")
    changes = shared_sd.get_field(ticket_data, cf_group_member_email_addresses)
    changes = linaro_shared.response_split(changes)
    cf_add_remove = custom_fields.get("Added / Removed")
    change_to_make = shared_sd.get_field(ticket_data, cf_add_remove)
    batch_process_membership_changes(grp_name, changes, True, change_to_make)
    # Need to check if the requester is a group owner ...
    if "owner" in group_obj and shared_ldap.reporter_is_group_owner(
            group_obj.owner.values):
        shared_sd.post_comment(
            ("As you are an owner of this group, you can make further changes"
             " to the membership by posting new comments to this ticket with"
             " the following format:\r\n"
             "*add* <email address>\r\n"
             "*remove* <email address>\r\n"
             "One command per line but you can have multiple changes in a "
             "single comment. If you do not get the syntax right, the "
             "automation will not be able to understand your request and "
             "processing will stop.\r\n"), True)
        shared_sd.transition_request_to("Waiting for customer") # This shouldn't be
        # necessary as comments from the assignee should trigger the
        # transition but it isn't.
    else:
        shared_sd.resolve_ticket()

def batch_process_membership_changes(
        group_cn,
        batch,
        auto=False,
        change_to_make=None):
    """ Process a list of changes to the membership """
    # If auto is false, we're expecting "keyword emailaddress" and will stop on
    # the first line that doesn't match that syntax. If auto is true, we're
    # just expecting emailaddress and the change flag will indicate add or
    # remove.
    #
    # The formatting of the text varies from "\r\n" in the original request to
    # "\n" in comments, so the *caller* must pass batch as a list.

    change_made = False

    # We need a list of current members to sanity check the request.
    _, result = shared_ldap.find_group(
        "cn=%s,ou=mailing,ou=groups,dc=linaro,dc=org" % group_cn, ["uniqueMember"])
    if len(result) == 1 and "uniqueMember" in result[0]:
        members = result[0].uniqueMember.values
    else:
        members = []

    response = ""
    keyword = determine_auto_keyword(auto, change_to_make)

    for change in batch:
        if change != "":
            if auto:
                # Should just be an email address with nothing else on that
                # line.
                email_address = change.strip().lower()
            else:
                # Split the line on spaces and treat the second "word" as the
                # email address.
                split = change.split()
                if len(split) > 1:
                    email_address = change.split()[1].lower()
                else:
                    response += (
                        "\r\nCouldn't find a command at the start of '%s'. "
                        "*Processing of this request will now stop.*\r\n" %
                        change)
                    break
                # Try to get a keyword from this line of text. Do this after
                # the splitting to make sure there is a keyword to be had.
                keyword = "".join(
                    (char if char.isalpha() else " ") for char in change).\
                    split()[0].lower()

            result = find_member_change(email_address)

            if keyword == "add":
                if result is None:
                    response += (
                        "Couldn't find an entry '%s' on Linaro Login. Please "
                        "use https://servicedesk.linaro.org/servicedesk/"
                        "customer/portal/3/create/120 to create a contact "
                        "(email only) or external account (if login required) "
                        "and then submit a new ticket to add them.\r\n" %
                        email_address)
                elif result == (
                        "cn=%s,ou=mailing,ou=groups,dc=linaro,dc=org" %
                        group_cn):
                    response += (
                        "You cannot add the group as a member to itself.\r\n")
                elif result in members:
                    response += (
                        "%s is already a member of the group.\r\n" %
                        email_address)
                else:
                    response += "Adding %s\r\n" % email_address
                    shared_ldap.add_to_group(group_cn, result)
                    members.append(result)
                    change_made = True
            elif keyword == "remove":
                if result is None:
                    response += (
                        "Couldn't find an entry '%s' on Linaro Login. Did you "
                        "mistype?\r\n" % email_address)
                elif result in members:
                    response += "Removing %s\r\n" % email_address
                    shared_ldap.remove_from_group(group_cn, result)
                    members.remove(result)
                    change_made = True
                else:
                    response += (
                        "%s is not a member of the group so it cannot be "
                        "removed as one.\r\n" % email_address)
            else:
                response += (
                    "%s is not recognised as 'add' or 'remove'.\r\n" % keyword)
        else:
            # Stop on a blank line so we don't run into signature blocks on
            # email replies ...
            break

    if change_made:
        linaro_shared.trigger_google_sync()
        response += (
            "Please note it can take up to 15 minutes for these changes to "
            "appear on Google.")

    if response != "":
        shared_sd.post_comment(response, True)
    return

def get_group_details(ticket_data):
    """ Get the true email address and LDAP object for the specified group """
    cf_group_email_address = custom_fields.get("Group Email Address")
    group_email_address = shared_sd.get_field(
        ticket_data, cf_group_email_address).strip().lower()
    return shared_ldap.find_group(
        group_email_address, ['owner'])

def group_sanity_check(ldap_obj):
    """ Check that we've got one and only one object """
    if len(ldap_obj) == 0:
        shared_sd.post_comment(
            "Sorry but the group's email address can't be found in Linaro"
            " Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return False
    if len(ldap_obj) != 1:
        shared_sd.post_comment(
            "Sorry but, somehow, the group's email address appears more than"
            " once in Linaro Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return False
    return True

def determine_auto_keyword(auto, change_to_make):
    """ Return the keyword based on the parameters """
    if auto:
        if change_to_make == "Added":
            return "add"
        return "remove"
    return None

def find_member_change(person):
    """ Get the LDAP object from the email address or UID """
    person = linaro_shared.cleanup_if_markdown(person)
    if "@" in person:
        return shared_ldap.find_single_object_from_email(person)
    return shared_ldap.find_from_attribute("uid", person)
