""" Handler to create a new LDAP group. """

import json
import re

import shared.custom_fields as custom_fields
import shared.globals
import shared.shared_google as shared_google
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd

import linaro_shared

CAPABILITIES = [
    "COMMENT",
    "CREATE"
]


def comment(ticket_data):
    """ Comment handler. """
    last_comment, keyword = shared_sd.central_comment_handler(
        [],
        ["help", "retry"]
    )
    if keyword == "help":
        shared_sd.post_comment(
            "All bot commands must be internal comments and the first "
            "word/phrase in the comment.\r\n\r\n"
            "Valid commands are:\r\n"
            "* retry to ask the bot to process the request again after issues have been resolved.",
            False)
    elif keyword == "retry":
        create(ticket_data)
    elif last_comment is not None and last_comment['public']:
        shared_sd.deassign_ticket_if_appropriate(comment)


def create(ticket_data):
    """ Create handler. """
    if not shared_ldap.is_user_in_group("employees", shared.globals.REPORTER):
        shared_sd.post_comment(
            "Sorry but only Linaro employees can use this Service Request.",
            True)
        shared_sd.resolve_ticket("Declined")
        return

    cf_group_name = custom_fields.get("Group / List Name")
    cf_group_description = custom_fields.get("Group / List Description")
    cf_group_owners = custom_fields.get("Group Owner(s)")
    cf_group_email_address = custom_fields.get("Group Email Address")

    group_display_name = shared_sd.get_field(
        ticket_data, cf_group_name)
    if group_display_name is None:
        shared_sd.post_comment(
            "Sorry but a display name must be provided.",
            True
        )
        shared_sd.resolve_ticket("Declined")
        return

    group_description = shared_sd.get_field(ticket_data, cf_group_description)
    if group_description is None:
        shared_sd.post_comment(
            "Sorry but a group description must be provided.",
            True
        )
        shared_sd.resolve_ticket("Declined")
        return

    group_display_name = group_display_name.strip()
    group_lower_name = group_display_name.lower()
    # Take the group name, make it lower case, replace spaces with hyphens and
    # remove any other potentially troublesome characters.
    group_name = re.sub(r"\s+", '-', group_lower_name)
    group_name = re.sub(r"[^\w\s-]", '', group_name)
    group_email_address = shared_sd.get_field(
        ticket_data, cf_group_email_address)
    if group_email_address is None:
        group_email_address = group_name + "@linaro.org"
        group_domain = "linaro.org"
    else:
        group_email_address = group_email_address.strip().lower()
        # Check we have a domain
        if "@" not in group_email_address:
            group_email_address += "@linaro.org"
            group_domain = "linaro.org"
        else:
            group_domain = group_email_address.split('@')[1]

    shared_sd.set_summary(f"Create LDAP group for {group_email_address}")

    result = shared_ldap.find_from_email(group_email_address)
    if result is not None:
        reply = (
            f"Cannot create this group because the email address ('{group_email_address}') is "
            f"already being used by the LDAP object {result}")
        shared_sd.post_comment(reply, True)
        shared_sd.resolve_ticket("Won't Do")
        return

    result = shared_ldap.find_from_attribute("cn", group_name)
    if result is not None:
        reply = (
            f"Cannot create this group because the name ('{group_name}') is already "
            f"being used by the LDAP object {result}")
        shared_sd.post_comment(reply, True)
        shared_sd.resolve_ticket("Won't Do")
        return

    google = shared_google.check_group_alias(group_email_address)
    if google is not None:
        shared_sd.post_comment(
            "Cannot create this group because the email address is an alias "
            f"for the group {google}", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    group_description = group_description.strip()

    if "=" in group_description or "=" in group_display_name:
        shared_sd.post_comment(
            "Sorry but due to a Google limitation it is not possible to "
            "create a group that uses the equal sign in the group's name or "
            "description.", True)
        shared_sd.resolve_ticket("Won't Do")
        return

    owner_list = []
    group_owners = shared_sd.get_field(ticket_data, cf_group_owners)
    if group_owners is not None:
        owner_list = process_group_owners(group_owners)
    if not owner_list:
        owner_list = handle_empty_owners()

    result = shared_ldap.create_group(
        group_name,
        group_description,
        group_display_name,
        group_email_address,
        owner_list
    )
    if result is not None:
        shared_sd.post_comment(
            "Sorry but something when wrong while creating the group. "
            "IT Services will investigate further.", True)
        shared_sd.post_comment(json.dumps(result), False)
        shared_sd.transition_request_to("Waiting for Support")
        return

    linaro_shared.trigger_google_sync()

    # If the user has specified a custom email address, the URL for the group
    # uses *that* instead of the group's name. So, basically, always use the
    # bit that comes before the domain string.
    group_name = group_email_address.split('@')[0]

    response = ("A group has been created on Linaro Login with an"
                " email address of %s.\r\n"
                "To change who can post to the group, or to change the "
                "conversation history setting, go to:\r\n"
                "https://groups.google.com/a/%s/g/%s/settings#posting\r\n"
                "\r\nIMPORTANT! Do not change group membership via Google."
                " It MUST be done via the [Add/Remove Users from Group|"
                "https://servicedesk.linaro.org/servicedesk/customer/portal/"
                "3/create/139] request otherwise changes will be lost.")

    shared_sd.post_comment(response % (
            group_email_address,
            group_domain,
            group_name
        ), True)

    shared_sd.resolve_ticket()


def process_group_owners(data):
    """
    We ask for owners as email addresses but LDAP needs the DN for the
    appropriate object
    """
    owner_list = []
    owners = data.split("\r\n")
    for owner in owners:
        if owner != "":
            result = shared_ldap.find_from_email(owner)
            if result is None:
                shared_sd.post_comment(
                    f"Unable to add {owner} as an owner as the email address "
                    "cannot be found in Linaro Login.", True)
            else:
                # Need to make sure we append the mailing group if it
                # is a group!
                if ",ou=security," not in result:
                    owner_list.append(result)
                    shared_sd.post_comment(
                        f"Adding {owner} as an owner.", True)
    return owner_list


def handle_empty_owners():
    """
    Try to add the reporter as a fall-back owner or if no alternative
    owners have been specified. This should work since only employees
    are allowed to use this request type and all employees are in LDAP.
    """
    result = shared_ldap.find_from_email(shared.globals.REPORTER)
    if result is not None:
        shared_sd.post_comment(
            f"Adding {shared.globals.REPORTER} as the owner of the group.", True)
        return [result]

    # OK - something stupid is happening but let's give ourselves
    # a safety net.
    shared_sd.post_comment(
        f"Unable to add {shared.globals.REPORTER} as an owner as the email address cannot be "
        "found in Linaro Login. This means the automation has not "
        "been able to find any of the specified email addresses in "
        "Linaro Login. Consequently, IT Services will need to manage "
        "it in the interim.", True)
    return ["cn=its,ou=mailing,ou=groups,dc=linaro,dc=org"]
