# my manifests name the objects that carry a service's values

The project's own manifests declare which objects a service's values land
in, and Seal fills the ones they mark. It supplies the contents and
nothing else -- no object it invented, no name it chose.

A library that named the objects itself would be choosing Kubernetes names
inside a project's manifests, and the shape it chose would be one no real
environment uses: one object per service, where a real environment
assembles a pod's environment from several, split by who owns them and how
each is filled. The two shapes are then never exercised together, and the
difference surfaces at the worst moment.

Marking is opt-in. A project that marks nothing gets nothing filled, and
everything else still works.

## Worth covering

- An object the project declares and marks is filled; one it does not mark
  is left alone.
- The names and grouping are the project's, and a session assembles a
  pod's environment the same way the shape that ships does.
- A project that marks nothing is not broken by that.

## What this does not claim

Which objects a project *should* use, or how many.

That the manifests are otherwise valid. This is about who names the
objects, not about them being right.
