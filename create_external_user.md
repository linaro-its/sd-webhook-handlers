# Create External User/Contact handler

## Introduction

This handler is used to handle tickets for creating external users or contacts.

## Form fields

The following fields are used:

* First Name
  * Text field (single line)
* Family Name
  * Text field (single line)
* Email Address
  * Text field (single line)
* External Account / Contact
  * Radio buttons

The summary field is hidden.

## Behaviour

The handler operates on the `CREATE` and `COMMENT` events.

The `CREATE` event processes the request.

The `COMMENT` event is primarily used to allow a `retry` comment to get the automation to parse the account list again. This is used if the automation hits a problem that can be fixed and then the list reprocessed rather than submitting a new ticket.
