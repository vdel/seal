"""The agent skills Seal ships, and the installer that puts them in a project.

Everything here is exercised against a synthetic target repository in
tmp_path: what makes an install correct is what it does to *any* project, not
what it happens to do to this one. The shipped skills themselves are read from
the repository, since they are the deliverable.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALLER = REPO_ROOT / "bin" / "install-seal-skills"
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"
AGENTS_DIR = REPO_ROOT / ".claude" / "agents"

BLOCK_BEGIN = "<!-- seal:skills:begin -->"
BLOCK_END = "<!-- seal:skills:end -->"


def _frontmatter(path: Path) -> dict[str, str]:
    """The `key: value` pairs of a leading `---` block, which is all these use."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None, f"{path} has no frontmatter block"
    fields: dict[str, str] = {}
    key = None
    for line in match.group(1).splitlines():
        if re.match(r"^\w[\w-]*:", line):
            key, _, value = line.partition(":")
            fields[key] = value.strip()
        elif key is not None:
            fields[key] += " " + line.strip()
    return fields


def _install(target: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(INSTALLER), "--target", str(target), "--from", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A repository with a CLAUDE.md of its own and a skill that isn't Seal's."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "CLAUDE.md").write_text("# My project\n\nSome guidance.\n", encoding="utf-8")
    own = tmp_path / ".claude" / "skills" / "project-own"
    own.mkdir(parents=True)
    (own / "SKILL.md").write_text("---\nname: project-own\n---\n", encoding="utf-8")
    return tmp_path


# -- What ships --------------------------------------------------------------


def test_every_skill_declares_the_name_of_its_own_directory():
    shipped = sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir())
    assert shipped, "no skills ship at all"

    for skill in shipped:
        fields = _frontmatter(skill / "SKILL.md")
        assert fields["name"] == skill.name
        assert len(fields["description"]) > 40, f"{skill.name}'s description says too little to route on"


def test_every_agent_declares_the_name_of_its_own_file():
    shipped = sorted(AGENTS_DIR.glob("*.md"))
    assert shipped, "no agents ship at all"

    for agent in shipped:
        fields = _frontmatter(agent)
        assert fields["name"] == agent.stem
        assert len(fields["description"]) > 40, f"{agent.stem}'s description says too little to route on"


def test_the_entry_skill_routes_to_every_other_one():
    entry = (SKILLS_DIR / "seal" / "SKILL.md").read_text(encoding="utf-8")

    for skill in sorted(p for p in SKILLS_DIR.iterdir() if p.is_dir() and p.name != "seal"):
        assert skill.name in entry, f"{skill.name} is unreachable from the skill that routes"
    for agent in sorted(AGENTS_DIR.glob("*.md")):
        assert agent.stem in entry, f"{agent.stem} is unreachable from the skill that routes"


# -- Installing --------------------------------------------------------------


def test_installing_copies_every_skill_and_agent(project: Path):
    result = _install(project)

    assert result.returncode == 0, result.stderr
    for skill in (p for p in SKILLS_DIR.iterdir() if p.is_dir()):
        assert (project / ".claude" / "skills" / skill.name / "SKILL.md").is_file()
    for agent in AGENTS_DIR.glob("*.md"):
        assert (project / ".claude" / "agents" / agent.name).is_file()


def test_installing_twice_changes_nothing_the_second_time(project: Path):
    _install(project)

    assert _install(project, "--check").returncode == 0


def test_check_reports_what_is_missing_without_writing_it(project: Path):
    result = _install(project, "--check")

    assert result.returncode == 1
    assert "seal-outcome" in result.stdout
    assert not (project / ".claude" / "skills" / "seal").exists()


def test_a_skill_seal_no_longer_ships_is_removed(project: Path):
    _install(project)
    stale = project / ".claude" / "skills" / "seal-retired"
    stale.mkdir()
    (stale / "SKILL.md").write_text("---\nname: seal-retired\n---\n", encoding="utf-8")

    _install(project)

    assert not stale.exists()


def test_a_skill_that_isnt_seals_is_left_alone(project: Path):
    _install(project)

    assert (project / ".claude" / "skills" / "project-own" / "SKILL.md").is_file()


def test_the_projects_own_claude_md_keeps_what_it_said(project: Path):
    _install(project)

    contents = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Some guidance." in contents
    assert contents.count(BLOCK_BEGIN) == 1
    assert "seal up" in contents


def test_a_project_with_no_claude_md_gets_one(tmp_path: Path):
    _install(tmp_path)

    assert BLOCK_BEGIN in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_an_edited_block_is_put_back_and_the_rest_is_not(project: Path):
    _install(project)
    path = project / "CLAUDE.md"
    path.write_text(
        path.read_text(encoding="utf-8").replace("## Seal", "## Seal, edited by hand"),
        encoding="utf-8",
    )

    result = _install(project)

    contents = path.read_text(encoding="utf-8")
    assert "edited by hand" not in contents
    assert "Some guidance." in contents
    assert contents.count(BLOCK_BEGIN) == 1
    assert "CLAUDE.md" in result.stdout


