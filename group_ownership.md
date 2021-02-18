# Group Ownership handler

## Introduction

This handler is used to display and change the owners of a group.

## Form fields

The following fields are used:

* Group Email Address
  * Text Field (single line)
* Group Owners
  * Text Field (multi-line)
  * Not required
* Added / Removed
  * Radio Buttons
  * Not required

The summary field is hidden.

Although there is a group picker type, it is not currently possible to use this on a Request Type. This is why the requester has to provide the email address of the group.

## Behaviour

The handler operates on the `CREATE`, `COMMENT` and `TRANSITION` events.

The `CREATE` event processes the request. If "Added / Removed" is left at None, the script lists the current owners, otherwise the script acts on the request, adding or removing as specified.

The `COMMENT` event handles both public and private comments. Public comments use `add` and `remove` comments to make follow-up changes to the owners of the group. Private comments allow a `retry` comment to get the automation to parse the account list again. This is used if the automation hits a problem that can be fixed and then the list reprocessed rather than submitting a new ticket.

The `TRANSITION` event is used to process the actual changes based on when the state of the ticket changes to `In Progress`. Note that the transitions are resolved by name and so must match the names used in the workflow.
