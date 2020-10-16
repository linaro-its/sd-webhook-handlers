# Group Ownership handler

## Introduction

This handler is used to request changes for an existing employee or contractor.

## Form fields

The following fields are used:

* Employee/Contractor
  * User picker with filtering by `contractors` and `employees` groups.
* New job title
  * Text field (single line)
* Engineering Team
  * Select list (single choice)
* Reports To
  * User picker with filtering by `everyone` group.
* Due Date
* Description

The summary field is hidden.

## Behaviour

The handler operates on the `CREATE` and `COMMENT` events.

The `CREATE` event processes the request.

The `COMMENT` event is primarily used to allow a `retry` comment to get the automation to parse the account list again. This is used if the automation hits a problem that can be fixed and then the list reprocessed rather than submitting a new ticket.
