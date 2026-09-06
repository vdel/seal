"""Discover a project's services by asking Tilt itself, instead of a
separate config file: `seal up`/`seal ci` need to know every service's
name and directory to generate its Kubernetes Secret (see seal.py) before
`tilt up`/`tilt ci` runs, so they run `tilt alpha tiltfile-result` against
the project's own root Tiltfile first and read the result back out.

`tilt alpha tiltfile-result` fully evaluates the Tiltfile (the same
`include()`s, `docker_build()` calls, etc. that `tilt up` would run) without
needing a live cluster, and prints the resulting model as JSON. Every
`seal_service()`/`docker_build()` call anywhere in the project shows
up as one `ImageTargets[]` entry per manifest, with `selector` (the image
ref -- always that service's own `service_name`, since
seal_service(service_name, ...) passes it straight through) and a
context directory, already an absolute path -- the service's own directory,
for every service in this repo's convention of `context='.'`. *Where* that
directory lives in `BuildDetails` depends on which build function actually
ran: Tilt's native `docker_build()` (local dev, and CI when a service opts
out of the buildx-cache path -- see `seal_service()`'s `use_cache`)
puts it under `context`; `cached_docker_build()`'s `custom_build()` (CI's
default, SEAL_BUILDX_CACHE=1 -- see build.Tiltfile) puts it under `dir`
instead, with no `context` key at all -- missing this silently discovers
zero services under SEAL_BUILDX_CACHE=1, so no service's Secret ever gets
generated.

Run with IS_BUILD_OR_TEST=1, which a project's own Tiltfile may branch on
to skip anything a discovery pass has no cluster for: this evaluates the
Tiltfile before a session exists, so whatever the run would eventually
deploy is not there yet.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from seal.credentials import SealError


def _tiltfile_config_args(tilt_args: list[str]) -> list[str]:
    """`tilt_args` is whatever `seal up`/`seal ci` forwarded verbatim from
    the command line: optionally some `tilt up`/`tilt ci`-level flags (e.g.
    `--namespace`), then a '--', then the Tiltfile's own config args (e.g.
    `--k8s_overlay=stag`) that `config.parse()` (tilt/seal/config.Tiltfile)
    reads via Tilt's own '--'-forwarding convention, same as `tilt up -- ...`.
    `tilt alpha tiltfile-result` doesn't accept `tilt up`/`tilt ci`-level
    flags like `--namespace` ("unknown flag: --namespace"), so those must be
    dropped -- but the '--' itself has to stay: without it, cobra parses
    `--k8s_overlay=...` as a top-level flag of `tiltfile-result` itself
    instead of a Tiltfile config arg, and fails the same way
    ("unknown flag: --build_type"). So: keep the '--' and everything
    after it, drop everything before it. Both shapes are real -- a deploy
    pipeline passes `--namespace "$NS" -- --k8s_overlay=...
    --allowed_k8s_contexts=...`, while actions/ci passes nothing before
    the '--' at all -- so exercise both when touching this."""
    if "--" in tilt_args:
        return tilt_args[tilt_args.index("--") :]
    return []


def discover_services(seal_root: Path, tilt_args: list[str]) -> list[tuple[str, Path]]:
    """Every (service_name, service_dir) pair `seal_service()` builds
    an image for, anywhere in the project's root Tiltfile -- deduplicated,
    in first-seen order (a service can show up more than once, e.g. a
    Celery worker built from the same image as its web service)."""
    tilt = shutil.which("tilt")
    if tilt is None:
        raise SealError("Error: 'tilt' not found on PATH. See https://tilt.dev for install instructions.")

    env = os.environ.copy()
    env["IS_BUILD_OR_TEST"] = "1"
    result = subprocess.run(
        [tilt, "alpha", "tiltfile-result", "--file", "Tiltfile", *_tiltfile_config_args(tilt_args)],
        cwd=seal_root,
        capture_output=True,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise SealError(
            f"Error: 'tilt alpha tiltfile-result' failed while discovering services:\n{result.stderr}"
        )

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SealError(f"Error: could not parse 'tilt alpha tiltfile-result' output: {error}")

    services: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for manifest in data.get("Manifests") or []:
        for image_target in manifest.get("ImageTargets") or []:
            service_name = image_target.get("selector")
            build_details = image_target.get("BuildDetails") or {}
            # docker_build() reports it as 'context'; custom_build() (see the
            # module docstring above) as 'dir' instead.
            context = build_details.get("context") or build_details.get("dir")
            if not service_name or not context or service_name in seen:
                continue
            seen.add(service_name)
            services.append((service_name, Path(context)))
    return services
