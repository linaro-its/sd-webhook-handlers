# About this repository
This repository is a collection of request type handlers used by Linaro in conjunction with the [Jira Service Desk Webhook Framework](https://github.com/linaro-its/sd-webhook-framework).

Each handler is unlikely to be usable outside of Linaro without changes but they serve to show how the underlying framework can be used.

Since the ID number assigned to a given request type will vary on each installation of Service Desk, the handlers in this repository are named after their function.

VS Code is used at Linaro for developing both the framework and the handlers. To simplify testing and development, this repo contains configuration to tell VS Code and pylint where to find the framework files so that the linter and the Python Language Server don't complain unless there are valid problems discovered.
