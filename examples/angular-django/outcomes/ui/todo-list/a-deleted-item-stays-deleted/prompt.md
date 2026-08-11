# deleting an item takes it off the list for good

An item I delete is gone from the list straight away, and it's still gone
when the application is loaded again. Deleting one item leaves every other
item alone.

The second half is the part worth having: something that only disappears
from the screen, and comes back on the next load, reads as working right up
until somebody reloads. The third is what stops a delete that's too eager
from passing -- one item goes, the rest stay, with the text and done-state
they had.

Whether a deleted item could be recovered from somewhere is not something
this promises either way. From the list's point of view it's gone.
