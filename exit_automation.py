"""Handle the automated processes involved in exiting someone."""

# The HR automation script creates this ticket when someone needs to be exited. The
# reporter is set to be the manager of the person exiting. The ticket summary
# is set to the email address of the person being exited.

import requests
import json
# from shared import shared_vault
from shared import shared_ssmparameterstore as shared_ssm

CAPABILITIES = [
    "CREATE",
    "JIRAHOOK"
]

def create(ticket_data):
    """ Ticket has been created """
    # Called when the ticket is first created and when the ticket transitions
    # to Phase 3. The latter is handled by the "Exit Leaver - 6 months" SLA.
    #
    # Fire the GitHub Action with the additional information required.
    fire_gitlab_workflow(ticket_data)


def fire_gitlab_workflow(ticket_data):
    """ Fire the GitLab Pipeline """
    issue_self = ticket_data["self"]
    #
    # Work around a bug where the "self" link is broken
    parts = issue_self.split("/")
    if parts[-2] != "issue":
        # We're missing part of the URL
        parts.append(parts[-1])
        parts[-2] = "issue"
        issue_self = "/".join(parts)
    print(f'Triggering workflow for {issue_self}')
    # auth_token = shared_vault.get_secret("secret/misc/gitlab-exit-automation")
    auth_token = shared_ssm.get_secret("/secret/misc/gitlab-exit-automation")
    url = "https://gitlab.com/api/v4/projects/68959654/trigger/pipeline"
    payload = {
        "token": auth_token,
        "ref": "master",
        "variables[SD_REFERENCE]": issue_self,
        "variables[WORKFLOW_NAME]": "Exit automation: " + ticket_data["key"]
    }

    result = requests.post(url, data=payload, timeout=60)
    print(
        "fire_github_workflow: got "
        f"{result.status_code} after triggering workflow for {issue_self}")


def jira_hook(ticket_data, changelog):
    """ Called when the Jira webhook fires """
    # Called whenever the ticket is updated. There are two reasons we want
    # to trigger the GitHub Action:
    #
    # 1. The ticket is in Phase 2 and has been assigned to somebody.
    # 2. The ticket is in Phase 2 and the custom field has been updated.
    if is_valid_assignment(ticket_data, changelog) or is_checkfield_update(ticket_data, changelog):
        fire_gitlab_workflow(ticket_data)


def is_valid_assignment(ticket_data, changelog):
    """ Is this a valid user assignment? """
    assignee = who_is_ticket_assigned_to(changelog)
    if assignee is not None and assignee != "it services sd bot":
        # Make sure we're in Phase 2
        return in_phase_two(ticket_data)
    return False


def who_is_ticket_assigned_to(changelog):
    """ Who was this ticket assigned to? """
    if "items" in changelog:
        items = changelog["items"]
        for item in items:
            if item["field"] == "assignee":
                return item["to"]
    return None


def is_checkfield_update(ticket_data, changelog):
    """ Is this a checkfield update? """
    if "items" in changelog:
        items = changelog["items"]
        for item in items:
            if item["field"] == "Checklist Text":
                return in_phase_two(ticket_data)
    return False


def in_phase_two(ticket_data):
    """ Is the ticket in Phase 2? """
    return ticket_data["fields"]["status"]["name"] == "Phase 2"
