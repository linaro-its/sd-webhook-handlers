"""Handler for requests to view/change group ownership."""
import shared.custom_fields as custom_fields
import shared.globals
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd
import linaro_shared

CAPABILITIES = [
    "CREATE",
    "COMMENT",
    "TRANSITION"
]

IT_BOT = "uid=it.support.bot,ou=mail-contacts-unsynced,ou=accounts,dc=linaro,dc=org"

def comment(ticket_data):
    """ Comment handler """
    last_comment, keyword = shared_sd.central_comment_handler(
        ["add", "remove"],  # Public comments
        ["help", "retry"])  # Private comments

    if keyword == "help":
        shared_sd.post_comment(
            ("All bot commands must be internal comments and the first "
             "word/phrase in the comment.\r\n\r\n"
             "Valid commands are:\r\n"
             "* retry to ask the bot to process the request again after "
             "issues have been resolved."), False)
    elif keyword == "retry":
        shared_sd.transition_request_to("Open")
        create(ticket_data)
    elif (last_comment['public'] and
          last_comment['author']['name'] != shared.globals.CONFIGURATION["bot_name"] and
          shared_sd.get_current_status() != "Resolved"):
        if keyword is None or not process_public_comment(ticket_data, last_comment, keyword):
            shared_sd.post_comment(
                "Your comment has not been recognised as an instruction to "
                "the bot so the ticket will be left for IT Services to "
                "review.", True)
            shared_sd.deassign_ticket_if_appropriate(last_comment)


