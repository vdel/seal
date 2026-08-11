# adding a service to the project is declaring it, and nothing else

A service is added by declaring it where the project already lists what it
is made of. There is no second registry, and no place a new service can be
half-added.

The failure this rules out is quiet: a service that exists on disk and in
somebody's head, but is missing from one of the two places it had to be
named, so it never comes up and nothing says why. The project looks
complete and behaves as though the service were not there.

One list means the list cannot disagree with itself.

## Worth covering

- Declaring a service is enough for it to be built, deployed and waited
  for.
- Nothing else in the project has to learn about it.
- Removing the declaration removes the service, with nothing left behind
  claiming it exists.

## What this does not claim

What a service *is* -- its language, its image, whether it has tests, what
it depends on. Those are the project's, and the declaration is where the
project says them.

That a mis-declared service is caught. This is about there being one place
to declare it, not about that place being validated.
