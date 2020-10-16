# Developer Cloud Registration handler

## Introduction

This handler is used when processing registration requests for Linaro's Developer Cloud service.

## Form fields

The associated form has the following fields:

* First name (required)
* Family name (required)
* Company (required)
* Job title (required)
* Project website
* Intended usage (required)
* Project size (required)
* Special request details
* Number of public IP addresses (required)

In addition, the summary and approvers fields are hidden.

## Behaviour

The handler only operates on the `TRANSITION` event and that is triggered when the issue is approved.

When the request is approved, the handler creates a new LDAP account if one is required, adds the account to the desired LDAP group, sends a welcome email to the new registrant and, finally, creates a new SD ticket under a different project to initiate the process of setting up an OpenStack project.
