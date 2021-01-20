""" Handler to create external users or accounts. """

import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import shared.custom_fields as custom_fields
import shared.email
import shared.globals
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd

import linaro_shared

# Define what this handler can handle.
CAPABILITIES = [
    "COMMENT",
    "CREATE"
]

def comment(ticket_data):
    """ Comment handler """
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
    elif last_comment['public']:
        shared_sd.resolve_ticket()

def create(ticket_data):
    """ Ticket creation handler. """
    cf_email_address = custom_fields.get("Email Address")
    email_address = shared_sd.get_field(
        ticket_data, cf_email_address).strip().lower()
    email_address = shared_ldap.cleanup_if_gmail(email_address)

    shared_sd.set_summary("Create external user/account for %s" % email_address)

    if not ok_to_proceed(email_address):
        return

    cf_first_name = custom_fields.get("First Name")
    cf_family_name = custom_fields.get("Family Name")
    first_name = shared_sd.get_field(
        ticket_data, cf_first_name)
    if first_name is not None:
        first_name = first_name.strip()
    surname = shared_sd.get_field(
        ticket_data, cf_family_name).strip()

    uid = shared_ldap.calculate_uid(first_name, surname)
    if uid is None:
        shared_sd.post_comment("It has not been possible to create the account as requested.", True)
        shared_sd.resolve_ticket("Declined")
        return

    md5_password = None
    cf_account_type = custom_fields.get("External Account / Contact")
    account_type = shared_sd.get_field(ticket_data, cf_account_type)
    if account_type != "Contact":
        _, md5_password = linaro_shared.make_password()
    account_dn = shared_ldap.create_account(
        first_name,
        surname,
        email_address,
        md5_password
    )
    if account_dn is None:
        shared_sd.post_comment(
            "Sorry but something went wrong while creating the entry",
            True)
        shared_sd.transition_request_to("Waiting for support")
        shared_sd.assign_issue_to(None)
        return

    if account_type != "Contact":
        send_new_account_email(
            first_name,
            surname,
            email_address,
            account_dn
        )

    shared_sd.resolve_ticket()

def ok_to_proceed(email_address):
    """ Enforce company policy rules. """
    # Is the email address already present in LDAP?
    check = shared_ldap.find_from_email(email_address)
    if check is None:
        check = shared_ldap.find_from_attribute("cn", email_address)
    if check is not None:
        response = (
            "Cannot fulfil this request because the email address is "
            "already being used by %s" % check
        )
        shared_sd.post_comment(response, True)
        shared_sd.resolve_ticket("Won't Do")
        return False

    check = shared_ldap.find_from_attribute("passwordSelfResetBackupMail", email_address)
    if check is not None:
        dup_email = shared_ldap.get_object(check, ["mail"])
        if dup_email.mail.values != []:
            dup_email = dup_email.mail.values[0]
        else:
            # No email address so provide the DN instead
            dup_email = check

        response = (
            "Cannot fulfil this request because there is a Linaro "
            "account associated with the email address (%s)" % dup_email
        )
        shared_sd.post_comment(response, True)
        shared_sd.resolve_ticket("Won't Do")
        return False

    org_unit = shared_ldap.find_best_ou_for_email(email_address)
    if org_unit == "ou=staff,ou=accounts,dc=linaro,dc=org":
        shared_sd.post_comment(
            "Cannot fulfil this request because the email address is "
            "reserved for Linaro staff.",
            True)
        shared_sd.resolve_ticket("Won't Do")
        return False

    # Who is asking for this account? If staff, they can create any account.
    # If not, the OU must match.
    reporter_ou = shared_ldap.find_best_ou_for_email(shared.globals.REPORTER)
    if reporter_ou != "ou=staff,ou=accounts,dc=linaro,dc=org":
        if org_unit == "ou=the-rest,ou=accounts,dc=linaro,dc=org":
            shared_sd.post_comment(
                "Only Linaro staff and Linaro Members can create additional accounts.",
                True)
            shared_sd.resolve_ticket("Won't Do")
            return False
        if reporter_ou != org_unit:
            shared_sd.post_comment(
                "Cannot fulfil this request because you can "
                "only create accounts/contacts for your own organisation.",
                True)
            shared_sd.resolve_ticket("Won't Do")
            return False

    return True

def send_new_account_email(first_name, surname, email_address, account_dn):
    """ Send the new account email. """
    uid = account_dn.split("=", 1)[1].split(",", 1)[0]
    # Read in the template email.
    file_dir = os.path.dirname(os.path.abspath(__file__))
    with open("%s/developer_cloud_registration_email.txt" % file_dir, "r") as email_file:
        body = email_file.read()
    # Substitute the parameters
    name = first_name
    if name == "":
        name = surname
    body = body.format(
        name,
        email_address,
        uid
    )
    # and send it.
    msg = MIMEMultipart('alternative')
    msg['Subject'] = "Your Developer Cloud registration"
    msg['From'] = "it-support@linaro.org"
    msg['To'] = email_address
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    shared.email.send_email(msg)
