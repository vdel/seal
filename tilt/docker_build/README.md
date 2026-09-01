# docker_build

Builds via a GitHub-Actions-cached `buildx` build, for use under CI.

```python
cached_docker_build(
    ref,
    context='.',
    dockerfile='Dockerfile',
    target=build_type,
    live_update=[...],
)
```

Unlike Tilt's built-in `docker_build()`, `cached_docker_build()` always
takes the `buildx` path -- it doesn't check `SEAL_BUILDX_CACHE`
itself. Deciding when that's actually wanted (only under a CI workflow that
sets `SEAL_BUILDX_CACHE` -- `.github/workflows/seal-ci.yml` at
the repo root does, and so does a deploy pipeline; never local `tilt up`) is
the caller's job -- see `/tilt/seal/README.md`'s `build.Tiltfile`
section for how `seal_service()` makes that decision for you. It
`load()`s this file by relative path from its sibling directory, so a project
never names it.

Any other `docker_build()` argument (`build_args`, `extra_tag`, `ignore`,
`only`, `network`, `ssh`, `secret`, `platform`, ...) fails loudly if passed
here -- the `buildx` command above doesn't understand any of them. Use
Tilt's native `docker_build()` instead when you need one of those.

## SEAL_IMAGE_TAG / SEAL_BUILD_ID

When `SEAL_IMAGE_TAG` is set, `cached_docker_build()` also explicitly
re-tags and pushes the image as
`ref:$SEAL_BUILD_ID-$SEAL_IMAGE_TAG` (or bare
`ref:$SEAL_IMAGE_TAG` if `SEAL_BUILD_ID` isn't also set), in
addition to whatever Tilt itself pushes it as. Only a pipeline actually
publishing a build sets these (`SEAL_IMAGE_TAG` to the git SHA being
deployed, `SEAL_BUILD_ID` to a zero-padded, monotonically increasing
build identifier) -- local `tilt up` and this repo's own CI never do.

This exists because Tilt always re-tags whatever it pushes under its own
content-digest-derived tag, per Tilt's own source
(`internal/build/custom_builder.go`) -- even `custom_build()`'s own `tag`
argument only controls the *local* build target, not what actually reaches
the registry. Nothing outside Tilt can discover or reason about that opaque
tag, so it can't be what a release-tracking tool subscribes to for new
builds. `SEAL_IMAGE_TAG` is the one place a real, externally-stable
identifier for a given build gets into the registry at all.

`SEAL_BUILD_ID`'s prefix makes plain lexicographic tag comparison a
correct recency comparison. A tool selecting the newest image typically
sorts candidate tags by each image's own embedded build timestamp, but a
fully build-cache-hit rebuild (nothing the image actually depends on
changed) reproduces an earlier build's timestamp exactly -- such ties break
on a plain tag string comparison, which only tracks real recency because of
this prefix.

Most service Tiltfiles never call this directly -- `ext://seal`'s
`seal_service()` (see `/tilt/seal/README.md`) calls it for you,
only when needed, as part of the usual build/secret/syncback sequence (pass
`use_cache=False` to always use Tilt's native `docker_build()` instead).
Call `cached_docker_build()` here directly only when you need the
GitHub-Actions-cache behavior outside that sequence -- and check
`SEAL_BUILDX_CACHE` yourself first if you want the same "only under
CI" behavior `seal_service()` gives you.
