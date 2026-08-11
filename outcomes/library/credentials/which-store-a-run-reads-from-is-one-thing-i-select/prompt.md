# which store a run reads from is one thing I select

A run selects the credentials it resolves against, on an input of its own,
and that selection is the whole of what decides which store a reference is
read from. The same declaration serves every environment.

Without it, a project ends up with one declaration per environment --
three files saying the same thing with different values, which is three
places for a key to be added to two of them.

It is deliberately its own input rather than something inferred from which
shape is being deployed. The two coincide for a real deployment and come
apart everywhere else: verifying the shape that ships, on a throwaway
cluster, should not mean reaching for the store that shape uses.

## Worth covering

- One declaration resolves differently depending only on what the run
  selected.
- Selecting a different shape does not change which store is read.

## What this does not claim

Which store any environment should use, or what the selections should be
called. Seal substitutes what the project said and validates nothing
about it.

That a mis-selected store fails helpfully.
