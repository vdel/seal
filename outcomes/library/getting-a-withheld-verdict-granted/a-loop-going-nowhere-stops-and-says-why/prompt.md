# a loop that isn't getting anywhere stops, and says why

A loop that has stopped converging stops, with a reason: a promise fixed
and broken again, or a run past the limit the project set.

Coupled failures do not resolve in order. Fixing one promise can break
another, and fixing that one can re-break the first, and left alone that
has no guaranteed end. A cap alone would catch it, eventually, having
spent everything up to the cap.

Saying why is what makes stopping useful. "It stopped" tells whoever picks
it up nothing; the sequence of what was fixed and what broke tells them
whether two promises are in conflict, or whether one round simply needed
more than it got.

Where the limit sits is the project's -- one that has measured its own
loop should not be arguing with a number chosen before anything had.

## Worth covering

- A loop ping-ponging between promises is stopped for that, not by
  exhausting a cap.
- A chain where each round breaks something new is caught by the cap,
  which is what the cap is for.
- What stopped it, and the sequence that led there, are reported.

## What this does not claim

That the reason is a diagnosis. It is evidence handed to somebody with
fresh context, not a conclusion about which promise is at fault.

That the limits are right for any project. They are a backstop, and a
project that has measured its own replaces them.
