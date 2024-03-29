""" This code is triggered when adding a new engineer """

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
        print("add_engineer processing retry keyword & triggering create function")
        create(ticket_data)

def create(ticket_data):
    """ Triggered when the ticket is created """
    cf_engineering_team = custom_fields.get("Engineering Team")
    team = shared_sd.get_field(ticket_data, cf_engineering_team)
    director = linaro_shared.get_director(team["value"])
    if director is None:
        shared_sd.post_comment(
            f"[~philip.colmer@linaro.org] Couldn't find the director for team '{team}'",
            False
        )
    elif director != shared.globals.REPORTER:
        shared_sd.add_request_participant(director)

    # Build the name from the fields
    cf_firstname = custom_fields.get("First Name (migrated)")
    cf_familyname = custom_fields.get("Family Name")
    firstname = shared_sd.get_field(ticket_data, cf_firstname)
    familyname = shared_sd.get_field(ticket_data, cf_familyname)
    if firstname is None or firstname == "":
        name = familyname
    else:
        name = f"{firstname} {familyname}"
    # Add the name to the summary if we haven't already
    summary = shared_sd.get_field(ticket_data, "summary")
    if not summary.endswith(name):
        shared_sd.set_summary(f"{summary}: {name}")

    # If the ticket wasn't raised by the proposed manager, get them
    # to approve it.
    cf_approvers = custom_fields.get("Approvers")
    cf_manager = custom_fields.get("Employee/Contractor")
    manager_anonymised = shared_sd.get_field(ticket_data, cf_manager)
    # That gets us the manager's account ID so now get their full details
    # so that we have, and can compare, the email address.
    print(f"Result of retrieving the proposed manager: {manager_anonymised}")
    manager = shared_sd.find_account_from_id(manager_anonymised["accountId"])
    if manager is not None and "emailAddress" in manager:
        mgr_email = manager["emailAddress"]
        if mgr_email != shared.globals.REPORTER:
            shared_sd.post_comment(
                "As you are not the proposed manager, they will be asked to "
                "approve or decline your request.",
                True
            )
            shared_sd.assign_approvers([mgr_email], cf_approvers)
            shared_sd.transition_request_to("Needs approval")
        else:
            shared_sd.transition_request_to("In Progress")
