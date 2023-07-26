"""
Because this ticket uses a multi-user picker, there is the possibility that
the users report to different managers. So, if the ticket is submitted by
someone who reports to an Exec, we go straight to Executive Approval,
otherwise we get their manager's approval.
"""

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
        print("bulk_modify_team processing retry keyword & triggering create function")
        create(ticket_data)


def create(ticket_data):
    """ Create event triggered. """
    staff_dn = shared_ldap.find_single_object_from_email(shared.globals.REPORTER)
    # Get the manager of the person who created this ticket.
    mgr_email = shared_ldap.get_manager_from_dn(staff_dn)
    if mgr_email is None:
        # Fall back to getting Diane to approve the ticket
        mgr_email = "diane.cheshire@linaro.org"
    # Get their Exec
    exec_email = linaro_shared.get_exec_from_dn(staff_dn)
    if exec_email is not None:
        cf_exec_approvers = custom_fields.get("Executive Approvers")
        shared_sd.assign_approvers([exec_email], cf_exec_approvers)
    else:
        shared_sd.post_comment(
            "[~philip.colmer@linaro.org] Cannot find an exec for %s"
            % staff_dn, False
        )
    # If the ticket wasn't created by the manager, get the manager to approve
    # it.
    if mgr_email != exec_email:
        shared_sd.post_comment(
            "As you do not report to an Exec, %s will be asked to "
            "approve or decline your request." % mgr_email,
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
