""" Handler for the request to list the groups owned by the requester """

import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd


CAPABILITIES = [
    "CREATE"
]


def create(ticket_data):
    """ Triggered when the issue is created """
    # Keep the linter happy
    _ = ticket_data
    # Need to get all of the groups, with their owners
    all_groups = shared_ldap.find_matching_objects(
        "(objectClass=groupOfUniqueNames)",
        ["owner", "displayName"]
    )
    owned_groups = []
    for group in all_groups:
        owners = group.owner.values
        if shared_ldap.reporter_is_group_owner(owners):
            owned_groups.append(group)
    if owned_groups == []:
        shared_sd.post_comment(
            "You do not appear to be the owner of any "
            "groups on Linaro Login.", True
        )
        shared_sd.resolve_ticket()
        return

    owned_groups = sorted(owned_groups, key=lambda x: x.displayName.value)
    response = (
        "Below are the groups you can manage.\n\n"
        "There are automated Service Desk requests for [changing the "
        "membership of a group|https://servicedesk.linaro.org/servicedesk"
        "/customer/portal/3/create/121] and [changing the owners of a "
        "group|https://servicedesk.linaro.org/servicedesk/customer/portal"
        "/3/create/129].\n\n"
    )
    for group in owned_groups:
        response += "* %s\n" % group.displayName.value
    shared_sd.post_comment(response, True)
    shared_sd.resolve_ticket()
