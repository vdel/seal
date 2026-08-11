# a credential is written down once, in the service that needs it

The service that needs a value declares it, in one file, and that file's
key names are the schema. There is no second list of them anywhere.

A value written down twice is a value that will disagree with itself. The
usual shape of that is a schema beside the declaration -- one file naming
what a service needs and another naming what it gets -- which stays right
until somebody adds a key to one of them.

## Worth covering

- Adding a key means editing one file, and the value reaches the service.
- Nothing else in the project has to be told about it.
- A key the service no longer declares stops reaching it, for the same
  reason.

## What this does not claim

Where the value comes from -- a literal, a store, or the manifests. Those
are the shapes a declaration can take, and this promise is about there
being one declaration whichever it is.

Anything about the value itself.
