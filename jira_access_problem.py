"""Handle a JIRA access problem ticket."""

# This automation ONLY fires when the ticket is created. It does NOT
# respond to comments. The purpose of the automation is to see if there
# are any obvious reasons why access isn't possible and either advise
# on the steps to take or take them automatically.

import shared.globals
from shared import custom_fields, shared_ldap, shared_sd

def create(ticket_data):
    """ React to the ticket being created """
    # Is this for the reporter or someone else?
    cf_email_address = custom_fields.get("Email Address")
    person = shared_sd.get_field(ticket_data, cf_email_address)
    if person is None:
        person = shared.globals.REPORTER
    if person is not None:
        person = person.strip().lower()
    # Do they have an account in LDAP?
    person_dn = shared_ldap.find_single_object_from_email(person)
    if person_dn is None:
        shared_sd.post_comment(
            f"There isn't an account in Linaro Login with {person} as the email address.\r\n"
            "Please go to https://linaro-servicedesk.atlassian.net/servicedesk/customer/portal/32/group/117/create/557 "
            "and create an *external account* for this person.\r\n"
            "It will then be necessary to go to "
            "https://linaro-servicedesk.atlassian.net/servicedesk/customer/portal/32/group/113/create/547 to request "
            "access to JIRA once the account has been created.", True)
        shared_sd.resolve_ticket()
        return
    if "ou=mailing" in person_dn:
        shared_sd.post_comment(
            f"The email address {person} belongs to a group. "
            "Please submit a new ticket with a person's email address.", True)
        shared_sd.resolve_ticket()
    # Does this account have access to JIRA?
    jira_access = shared_ldap.get_group_membership(
        "cn=jira-users,ou=mailing,ou=groups,dc=linaro,dc=org")
    if person_dn not in jira_access:
        shared_sd.post_comment(
            f"{person} hasn't been granted access to JIRA.\r\n"
            "Please go to https://linaro-servicedesk.atlassian.net/servicedesk/customer/portal/32/group/116/create/551 "
            "to request access for them.", True)
        shared_sd.resolve_ticket()
