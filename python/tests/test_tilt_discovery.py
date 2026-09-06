"""Unit tests for discover_services()'s `tilt alpha tiltfile-result` JSON
parsing -- specifically, that it finds a service's build context regardless
of which build function actually built it.

`cached_docker_build()`'s `custom_build()` (SEAL_BUILDX_CACHE=1, the CI
action's default -- see build.Tiltfile) reports the context
directory under `BuildDetails.dir`, not `BuildDetails.context` like Tilt's
native `docker_build()` does (see tilt_discovery.py's module docstring).
Reading only `context` silently discovers zero services under
SEAL_BUILDX_CACHE=1, and an empty discovery result is not a failure by
itself -- so a caller gets a clean run that did nothing, with no error at
the seal layer at all. That is what these tests hold shut.

Nothing in the package calls discover_services() today: resolving a
service's credentials walks `services/<name>/.env` directly (see
credentials.py), which needs no Tilt evaluation. The function and its
build-details handling are covered here so that a caller reaching for it
again gets the version that reads both keys.
"""

import json
from pathlib import Path

from seal.tilt_discovery import _tiltfile_config_args, discover_services


def _tiltfile_result(build_details: dict) -> str:
    return json.dumps({
        "Manifests": [
            {
                "Name": "web",
                "ImageTargets": [
                    {"selector": "example-api", "BuildDetails": build_details},
                ],
            },
        ],
    })


def test_discover_services_reads_docker_build_context(tmp_path, monkeypatch):
    """Tilt's native docker_build() (local dev, and CI services that opt out
    of the buildx-cache path) reports the context under `context`."""
    stdout = _tiltfile_result({"context": str(tmp_path / "services/api")})
    monkeypatch.setattr("seal.tilt_discovery.shutil.which", lambda _: "/usr/bin/tilt")
    monkeypatch.setattr(
        "seal.tilt_discovery.subprocess.run",
        lambda *a, **kw: type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})(),
    )
    assert discover_services(tmp_path, []) == [("example-api", Path(tmp_path / "services/api"))]


def test_discover_services_reads_custom_build_dir(tmp_path, monkeypatch):
    """cached_docker_build()'s custom_build() (SEAL_BUILDX_CACHE=1, CI's
    default) reports it under `dir` instead, with no `context` key at all."""
    stdout = _tiltfile_result({"dir": str(tmp_path / "services/api"), "Deps": [str(tmp_path / "services/api")]})
    monkeypatch.setattr("seal.tilt_discovery.shutil.which", lambda _: "/usr/bin/tilt")
    monkeypatch.setattr(
        "seal.tilt_discovery.subprocess.run",
        lambda *a, **kw: type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})(),
    )
    assert discover_services(tmp_path, []) == [("example-api", Path(tmp_path / "services/api"))]


def test_discover_services_skips_targets_with_no_context(tmp_path, monkeypatch):
    """Neither key present (e.g. a non-image manifest) -- skipped, not a
    crash: this is also what silently swallowed the bug above, so it's worth
    pinning down on its own."""
    stdout = _tiltfile_result({})
    monkeypatch.setattr("seal.tilt_discovery.shutil.which", lambda _: "/usr/bin/tilt")
    monkeypatch.setattr(
        "seal.tilt_discovery.subprocess.run",
        lambda *a, **kw: type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})(),
    )
    assert discover_services(tmp_path, []) == []


def test_tiltfile_config_args_strips_tilt_cli_flags_before_dashdash():
    """The reusable deploy workflow calls `seal ci --namespace "$NS" --
    --k8s_overlay=stag --allowed_k8s_contexts=...`. `--namespace` is a
    `tilt ci`-level flag, not a Tiltfile config arg -- forwarding it to
    `tilt alpha tiltfile-result` (which doesn't accept `tilt up`/`tilt
    ci`-level flags) fails outright with 'unknown flag: --namespace', so no
    service gets discovered and no Secret ever generated. The '--' itself
    must stay in the result -- see the next test for why."""
    args = ["--namespace", "seal", "--", "--k8s_overlay=stag", "--allowed_k8s_contexts=my-context"]
    assert _tiltfile_config_args(args) == ["--", "--k8s_overlay=stag", "--allowed_k8s_contexts=my-context"]


def test_tiltfile_config_args_no_dashdash_means_no_tiltfile_args():
    """No '--' at all means every arg (if any) is a tilt-cli-level flag --
    there are no Tiltfile config args to forward."""
    assert _tiltfile_config_args(["--namespace", "seal"]) == []
    assert _tiltfile_config_args([]) == []


def test_tiltfile_config_args_keeps_dashdash_when_it_is_first():
    """the `ci` action's own calls (`seal ci -- --k8s_overlay dev --build_type
    test`): no tilt-cli flags before '--', so the whole thing -- '--'
    included -- passes through unchanged. The '--' must be kept, not stripped:
    `config.parse()` (tilt/seal/config.Tiltfile) only reads Tiltfile config
    args that come after Tilt's own '--' separator. Dropping the '--'
    makes `tilt alpha tiltfile-result` treat `--build_type` as one of
    its *own* flags and fail with 'unknown flag: --build_type'."""
    assert _tiltfile_config_args(["--", "--build_type", "test"]) == ["--", "--build_type", "test"]


def test_discover_services_drops_tilt_cli_flags_before_dashdash(tmp_path, monkeypatch):
    """End-to-end: discover_services() itself must not forward --namespace
    to the `tilt alpha tiltfile-result` subprocess call."""
    stdout = _tiltfile_result({"context": str(tmp_path / "services/api")})
    captured_argv = []

    def fake_run(argv, **kw):
        captured_argv.append(argv)
        return type("Result", (), {"returncode": 0, "stdout": stdout, "stderr": ""})()

    monkeypatch.setattr("seal.tilt_discovery.shutil.which", lambda _: "/usr/bin/tilt")
    monkeypatch.setattr("seal.tilt_discovery.subprocess.run", fake_run)

    args = ["--namespace", "seal", "--", "--k8s_overlay=stag"]
    assert discover_services(tmp_path, args) == [("example-api", Path(tmp_path / "services/api"))]
    assert captured_argv == [
        ["/usr/bin/tilt", "alpha", "tiltfile-result", "--file", "Tiltfile", "--", "--k8s_overlay=stag"]
    ]
