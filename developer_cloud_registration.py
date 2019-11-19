""" Handler for Developer Cloud Registration. """

import os
from enum import Enum
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import shared.shared_sd as shared_sd
import shared.custom_fields as custom_fields
import shared.shared_ldap as shared_ldap
import shared.email


# Define what this handler can handle :)
# Using strings avoids the need to access defines elsewhere.
CAPABILITIES = [
    "TRANSITION"
]

SAVE_TICKET_DATA = False


class AccountCreationStatus(Enum):
    """ Define the various possibilities from creating an account. """
    CREATION_FAILED = 1
    ACCOUNT_EXISTED = 2
    ACCOUNT_CREATED = 3


def create_ldap_account(ticket_data):
    """ Create a LDAP account based off the ticket data. """
    result = AccountCreationStatus.ACCOUNT_EXISTED
    cf_firstname = custom_fields.get("First Name")
    cf_familyname = custom_fields.get("Family Name")
    # Start by retrieving and cleaning up the data from the ticket.
    email_address = shared_sd.reporter_email_address(ticket_data).strip()
    email_address = shared_ldap.cleanup_if_gmail(email_address)
    first_name = shared_sd.get_field(ticket_data, cf_firstname).strip()
    family_name = shared_sd.get_field(ticket_data, cf_familyname).strip()
    # Does an account already exist? If not, create it.
    account_dn = shared_ldap.find_from_email(email_address)
    if account_dn is None:
        result = AccountCreationStatus.ACCOUNT_CREATED
        account_dn = shared_ldap.create_account(
            first_name,
            family_name,
            email_address
        )
        if account_dn is None:
            result = AccountCreationStatus.CREATION_FAILED
            shared_sd.post_comment("Failed to create account", True)
    # Make sure that the account is a member of dev-cloud-users
    if not shared_ldap.add_to_group("dev-cloud-users", account_dn):
        shared_sd.post_comment("Failed to add to dev-cloud-users", False)
    return result


def send_welcome_email(ticket_data):
    """ Send a welcome email to the ticket requester. """
    cf_firstname = custom_fields.get("First Name")
    cf_familyname = custom_fields.get("Family Name")
    email_address = shared_sd.reporter_email_address(ticket_data).strip()
    email_address = shared_ldap.cleanup_if_gmail(email_address)
    account_dn = shared_ldap.find_from_email(email_address)
    uid = account_dn.split("=", 1)[1].split(",", 1)[0]
    # Read in the template email.
    file_dir = os.path.dirname(os.path.abspath(__file__))
    with open("%s/developer_cloud_registration_email.txt" % file_dir, "r") as email_file:
        body = email_file.read()
    # Substitute the parameters
    name = shared_sd.get_field(ticket_data, cf_firstname).strip()
    if name == "":
        name = shared_sd.get_field(ticket_data, cf_familyname).strip()
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


def create_openstack_ticket(ticket_data):
    """ Create a ticket for a new OpenStack project. """
    email_address = shared_sd.reporter_email_address(ticket_data).strip()
    email_address = shared_ldap.cleanup_if_gmail(email_address)
    service_desk_id = shared_sd.get_servicedesk_id("DC")
    if service_desk_id == -1:
        shared_sd.post_comment(
            "Unable to get ID for DC Service Desk project", False)
        return
    request_type_id = shared_sd.get_request_type_id(
        "Request a new OpenStack project", service_desk_id)
    if request_type_id == -1:
        shared_sd.post_comment(
            "Unable to get ID for new OpenStack project request type", False)
        return

    cf_devcloud_project_size = custom_fields.get("DevCloud Project Size")
    cf_devcloud_special_request = custom_fields.get("DevCloud Special Request")
    cf_devcloud_public_ips = custom_fields.get("DevCloud Public IP Addresses")
    cf_devcloud_duration = custom_fields.get("DevCloud Project Duration")
    if (cf_devcloud_project_size is None or
            cf_devcloud_special_request is None or
            cf_devcloud_public_ips is None or
            cf_devcloud_duration is None):
        shared_sd.post_comment(
            "Unable to get custom field IDs for OpenStack project request", False)
        return
    value_devcloud_project_size = shared_sd.get_field(ticket_data, cf_devcloud_project_size)
    value_devcloud_special_request = shared_sd.get_field(ticket_data, cf_devcloud_special_request)
    value_devcloud_public_ips = shared_sd.get_field(ticket_data, cf_devcloud_public_ips)
    value_devcloud_duration = shared_sd.get_field(ticket_data, cf_devcloud_duration)
    request = {
        "serviceDeskId": service_desk_id,
        "requestTypeId": request_type_id,
        "requestFieldValues": {
            "customfield_%s" % cf_devcloud_project_size: value_devcloud_project_size,
            "customfield_%s" % cf_devcloud_public_ips: value_devcloud_public_ips,
            "customfield_%s" % cf_devcloud_duration: value_devcloud_duration
        },
        "raiseOnBehalfOf": email_address
    }
    if value_devcloud_special_request is not None:
        request["requestFieldValues"]["customfield_%s" % cf_devcloud_special_request] = \
            value_devcloud_special_request
    shared_sd.create_request(request)


def transition(status_from, status_to, ticket_data):
    """ Transition handler. """
    print("Transition from %s to %s" % (status_from, status_to))
    # When a DCR issue is created, it must be approved before the
    # automation does anything with the issue. Therefore, we wait
    # for the issue to transition appropriately.
    if (status_from != "Waiting for approval" or
            status_to != "Approved"):
        return
    #
    # Create an account on LDAP for this person.
    result = create_ldap_account(ticket_data)
    if result != AccountCreationStatus.CREATION_FAILED:
        #
        # Send them an email telling them how to set their password
        # and upload SSH keys.
        if result == AccountCreationStatus.ACCOUNT_CREATED:
            send_welcome_email(ticket_data)
        #
        # Create a ticket in the DC project to request a new
        # OpenStack project.
        create_openstack_ticket(ticket_data)
        #
        # Resolve the ticket.
        shared_sd.resolve_ticket()
