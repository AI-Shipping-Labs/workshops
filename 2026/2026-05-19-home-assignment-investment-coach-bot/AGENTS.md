# Agent Instructions

When creating or editing tests in this repository, follow the guidelines in:

- [docs/test-guidelines.md](docs/test-guidelines.md)

In particular:

- test observable behavior, not prompt wording.
- prefer async real-model agent tests when checking agent behavior.
- keep test blocks easy to scan: create agent, define prompt, run agent, extract output, assert behavior.
- don't use canned model outputs for behavior tests.
- don't add prompt-string assertions.
