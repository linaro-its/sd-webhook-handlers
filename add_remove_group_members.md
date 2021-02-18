# Modify Group Membership handler

## Introduction

This handler processes requests to add members to or remove members from an existing group.

## Form fields

The following fields are used:

* Group Email address
  * Text Field (single line)
* Group member email addresses
  * Tet field (multi-line)
* Added / Removed
  * Radio Buttons

The summary field is hidden.

## Behaviour

The handler operates on the `CREATE`, `COMMENT` and `TRANSITION` events.

The `CREATE` event processes the request, triggering the approval workflow if the requester is not one of the owners of the group.

The `COMMENT` event handles both public and private comments. Public comments use `add` and `remove` comments to make follow-up changes to the owners of the group. Private comments allow a `retry` comment to get the automation to parse the account list again. This is used if the automation hits a problem that can be fixed and then the list reprocessed rather than submitting a new ticket.

The `TRANSITION` event is used to process the actual changes based on when the state of the ticket changes to `In Progress`. Note that the transitions are resolved by name and so must match the names used in the workflow.