def test_uninstalling_takes_back_exactly_what_was_installed(project: Path):
    _install(project)

    result = _install(project, "--uninstall")

    assert result.returncode == 0
    assert not (project / ".claude" / "skills" / "seal").exists()
    assert (project / ".claude" / "skills" / "project-own" / "SKILL.md").is_file()
    contents = (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert BLOCK_BEGIN not in contents and BLOCK_END not in contents
    assert "Some guidance." in contents


def test_installing_into_seals_own_checkout_is_refused(tmp_path: Path):
    result = _install(REPO_ROOT)

    assert result.returncode != 0
    assert "checkout itself" in result.stderr


def test_a_target_that_isnt_a_directory_is_refused(tmp_path: Path):
    result = _install(tmp_path / "nowhere")

    assert result.returncode != 0
    assert "not a directory" in result.stderr


# -- What they promise the CLI does ------------------------------------------


def _seal_invocations(text: str) -> list[list[str]]:
    """Every `seal ...` command line a skill spells out, as tokens.

    Both places one appears: a line of its own inside a fenced block, and a
    backtick span in a table cell or a sentence."""
    found = []
    for line in re.findall(r"(?m)^\s{0,4}(seal [^\n`|]*)", text):
        found.append(line)
    for span in re.findall(r"`(seal [^`]*)`", text):
        found.append(span)
    invocations = []
    for command in found:
        tokens = command.split("#", 1)[0].split()
        # Everything after `--` is Tilt's, forwarded verbatim -- `seal ci --
        # --build_type test` passes a Tiltfile config arg, not a flag of
        # seal's own.
        if "--" in tokens:
            tokens = tokens[: tokens.index("--")]
        invocations.append(tokens)
    return invocations


def _declared_flags() -> set[str]:
    source = (REPO_ROOT / "python" / "src" / "seal" / "seal.py").read_text(encoding="utf-8")
    return set(re.findall(r'add_argument\(\s*"(--[a-z0-9-]+)"', source))


def _dispatched_subcommands() -> set[str]:
    source = (REPO_ROOT / "python" / "src" / "seal" / "seal.py").read_text(encoding="utf-8")
    return set(re.findall(r'(?:subcommand ==|rest\[0\] ==) "([a-z-]+)"', source))


def test_every_seal_command_a_skill_spells_out_is_one_the_cli_has():
    """A skill that promises a flag the CLI does not have is worse than a
    missing skill: it reads as authoritative and fails at the first use.

    What this catches is drift -- a flag or a subcommand renamed on one side
    and not the other. It does not check that a flag belongs to the
    subcommand it is written beside; the parsers are built inside the
    commands that own them, and reaching into them here would pin this test
    to how the CLI happens to be structured rather than to what it accepts.
    """
    flags = _declared_flags()
    subcommands = _dispatched_subcommands()
    checked = 0

    for path in [*SKILLS_DIR.glob("*/SKILL.md"), *AGENTS_DIR.glob("*.md")]:
        text = path.read_text(encoding="utf-8")
        for tokens in _seal_invocations(text):
            words = [token for token in tokens[1:] if re.fullmatch(r"[a-z][a-z-]*", token)]
            if words:
                assert words[0] in subcommands, (
                    f"{path.name} runs `seal {words[0]}`, which the CLI does not dispatch"
                )
            for token in tokens:
                if token.startswith("--") and token != "--":
                    assert token in flags, (
                        f"{path.name} passes `{token}`, which the CLI does not declare"
                    )
                    checked += 1

    assert checked, "no seal invocation with a flag was found to check"


def test_the_loop_is_reachable_and_installs_with_the_rest():
    """The regression loop is the one skill whose absence would be invisible:
    an agent that never finds it falls back to reasoning about a red suite
    from first principles, and the first thing that suggests is editing the
    test that failed."""
    entry = (SKILLS_DIR / "seal" / "SKILL.md").read_text(encoding="utf-8")

    assert (SKILLS_DIR / "seal-regression-loop" / "SKILL.md").is_file()
    assert (AGENTS_DIR / "seal-app-fixer.md").is_file()
    assert "seal-regression-loop" in entry
    assert "seal-app-fixer" in entry


def test_the_loop_never_tells_an_agent_to_narrow_the_suite():
    """A fix scoped to the promise that was red, re-verified against nothing
    else, is how another gets broken with nobody looking -- so the iteration
    the loop spells out has to be the whole tree."""
    loop = (SKILLS_DIR / "seal-regression-loop" / "SKILL.md").read_text(encoding="utf-8")

    iterations = [
        tokens
        for tokens in _seal_invocations(loop)
        if tokens[1:3] == ["outcomes", "run"] and "--confirm" in tokens
    ]
    assert iterations, "the loop spells out no iteration at all"
    for tokens in iterations:
        assert "--all" in tokens
        assert "--reset" in tokens


def test_a_loop_with_a_reason_to_stop_hands_over_rather_than_concluding():
    """The session that has been looping is the one that has already decided
    which promise is at fault, which is exactly why it does not get to say.
    A loop whose instructions end at "stop" leaves that decision with it by
    default."""
    loop = (SKILLS_DIR / "seal-regression-loop" / "SKILL.md").read_text(encoding="utf-8")

    assert (AGENTS_DIR / "seal-loop-triager.md").is_file()
    assert "seal-loop-triager" in loop
    assert any(
        tokens[1:3] == ["outcomes", "loop"] for tokens in _seal_invocations(loop)
    ), "the loop never says how to read the sequence it is meant to hand over"


def test_the_triager_reads_the_loop_before_it_concludes_anything():
    """Its whole contribution is fresh context over the sequence. One that
    started from the failing tests instead would be reasoning from the same
    place the loop already did."""
    triager = (AGENTS_DIR / "seal-loop-triager.md").read_text(encoding="utf-8")

    assert any(
        tokens[1:3] == ["outcomes", "loop"] for tokens in _seal_invocations(triager)
    )
    assert any(
        tokens[1:3] == ["outcomes", "review"] for tokens in _seal_invocations(triager)
    ), "nothing puts a promise beside the test it is being judged against"
