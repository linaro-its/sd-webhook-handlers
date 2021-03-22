""" Handler for the request to list the groups owned by the requester """

import shared.globals
import shared.shared_ldap as shared_ldap
import shared.shared_sd as shared_sd

CAPABILITIES = [
    "CREATE"
]

def group_name(ldap_obj):
    """ Return the display name or cn """
    if ldap_obj.displayName.value is None:
        return ldap_obj.cn.value
    return ldap_obj.displayName.value


def create(ticket_data):
    """ Triggered when the issue is created """
    shared_sd.assign_issue_to(shared.globals.CONFIGURATION["bot_name"])
    # Keep the linter happy
    _ = ticket_data
    # Need to get all of the groups, with their owners
    all_groups = shared_ldap.find_matching_objects(
        "(objectClass=groupOfUniqueNames)",
        ["owner", "displayName", "cn", "uniqueMember"]
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

    owned_groups = sorted(owned_groups, key=group_name)
    response = (
        "Below are the groups you can manage.\n\n"
        "There are automated Service Desk requests for [changing the "
        "membership of a group|https://servicedesk.linaro.org/servicedesk"
        "/customer/portal/3/create/121] and [changing the owners of a "
        "group|https://servicedesk.linaro.org/servicedesk/customer/portal"
        "/3/create/129].\n\n"
    )
    for group in owned_groups:
        empty = check_if_group_has_members(group)
        response += "* %s%s\n" % (group_name(group), empty)
    shared_sd.post_comment(response, True)
    shared_sd.resolve_ticket()

def check_if_group_has_members(group):
    """ See if this group has any members """
    memb = group.uniqueMember.values
    # It can't be an empty list so an empty group should
    # just be a single empty member.
    if memb == ['']:
        return " (empty)"
    return ""
