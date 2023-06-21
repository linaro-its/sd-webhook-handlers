""" This code is triggered when a Hold Engineer ticket is created """

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
        print("hold_engineer processing retry keyword & triggering create function")
        create(ticket_data)


def create(ticket_data):
    linaro_shared.check_approval_assignee_member_engineer(ticket_data)
