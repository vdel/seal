# an item I add is still on the list after a reload

Adding something is the one thing this list is for, and a list that forgets
it the moment the page is loaded again is broken however good the rest of
it looks.

Reload means loading the application again against the same running
environment -- not restarting anything, and not putting the data back to
its baseline. What was added before the reload is there after it, with the
text it was given.

This promise deliberately says nothing about *where* on the list a new item
appears, only that it's on it. Nor does it claim anything about two people
adding at once; a single person adding one thing is the whole of it.
