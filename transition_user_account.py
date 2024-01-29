""" Handler for requests to transition user accounts. """

# The handler transitions accounts between ou=staff and ou=<something else> depending on
# the email addresses specified in the field.
#
# If all transitions succeed, the request is assigned to the bot and marked as resolved,
# otherwise the request is left unassigned, ready for IT Services to review.
#
# There are three possible states:
# Done: if all of the addresses transition OK
# IT: if any of the addresses require IT Services involvement
# Customer: if at least one of the addresses requires customer attention but the rest are OK
#
# For either of the last two, the ticket is left unassigned

from enum import Enum

import shared.custom_fields as custom_fields
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd

RESULT_STATE = Enum("ResultState", "Done IT Customer")

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
    elif last_comment is not None and last_comment["public"]:
        shared_sd.deassign_ticket_if_appropriate(last_comment)


def create(ticket_data):
    """ Create handler. """
    # Start by making sure that the requester is in IT or HR.
    email_address = shared_sd.reporter_email_address(ticket_data)
    print(f"transition_user_account: reporter email address = {email_address}")
    account_dn = shared_ldap.find_from_email(email_address)
    print(f"transition_user_account: account DN = {account_dn}")
    valid_account = shared_ldap.is_dn_in_group("hr", account_dn) or \
        shared_ldap.is_dn_in_group("its", account_dn)
    if not valid_account:
        shared_sd.post_comment(
            "You must be in HR or IT Services to use this request.",
            True)
        shared_sd.resolve_ticket(resolution_state="Won't Do")
        return

    outcome = RESULT_STATE.Done
    cf_addresses = custom_fields.get("Email Address(es) of Users")
    if cf_addresses is None:
        cf_addresses = custom_fields.get("Email Address(es) of Users (Legacy ITS)")
    addresses = shared_sd.get_field(ticket_data, cf_addresses)
    if addresses is None:
        shared_sd.post_comment(
            "Unable to retrieve users to transition",
            True
        )
        shared_sd.resolve_ticket(resolution_state="Won't Do")
        return
    addresses = addresses.split("\r\n")
    for address in addresses:
        # Clean up by trimming white space.
        clean = address.strip().lower()
        if clean != "":
            result = transition_user_account(clean)
            if (result == RESULT_STATE.IT or
                    (result == RESULT_STATE.Customer and outcome == RESULT_STATE.Done)):
                outcome = result
    # Did all of the accounts transition?
    if outcome == RESULT_STATE.Done:
        shared_sd.resolve_ticket()
    elif outcome == RESULT_STATE.Customer:
        shared_sd.post_comment(
            "Sorry but it has not been possible to fully process your request. "
            "Hopefully the above comments are helpful. Further replies to this "
            "ticket will be handled by IT Services staff rather than the automation bot.",
            True
        )
        shared_sd.assign_issue_to(None)
    else:
        shared_sd.transition_request_to("Waiting for Support")


def transition_user_account(email_address):
    """ Transition the account corresponding to the email address. """
    account_dn = shared_ldap.find_from_email(email_address)
    if account_dn is None:
        shared_sd.post_comment("Cannot find '%s'" % email_address, True)
        return RESULT_STATE.Customer

    parts = account_dn.split(",", 2)
    if parts[1] == "ou=leavers":
        return transition_leaver(account_dn, email_address)
    elif parts[1] == "ou=staff":
        shared_sd.post_comment(
            "Cannot transition '%s' because this is an active Linaro account. "
            "It is only possible to transition leaving Linaro accounts." % email_address,
            True
        )
        return RESULT_STATE.Customer

    return transition_member(account_dn, email_address)


def transition_leaver(account_dn, email_address):
    """ Transition a leaver account back to a Member account. """
    account = shared_ldap.get_object(
        account_dn,
        [
            "passwordSelfResetBackupMail",
            "memberOf"
        ])
    if "passwordSelfResetBackupMail" not in account:
        shared_sd.post_comment(
            "Cannot transition '%s' because there isn't a private email "
            "address stored in LDAP. Please provide it to IT Services." % email_address,
            True
        )
        return RESULT_STATE.Customer

    clean_up_account(account)
    return transition_account(
        account,
        account["passwordSelfResetBackupMail"].value,
        email_address)


