# the same promises can be checked against the shape that actually ships

A project can have its promises checked against more than one manifest
shape -- the one developers work in, and the one a real environment runs.

A gate that only ever verifies the shape developers work in says less than
it looks like it says. The differences between the two are exactly the
things that hide: a development server replaced by a built bundle behind a
proxy, a container that only one shape has, static files served a
different way. Each is invisible to a suite that never deploys the second.

The same promises, against both. Not a second set written for the other
shape -- the promises are the application's, and if one holds in
development and not in what ships, that is the finding.

## Worth covering

- The promises run against a shape other than the usual one.
- The verdicts are reported per shape, so a reader can tell which went red.
- The promises are the same ones, not a variant set.

## What this does not claim

How much a second shape adds. That depends entirely on what it changes --
one adjusting replicas adds nothing; one rearranging how an application is
served adds a great deal. The axis is available and the project decides.

Anything about deploying to a real environment.
