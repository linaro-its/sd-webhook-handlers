""" Triggered by a change assignee/Member engineer/Affiliate ticket """

import shared.custom_fields as custom_fields
import shared.globals
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
        print("change_engineer processing retry keyword & triggering create function")
        create(ticket_data)


def create(ticket_data):
    """ Trigger the approval or transition code. """
    linaro_shared.check_approval_assignee_member_engineer(ticket_data)
    # Is the engineer changing team? Has a new manager been provided?
    cf_engineering_team = custom_fields.get("Engineering Team")
    cf_reports_to = custom_fields.get("Reports To")
    new_department = shared_sd.get_field(ticket_data, cf_engineering_team)
    if new_department is not None:
        new_department = new_department["value"]
    reports_to = shared_sd.get_field(ticket_data, cf_reports_to)
    if reports_to is not None and "emailAddress" not in reports_to:
        reports_to = shared_sd.find_account_from_id(reports_to["accountId"])
    if new_department is not None and reports_to is None:
        shared_sd.post_comment(
            "WARNING! You are changing the engineering team for this "
            "engineer but you have not provided a new manager. Please "
            "note that if the engineer will have a new manager as a "
            "result of changing team, you will need to [create a separate "
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
                f"Adding {new_mgr} for visibility of this request as the proposed "
                "new manager.",
                True
            )
    # Create an internal comment for HR that specifies all of the bits that
    # need to be done.
    comment = ""
    cf_new_engineer_type = custom_fields.get("Engineer Type")
    new_engineer_type = shared_sd.get_field(ticket_data, cf_new_engineer_type)
    if new_engineer_type is not None:
        new_engineer_type = new_engineer_type["value"]
        comment += (
            f"* Change engineer type to {new_engineer_type}\r\n"
        )
    if new_department is not None:
        comment += (
            f"* Change department/team to {new_department}\r\n"
        )
    if new_mgr is not None:
        comment += (
            f"* Change manager to {new_mgr}\r\n"
        )
    cf_new_job_title = custom_fields.get("New job title")
    new_job_title = shared_sd.get_field(ticket_data, cf_new_job_title)
    if new_job_title is not None:
        comment += (
            f"* Change job title to {new_job_title}\r\n"
        )
    if comment != "":
        shared_sd.post_comment(
            f"HR: here is a summary of the changes to be made:\r\n{comment}",
            False
        )
