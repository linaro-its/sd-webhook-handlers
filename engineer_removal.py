""" This code is triggered when an Engineer Removal ticket is created """

import shared.shared_sd as shared_sd
import shared.shared_ldap as shared_ldap
import shared.custom_fields as custom_fields
import shared.globals
import linaro_shared

CAPABILITIES = [
    "COMMENT",
    "CREATE"
]

def comment(ticket_data):
    """ Triggered when a comment is posted """
    _, keyword = shared_sd.central_comment_handler(
        [], ["help", "retry"])

    if keyword == "help":
        shared_sd.post_comment(("All bot commands must be internal comments and the first word/phrase in the comment.\r\n\r\n"
                               "Valid commands are:\r\n"
                               "* retry to ask the bot to process the request again after issues have been resolved."), False)
    elif keyword == "retry":
        print("engineer_removal processing retry keyword & triggering create function")
        create(ticket_data)

def create(ticket_data):
    linaro_shared.check_approval_assignee_member_engineer(ticket_data)
    cf_engineer = custom_fields.get("Assignee/Member Engineer")
    ldap_dn = linaro_shared.get_dn_from_account_id(ticket_data, cf_engineer)
    if ldap_dn is None:
        return

    ldap_search = shared_ldap.get_object(
        ldap_dn,
        ['employeeType', 'secretary'])
    if ldap_search is None:
        return
    
    print("engineer_removal:")
    print(ldap_search)

    employee_type = ldap_search.employeeType.value
    if employee_type not in [
        "Assignee",
        "Member Engineer",
        "Affiliate Engineer"
        ]:
        return


    # If there is a "secretary" record for this person, add them as a request
    # participant.
    secretary = ldap_search.secretary.value
    if secretary is not None:
        secretary = shared_ldap.get_email_address(secretary)
    print(f"engineer_removal: secretary is {secretary}")
    if secretary is not None and secretary != shared.globals.REPORTER:
        shared_sd.add_request_participant(secretary)
