# Hackbox Access Request handler

## Introduction

This handler is used when processing requests from staff for SSH access to the Hackbox2 service.

## Form fields

There are no form fields for this request.

## Behaviour

This handler supports both the `CREATE` and `COMMENT` events.

When an issue is created, it applies the appropriate business logic and, if all the checks pass, the requester gets added to the LDAP group that controls SSH access for the service.

The purpose of the `COMMENT` handler is to demonstrate a useful way to allow IT support staff to tell the handler to try the request again. This is useful because if something goes wrong and IT support needs to fix something, telling the handler to try again avoids having to get the original requestor to resubmit.
