""" Handler to staff modification requests. """

# Check who has submitted the ticket. If it is the line manager for the
# affected employee/contractor, move the ticket to Executive Approval.
#
# Otherwise, add the manager as the approver and move the issue to Needs
# Approval.

import shared.custom_fields as custom_fields
import shared.globals
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd
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
        print("modify_staff processing retry keyword & triggering create function")
        create(ticket_data)


def get_affected_person(ticket_data):
    """ Return the email address for the affected person. """
    cf_who_picker = custom_fields.get("Employee/Contractor")
    who = shared_sd.get_field(ticket_data, cf_who_picker)
    if who is not None and "emailAddress" not in who:
        who = shared_sd.find_account_from_id(who["accountId"])
    return who


def create(ticket_data):
    """Triggered when the issue is created."""
    # Who is this ticket about?
    person = get_affected_person(ticket_data)
    person_dn = shared_ldap.find_single_object_from_email(person["emailAddress"])
    if person_dn is None:
        # Shouldn't happen because we use a people picker
        shared_sd.post_comment(
            "Unable to find this person in LDAP.",
            True
        )
        shared_sd.resolve_ticket(resolution_state="Declined")
        return

    # Add the name to the summary if we haven't already
    summary = shared_sd.get_field(ticket_data, "summary")
    if summary is not None:
        name = person["displayName"]
        if not summary.endswith(name):
            shared_sd.set_summary(f"{summary}: {name}")

    # Is this person changing team? Has a new manager been provided?
    cf_engineering_team = custom_fields.get("Engineering Team")
    cf_reports_to = custom_fields.get("Reports To")
    new_department = shared_sd.get_field(ticket_data, cf_engineering_team)
    reports_to = shared_sd.get_field(ticket_data, cf_reports_to)
    if reports_to is not None and "emailAddress" not in reports_to:
        reports_to = shared_sd.find_account_from_id(reports_to["accountId"])
    if new_department is not None and reports_to is None:
        shared_sd.post_comment(
            "WARNING! You are changing the department/team for this "
            "person but you have not provided a new manager. Please "
            "note that if the person will have a new manager as a "
            "result of changing department/team, you will need to [create a separate "
            "request|https://servicedesk.linaro.org/servicedesk/customer/"
            "portal/13/create/233] as you cannot edit the information "
            "provided in this ticket.",
            True
        )

    # If a new manager has been provided, add them as a request participant
    new_mgr = None
    if reports_to is not None:
        new_mgr = reports_to["emailAddress"]
        # ... but only if they aren't the person who raised the ticket. If
        # they raised the ticket, the current manager will automatically
        # be added (to approve the ticket).
        if new_mgr != shared.globals.REPORTER:
            shared_sd.add_request_participant(new_mgr)
            shared_sd.post_comment(
                "Adding %s for visibility of this request as the proposed "
                "new manager." % new_mgr,
                True
            )

    # Create an internal comment for HR that specifies all of the bits that
    # need to be done.
    post_hr_guidance(new_department, reports_to, new_mgr, ticket_data)
    # Get their manager
    mgr_email = shared_ldap.get_manager_from_dn(person_dn)
    if mgr_email is None:
        # Fall back to getting Diane to approve the ticket
        mgr_email = "diane.cheshire@linaro.org"
        shared_sd.post_comment(
            "Cannot find a manager for %s, defaulting to Diane." % person_dn,
            False
        )
    # Get their Exec
    exec_email = linaro_shared.get_exec_from_dn(person_dn)
    # This can fail if an intermediate manager is leaving Linaro, in
    # which case find the Exec for the proposed new manager.
    if exec_email is None and new_mgr is not None:
        new_mgr_dn = shared_ldap.find_single_object_from_email(new_mgr)
        exec_email = linaro_shared.get_exec_from_dn(new_mgr_dn)
    if exec_email is not None:
        cf_approvers = custom_fields.get("Executive Approvers")
        shared_sd.assign_approvers([exec_email], cf_approvers)
    else:
        shared_sd.post_comment(
            "Cannot find an exec for %s"
            % person_dn, False
        )
    # If the ticket wasn't created by the manager, get the manager to approve
    # it.
    post_approval_message(mgr_email, exec_email, person)


def post_approval_message(mgr_email, exec_email, person):
    """ Move to next step in the approval process. """
    if mgr_email not in (shared.globals.REPORTER, exec_email):
        shared_sd.post_comment(
            "As you are not the manager for %s, %s will be asked to "
            "approve or decline your request." % (person["displayName"], mgr_email),
            True
        )
        if exec_email is not None:
            shared_sd.post_comment(
                "If that approval is given, %s will then be asked to approve "
                "or decline your request." % exec_email,
                True
            )
        cf_approvers = custom_fields.get("Approvers")
        shared_sd.assign_approvers([mgr_email], cf_approvers)
        shared_sd.transition_request_to("Needs Approval")
    else:
        if exec_email is not None:
            shared_sd.post_comment(
                "%s will be asked to approve or decline your "
                "request." % exec_email,
                True
            )
        shared_sd.transition_request_to("Executive Approval")


def post_hr_guidance(new_department, reports_to, new_mgr, ticket_data):
    """ Post a private comment making it clear what HR need to do. """
    comment = ""
    if new_department is not None:
        comment += (
            "* Change department/team to %s\r\n" %
            new_department["value"]
        )
    if reports_to is not None:
        comment += (
            "* Change manager to %s\r\n" %
            new_mgr
        )
    cf_new_job_title = custom_fields.get("New job title")
    new_job_title = shared_sd.get_field(ticket_data, cf_new_job_title)
    if new_job_title is not None:
        comment += (
            "* Change job title to %s\r\n" %
            new_job_title
        )
    if comment != "":
        shared_sd.post_comment(
            "HR: here is a summary of the changes to be made:\r\n%s" % comment,
            False
        )
