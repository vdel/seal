# a secret reaches the running container without being committed

A value a service needs arrives in the running container, and the
repository never holds it.

What is committed is the *reference*: which item this service needs. What
resolves it is whatever the project declared. So a checkout is safe to
clone, a fork is safe to make, and history is safe to keep -- and none of
that depends on anybody having remembered to keep a secret out.

The alternative shapes are all worse in the same way: a value pasted into
a manifest, a file everybody is told not to commit, an environment somebody
sets up by hand. Each works until one person forgets.

## Worth covering

- A service reads a value at run time that appears nowhere in the
  repository.
- The reference to it does appear, and is readable -- that is the schema.

## What this does not claim

That the store is secure, or that access to it is controlled. That is the
store's job and the project's.

That a project cannot commit a secret anyway. This promises a path that
does not require it, not that no other path exists.
