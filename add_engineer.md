# Add Engineer handler

## Introduction

This handler processes requests to add a new engineer, ensuring that the team's directory is added when the ticket is created.

## Behaviour

The handler operates on the `CREATE` and `COMMENT` events.

The `CREATE` event processes the request, adding the director as a request participant if they are not the reporter, updating the ticket summary with the engineer's name and triggering approval by the proposed manager if they weren't the reporter.

The `COMMENT` event only allows private comments, and allows a `retry` comment to process the create automation again.
