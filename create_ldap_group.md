# Create Group handler

## Introduction

This handler is used to create a new LDAP group (security + mailing) plus triggering the sync to Google.

## Form fields

The following fields are used:

* Group Name
  * Text field (single line)
* Group Description
  * Text field (single line)
* Group Owners
  * Text field (multi line)
* Group Email Address
  * Text field (single line)

The summary field is hidden.

## Behaviour

The handler operates on the `CREATE` and `COMMENT` events.

The `CREATE` event processes the request.

The `COMMENT` event is primarily used to allow a `retry` comment to get the automation to parse the account list again. This is used if the automation hits a problem that can be fixed and then the list reprocessed rather than submitting a new ticket.
