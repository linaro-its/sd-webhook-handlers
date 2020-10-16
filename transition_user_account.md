# Transition User Account handler

## Introduction

This handler is used to transition accounts between Linaro and Member states.

## Form fields

There is a single, multi-line text field which the automation parses.

The summary field is hidden.

## Behaviour

The handler operates on the `CREATE` and `COMMENT` events.

The `CREATE` event steps through each of the named accounts, deciding which transition direction the account has to take. Regardless of the direction, the account is cleaned of certain attributes and group membership.

The `COMMENT` event is primarily used to allow a `retry` comment to get the automation to parse the account list again. This is used if the automation hits a problem that can be fixed and then the list reprocessed rather than submitting a new ticket.