def process_public_comment(ticket_data, last_comment, keyword):
    """Logic to process a public comment."""
    shared_sd.assign_issue_to(shared.globals.CONFIGURATION["bot_name"])
    # If the original reporter IS a group owner, we will only accept comments
    # from the same person and those comments will be add/remove commands.
    #
    # Otherwise, deassign and let IT work on what was said.
    #
    # Get the definitive email address for the group and the owner(s).
    cf_group_email_address = custom_fields.get("Group Email Address")
    group_email_address = shared_sd.get_field(
        ticket_data, cf_group_email_address).strip().lower()
    group_email_address, result = shared_ldap.find_group(
        group_email_address, ['owner'])
    # Make sure that the group still exists because this is all asynchronous
    # and anything could have happened!
    if len(result) == 0:
        shared_sd.post_comment(
            "Sorry but the group's email address can't be found in Linaro "
            "Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return True
    if len(result) != 1:
        shared_sd.post_comment(
            "Sorry but, somehow, the group's email address appears more than "
            "once in Linaro Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return True

    if (result[0].owner.values != [] and
            shared_ldap.reporter_is_group_owner(result[0].owner.values)):
        if keyword in ("add", "remove"):
            grp_name = shared_ldap.extract_id_from_dn(result[0].entry_dn)
            changes = last_comment["body"].split("\n")
            batch_process_ownership_changes(grp_name, changes)
            post_owners_of_group_as_comment(result[0].entry_dn)
            return True

    return False


def create(ticket_data):
    """Triggered when the issue is created."""
    cf_group_email_address = custom_fields.get("Group Email Address")
    group_email_address = shared_sd.get_field(
        ticket_data, cf_group_email_address).strip().lower()
    group_email_address, result = shared_ldap.find_group(
        group_email_address, ['owner'])

    shared_sd.set_summary(
        "View/Change group ownership for %s" % group_email_address)
    shared_sd.assign_issue_to(shared.globals.CONFIGURATION["bot_name"])

    if len(result) == 0:
        shared_sd.post_comment(
            "Sorry but the group's email address can't be found in Linaro "
            "Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return
    if len(result) != 1:
        shared_sd.post_comment(
            "Sorry but, somehow, the group's email address appears more than "
            "once in Linaro Login.", True)
        shared_sd.resolve_ticket("Won't Do")
        return
    # See if the bot owns this group
    owners = result[0].owner.values
    if (len(owners) == 1 and owners[0] == IT_BOT):
        shared_sd.post_comment(
            (
                "This group is maintained through automation. It is not "
                "possible to change the owners of this group or raise "
                "tickets to directly change the membership. If you want "
                "to understand how this group is maintained automatically, "
                "please raise a general IT Services support ticket."
            ),
            True
        )
        shared_sd.resolve_ticket()
        return

    # Do we have any changes to process? If not, post the current owners to
    # the ticket.
    cf_group_owners = custom_fields.get("Group Owner(s)")
    ownerchanges = shared_sd.get_field(ticket_data, cf_group_owners)
    if ownerchanges is None:
        post_owners_of_group_as_comment(result[0].entry_dn)
        if shared_ldap.reporter_is_group_owner(result[0].owner.values):
            shared_sd.post_comment(
                ("As you are an owner of this group, you can make changes to "
                 "the ownership by posting new comments to this ticket with "
                 "the following format:\r\n"
                 "*add* <email address>\r\n"
                 "*remove* <email address>\r\n"
                 "One command per line but you can have multiple changes in a "
                 "single comment. If you do not get the syntax right, the "
                 "automation will not be able to understand your request and "
                 "processing will stop.\r\n"), True)
            shared_sd.transition_request_to("Waiting for customer")
        else:
            shared_sd.post_comment(
                "As you are not an owner of this group, if you want to make "
                "changes to the ownership, you will need to open a "
                "[new ticket|https://servicedesk.linaro.org/servicedesk/"
                "customer/portal/3/create/140].", True)
            shared_sd.resolve_ticket()
        return

    # There are changes ... but is the requester a group owner?
    cf_approvers = custom_fields.get("Approvers")
    if result[0].owner.values == []:
        # No owners at all. IT is always allowed to make changes
        if shared_ldap.is_user_in_group("its", shared.globals.REPORTER):
            shared_sd.transition_request_to("In progress")
        else:
            shared_sd.post_comment(
                "This group has no owners. Asking IT Services to review "
                "your request.", True)
            it_members = shared_ldap.get_group_membership(
                "cn=its,ou=mailing,ou=groups,dc=linaro,dc=org")
            shared_sd.assign_approvers(it_members, cf_approvers)
            shared_sd.transition_request_to("Needs approval")
    elif shared_ldap.reporter_is_group_owner(result[0].owner.values):
        shared_sd.transition_request_to("In progress")
    else:
        shared_sd.post_comment(
            "As you are not an owner of this group, the owners will be "
            "asked to approve or decline your request.", True)
        shared_sd.assign_approvers(result[0].owner.values, cf_approvers)
        shared_sd.transition_request_to("Needs approval")


def transition(_, status_to, ticket_data):
    """
    If the status is "In Progress", trigger the membership change. This
    status can only be reached from Open or Needs Approval.
    """
    if status_to == "In Progress":
        cf_group_email_address = custom_fields.get("Group Email Address")
        group_email_address = shared_sd.get_field(
            ticket_data, cf_group_email_address).strip().lower()
        group_email_address, result = shared_ldap.find_group(
            group_email_address, ['owner'])
        action_change(ticket_data, result[0])


def action_change(ticket_data, group_owners):
    """ Process the ownership changes specified in the field. """
    grp_name = shared_ldap.extract_id_from_dn(group_owners.entry_dn)
    cf_group_owners = custom_fields.get("Group Owner(s)")
    ownerchanges = shared_sd.get_field(ticket_data, cf_group_owners)
    changes = ownerchanges.split("\r\n")
    cf_added_removed = custom_fields.get("Added / Removed")
    action_value = shared_sd.get_field(ticket_data, cf_added_removed)
    if action_value is None:
        change_to_make = ""
    else:
        change_to_make = action_value
    batch_process_ownership_changes(grp_name, changes, True, change_to_make)
    post_owners_of_group_as_comment(group_owners.entry_dn)
    if (group_owners.owner.values != [] and
            shared_ldap.reporter_is_group_owner(group_owners.owner.values)):
        shared_sd.post_comment(
            ("As you are an owner of this group, you can make changes to the "
             "ownership by posting new comments to this ticket with the "
             "following format:\r\n"
             "*add* <email address>\r\n"
             "*remove* <email address>\r\n"
             "One command per line but you can have multiple changes in a "
             "single comment. If you do not get the syntax right, the "
             "automation will not be able to understand your request and "
             "processing will stop.\r\n"), True)
        shared_sd.transition_request_to("Waiting for customer")
    else:
        shared_sd.resolve_ticket()


def batch_process_ownership_changes(
        group_cn, batch, auto=False, change_to_make=None):
    """Process a list of changes to the ownership."""
    # This is used for the initial ticket (which doesn't specify add/remove)
    # and for followup comments (which *does* specify add/remove). If auto is
    # false, we're expecting "keyword emailaddress" and will stop on the first
    # line that doesn't match that syntax. If auto is true, we're just
    # expecting emailaddress.
    #
    # The formatting of the text varies from "\r\n" in the original request
    # to "\n" in comments, so the *caller* must pass batch as a list.

    change_made = False

    # We need a list of current owners to sanity check the request.
    result = shared_ldap.find_group(group_cn, ["owner"])
    if len(result) == 1:
        owners = result[0].owner.values
    else:
        owners = []

    response = ""

    if auto:
        if change_to_make == "Added":
            keyword = "add"
        elif change_to_make == "Removed":
            keyword = "remove"
        else:
            keyword = "auto"
    else:
        keyword = change_to_make

    for change in batch:
        if change != "":
            local_change, got_error, response = process_change(
                auto, keyword, change, owners, group_cn, response)
            if got_error:
                break
            change_made = change_made or local_change
        else:
            # Stop on a blank line so we don't run into signature blocks on
            # email replies ...
            break

    if change_made:
        linaro_shared.trigger_google_sync()
        response += (
            "Please note it can take up to 15 minutes for these changes to "
            "appear on Google."
        )

    if response != "":
        shared_sd.post_comment(response, True)


def process_change(auto, keyword, change, owners, group_cn, response):
    """ Process the membership change specified. """
    if auto:
        # Should just be an email address with nothing else on that
        # line.
        email_address = change.strip().lower()
    else:
        # Try to get a keyword from this line of text.
        keyword = "".join(
            (char if char.isalpha() else " ") for char in change).\
            split()[0].lower()
        # Split the line on spaces and treat the second "word" as the
        # email address.
        email_address = change.split()[1].lower()

    email_address = linaro_shared.cleanup_if_markdown(email_address)

    result = shared_ldap.find_single_object_from_email(email_address)
    if result is None:
        response += (
            "Couldn't find an entry on Linaro Login with an email "
            "address of '%s'.\r\n" % email_address
        )
        return False, True, response

    return process_keyword(
        keyword, result, owners, email_address, group_cn, response)


def process_keyword(keyword, result, owners, email_address, group_cn, response):
    """ Implement the change for the specified keyword action. """
    change_made = False
    got_error = False
    if keyword == "auto":
        # Is this email address already an owner?
        if result in owners:
            keyword = "add"
        else:
            keyword = "remove"

    if keyword == "add":
        if result in owners:
            response += (
                "%s is already an owner of the group.\r\n"
                % email_address
            )
        else:
            response += "Adding %s\r\n" % email_address
            shared_ldap.add_owner_to_group(group_cn, result)
            change_made = True
    elif keyword == "remove":
        if result in owners:
            response += "Removing %s\r\n" % email_address
            shared_ldap.remove_owner_from_group(
                group_cn, result)
            change_made = True
        else:
            response += (
                "%s is not an owner of the group so it cannot "
                "be removed as one.\r\n" % email_address
            )
    else:
        response += (
            "%s is not recognised as 'add' or 'remove'.\r\n"
            % keyword
        )
        got_error = True
    return change_made, got_error, response


def post_owners_of_group_as_comment(group_full_dn):
    """Emit a list of the owners of the group."""
    # Need to re-fetch the group ownership because we may have changed it
    # since last time we queried it.
    name = shared_ldap.extract_id_from_dn(group_full_dn)
    _, result = shared_ldap.find_group(name, ["owner"])
    if len(result) == 1 and result[0].owner.values != []:
        response = "Here are the owners for the group:\r\n"
        for owner in result[0].owner.values:
            this_owner = shared_ldap.get_object(
                owner,
                ['displayName', 'mail', 'givenName', 'sn'])
            if this_owner.displayName.value is not None:
                display_name = this_owner.displayName.value
            else:
                if this_owner.sn.value is not None:
                    if this_owner.givenName.value is not None:
                        display_name = "%s %s" % (
                            this_owner.givenName.value,
                            this_owner.sn.value)
                    else:
                        display_name = this_owner.sn.value
                else:
                    display_name = this_owner.mail.value

            response += "* [%s|mailto:%s]\r\n" % (
                display_name, this_owner.mail.value)
    else:
        response = "There are no owners for the group."
    shared_sd.post_comment(response, True)
