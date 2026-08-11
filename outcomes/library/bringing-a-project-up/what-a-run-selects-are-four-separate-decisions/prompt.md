# which shape I deploy, which images I build, whether images are published and which credentials resolve are four separate decisions

Four things a run selects, each stated on its own: the manifest shape, the
kind of image, whether images are published, and which credentials
resolve.

They coincide for a real deployment and come apart everywhere else. Folded
into one input, the useful combinations become unreachable: verifying the
shape that ships means either building images that carry no test suite, or
turning on publishing because "not the development one" was the only
available signal for it. A project ends up unable to ask the question it
actually has.

The cost of separating them is four inputs to state instead of one. The
cost of not separating them is a gate that can only check the shape
developers work in.

## Worth covering

- Selecting a different shape does not change the images, start
  publishing, or change which store is read.
- Building the kind of image a real environment runs does not stop the
  promises being checked.
- Each is stated rather than inferred from any other.

## What this does not claim

Which combinations are sensible. Some pairs make no sense together; what
is promised is that the project can express what it means, not that
Seal has an opinion about it.

Anything about deploying to a real environment.