def transition_member(account_dn, email_address):
    """ Transition a Member account to be a Staff account. """
    account = shared_ldap.get_object(
        account_dn,
        [
            "uid",
            "memberOf"
        ]
    )
    if account is None:
        shared_sd.post_comment(
            f"Can't transition {email_address} because they cannot be found in LDAP",
            True
        )
        return
    if "uid" not in account:
        shared_sd.post_comment(
            f"Can't transition {email_address} because their UID cannot be found",
            True
        )
        return
    new_email = f'{account["uid"]}@linaro.org'.lower()
    check = shared_ldap.find_matching_objects(f"(mail={new_email})", ["cn"])
    if check is not None:
        shared_sd.post_comment(
            f"Can't transition {email_address} because the calculated new email "
            f"address ({new_email}) is in use already.", True)
        shared_sd.post_comment(check[0].entry_dn, False)
        return RESULT_STATE.Customer
    # Good to go ...
    clean_up_account(account)
    return transition_account(account, new_email, email_address)


def clean_up_account(account):
    """Remove the account from any groups."""
    if "memberOf" in account:
        sd_comment = ""
        for grp in account["memberOf"].values:
            if shared_ldap.remove_from_group(grp, account.entry_dn):
                sd_comment += "Removed from %s\r\n" % grp
            else:
                sd_comment += "Failed to remove from %s\r\n" % grp
        if sd_comment != "":
            shared_sd.post_comment(sd_comment, True)


def transition_account(account, new_email, old_email):
    """Move the account and change the email address at the same time."""
    print(f"transition_account: old_email={old_email}")
    print(f"transition_account: new_email={new_email}")
    new_ou = shared_ldap.find_best_ou_for_email(new_email)
    print(f"transition_account: proposed new OU={new_ou}")
    # Make sure we're actually moving the account! Check against existing OU.
    old_ou = account.entry_dn.split(",", 1)[1]
    print(f"transition_account: comparing against old_ou={old_ou}")
    print(f"transition_account: derived from DN {account.entry_dn}")
    if old_ou == new_ou:
        shared_sd.post_comment(
            "Can't transition %s: OU is stuck at %s. IT Services needs to investigate "
            "further." % (old_email, old_ou), True)
        return RESULT_STATE.IT
    # Change the mail and cn attributes.
    shared_ldap.replace_attribute_value(account.entry_dn, "mail", new_email)
    shared_ldap.replace_attribute_value(account.entry_dn, "cn", new_email)
    # Remove various attributes if they are there ..
    for attr in [
            "userPassword",
            "businessCategory",
            "departmentNumber",
            "employeeNumber",
            "employeeType",
            "l",
            "labeledURI",
            "manager",
            "o",
            "passwordSelfResetBackupMail",
            "roomNumber",
            "secretary",
            "title"]:
        shared_ldap.replace_attribute_value(account.entry_dn, attr, None)
    # If there are any staff accounts that have this entry as their Member Company Line
    # Manager, need to update the reference
    check_secretary(account.entry_dn)
    # Finally, rename and move the account
    result = shared_ldap.move_object(account.entry_dn, new_ou)
    if result is None:
        shared_sd.post_comment(
            "Successfully transitioned %s to %s.\r\n"
            "Please note that the account does not have a password set, nor is it in any "
            "groups." % (old_email, new_ou), True)
        return RESULT_STATE.Done

    shared_sd.post_comment(
        "Got error when trying to move %s to %s. IT Services needs to investigate "
        "further." % (old_email, new_ou), True)
    shared_sd.post_comment("The error was: %s" % result, False)
    return RESULT_STATE.IT


def check_secretary(account_dn):
    """Flag up any accounts that have this account as their Member company manager."""
    result = shared_ldap.find_matching_objects("(secretary=%s)" % account_dn, ["cn"])
    if result is not None:
        alert = (
            "[~philip.colmer@linaro.org] Need to modify the following accounts as they "
            "reference %s as their Member Company Line Manager.\r\n" % account_dn
        )
        for entry in result:
            alert += "* %s\r\n" % entry.entry_dn
        shared_sd.post_comment(alert, False)
