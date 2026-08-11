# CI never has to learn my application's variable names

A project's CI points Seal at a directory and passes whatever its
password manager needs to authenticate. It never enumerates the
application's own keys.

That is what makes the CI file boilerplate rather than something to
maintain. The alternative is a workflow that lists every variable a
service needs, which has to be edited every time a service needs another
one -- in a file most people editing the service never open, and where
forgetting shows up as a container that starts without a setting.

It also means the CI file is copyable. A second project points the same
workflow at itself and changes a path.

## Worth covering

- A project's workflow contains no application variable name, and its
  services still get their values.
- A service that starts needing another key needs no CI change.

## What this does not claim

That CI needs no secret at all. Whatever authenticates against the store
is a credential CI holds -- one, not one per application key.

Anything about which CI system a project uses.
