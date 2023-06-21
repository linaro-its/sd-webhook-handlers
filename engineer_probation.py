""" This code is triggered when an Engineer Probation ticket is created """

import shared.shared_sd as shared_sd
import shared.shared_ldap as shared_ldap
import shared.custom_fields as custom_fields
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
        print("engineer_probation processing retry keyword & triggering create function")
        create(ticket_data)

def create(ticket_data):
    linaro_shared.check_approval_assignee_member_engineer(ticket_data)
    cf_engineer = custom_fields.get("Assignee/Member Engineer")
    ldap_dn = linaro_shared.get_dn_from_account_id(ticket_data, cf_engineer)
    if ldap_dn is None:
        return

    ldap_search = shared_ldap.get_object(
        ldap_dn,
        ['employeeType', 'departmentNumber', 'o'])
    if ldap_search is None:
        return
    
    print("engineer_probation:")
    print(ldap_search)

    employee_type = ldap_search.employeeType.value
    if employee_type not in [
        "Assignee",
        "Member Engineer",
        "Affiliate Engineer"
        ]:
        return

    # See if the team was specified - if not, set it from LDAP knowledge
    cf_engineering_team = custom_fields.get("Engineering Team")
    value = shared_sd.get_field(ticket_data, cf_engineering_team)
    if value is None:
        print(f"Setting engineering team to '{ldap_search.departmentNumber.value}'")
        shared_sd.set_customfield(cf_engineering_team, ldap_search.departmentNumber.value)
    # See if the member company was specified - if not, set it from LDAP
    # knowledge
    cf_member_company_name = custom_fields.get("Member Company Name")
    value = shared_sd.get_field(ticket_data, cf_member_company_name)
    if value is None:
        shared_sd.set_customfield(cf_member_company_name, ldap_search.o.value)
    # And finally the engineer type
    cf_engineer_type = custom_fields.get("Engineer Type")
    value = shared_sd.get_field(ticket_data, cf_engineer_type)
    if value is None:
        if employee_type == "Member Engineer":
            employee_type = "Member"
        if employee_type == "Affiliate Engineer":
            employee_type = "Affiliate"
        print(f"Setting engineer type to '{employee_type}'")
        shared_sd.set_customfield(cf_engineer_type, employee_type)
    # Add Engineering VP & Developer Services GM as request participants
    # (https://servicedesk.linaro.org/browse/ITS-4715)
    shared_sd.add_request_participant("tim.benton@linaro.org")
    shared_sd.add_request_participant("joe.bates@linaro.org")
