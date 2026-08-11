# ticking an item off updates how many are left

The list says how many of its items are still to do. Marking one done takes
it out of that number, and marking it undone again puts it back -- so the
count always describes the list as it is now, not as it was when the page
opened.

The point of the promise is that the two agree. A count that's right only
until you touch something is what this is here to catch, which is why it
covers ticking an item *back* on as well as off: a count that only ever
counts down looks correct through the obvious test.

It says nothing about how the done items themselves are shown -- struck
through, greyed out, moved, left where they are. That's presentation, and
it can change without this promise changing.
