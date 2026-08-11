"""Reading CODEOWNERS, exercised against files the tests write rather than
the one this repo happens to ship.

The point of this module is that it agrees with GitHub for any project, so
every fixture here is a synthetic repository in tmp_path: nothing asserted
below is true because of how the bundled example is laid out, and none of it
stops being checked if that example changes.
"""

from pathlib import Path

from seal.codeowners import (
    CODEOWNERS_FILENAME,
    Rule,
    find_codeowners,
    find_repository_root,
    parse_codeowners,
)


def _repository(root: Path) -> Path:
    (root / ".git").mkdir()
    return root


def _write_codeowners(root: Path, contents: str, location: str = ".") -> Path:
    directory = root / location
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / CODEOWNERS_FILENAME
    path.write_text(contents, encoding="utf-8")
    return path


def _owners(contents: str, path: str, is_dir: bool = False, root: Path = Path("/repo")):
    codeowners = parse_codeowners(contents, source=root / CODEOWNERS_FILENAME, root=root)
    return codeowners.owners_for(Path(path), is_dir=is_dir)


# -- Finding the file --------------------------------------------------------


def test_codeowners_at_the_repository_root_is_found(tmp_path):
    _repository(tmp_path)
    path = _write_codeowners(tmp_path, "/outcomes/ @owner\n")

    codeowners = find_codeowners(tmp_path)

    assert codeowners is not None
    assert codeowners.source == path


def test_codeowners_under_dot_github_is_found(tmp_path):
    _repository(tmp_path)
    path = _write_codeowners(tmp_path, "/outcomes/ @owner\n", location=".github")

    assert find_codeowners(tmp_path).source == path


def test_codeowners_under_docs_is_found(tmp_path):
    _repository(tmp_path)
    path = _write_codeowners(tmp_path, "/outcomes/ @owner\n", location="docs")

    assert find_codeowners(tmp_path).source == path


def test_the_root_wins_over_the_other_two_locations(tmp_path):
    _repository(tmp_path)
    root_file = _write_codeowners(tmp_path, "/outcomes/ @root-owner\n")
    _write_codeowners(tmp_path, "/outcomes/ @github-owner\n", location=".github")
    _write_codeowners(tmp_path, "/outcomes/ @docs-owner\n", location="docs")

    codeowners = find_codeowners(tmp_path)

    assert codeowners.source == root_file
    assert codeowners.owners_for(tmp_path / "outcomes", is_dir=True) == ("@root-owner",)


def test_dot_github_wins_over_docs(tmp_path):
    _repository(tmp_path)
    github_file = _write_codeowners(tmp_path, "* @github-owner\n", location=".github")
    _write_codeowners(tmp_path, "* @docs-owner\n", location="docs")

    assert find_codeowners(tmp_path).source == github_file


def test_a_repository_with_no_codeowners_has_none(tmp_path):
    _repository(tmp_path)

    assert find_codeowners(tmp_path) is None


def test_a_codeowners_somewhere_github_does_not_read_is_not_found(tmp_path):
    _repository(tmp_path)
    _write_codeowners(tmp_path, "* @owner\n", location="config")

    assert find_codeowners(tmp_path) is None


# -- Finding the repository --------------------------------------------------


def test_the_repository_root_is_found_from_a_directory_below_it(tmp_path):
    _repository(tmp_path)
    nested = tmp_path / "examples" / "project" / "outcomes"
    nested.mkdir(parents=True)

    assert find_repository_root(nested) == tmp_path.resolve()


def test_a_dot_git_file_counts_as_a_repository(tmp_path):
    """A worktree or a submodule keeps a file at .git, not a directory."""
    (tmp_path / ".git").write_text("gitdir: /elsewhere/.git/worktrees/x\n", encoding="utf-8")
    nested = tmp_path / "services"
    nested.mkdir()

    assert find_repository_root(nested) == tmp_path.resolve()


def test_a_directory_in_no_repository_has_no_root(tmp_path):
    nested = tmp_path / "somewhere"
    nested.mkdir()

    assert find_repository_root(nested) is None


def test_patterns_resolve_against_the_repository_not_the_nested_project(tmp_path):
    """An seal project inside a larger repository is governed by that
    repository's CODEOWNERS, at paths carrying the project's own prefix."""
    _repository(tmp_path)
    _write_codeowners(tmp_path, "/examples/project/outcomes/ @owner\n")
    project = tmp_path / "examples" / "project"
    (project / "outcomes" / "epic" / "an-outcome").mkdir(parents=True)

    codeowners = find_codeowners(tmp_path)

    assert codeowners.owners_for(project / "outcomes" / "epic" / "an-outcome", is_dir=True) == (
        "@owner",
    )
    # The same path spelled from the project root, rather than the
    # repository root, is not what GitHub matches against.
    assert codeowners.owners_for(Path("outcomes/epic/an-outcome"), is_dir=True) == ()


# -- Parsing -----------------------------------------------------------------


def test_comments_and_blank_lines_are_not_rules(tmp_path):
    codeowners = parse_codeowners(
        "# who owns what\n\n   \n/outcomes/ @owner\n",
        source=tmp_path / CODEOWNERS_FILENAME,
        root=tmp_path,
    )

    assert codeowners.rules == (Rule(pattern="/outcomes/", owners=("@owner",), line=4),)


def test_a_rules_source_line_is_kept(tmp_path):
    codeowners = parse_codeowners(
        "\n\n* @first\n/outcomes/ @second\n",
        source=tmp_path / CODEOWNERS_FILENAME,
        root=tmp_path,
    )

    assert [rule.line for rule in codeowners.rules] == [3, 4]


def test_a_trailing_comment_is_not_an_owner():
    assert _owners("/outcomes/ @owner  # the humans\n", "outcomes/epic/x") == ("@owner",)


def test_a_pattern_with_no_owners_parses_as_a_rule(tmp_path):
    codeowners = parse_codeowners(
        "/outcomes/\n", source=tmp_path / CODEOWNERS_FILENAME, root=tmp_path
    )

    assert codeowners.rules == (Rule(pattern="/outcomes/", owners=(), line=1),)
    assert not codeowners.rules[0].owns_anything


def test_several_owners_on_one_rule_are_all_kept():
    assert _owners("/outcomes/ @one @org/team person@example.com\n", "outcomes/epic/x") == (
        "@one",
        "@org/team",
        "person@example.com",
    )


def test_a_section_header_owns_nothing(tmp_path):
    codeowners = parse_codeowners(
        "[Outcomes]\n/outcomes/ @owner\n^[Docs]\n",
        source=tmp_path / CODEOWNERS_FILENAME,
        root=tmp_path,
    )

    assert [rule.pattern for rule in codeowners.rules] == ["/outcomes/"]


# -- Matching ----------------------------------------------------------------


def test_an_anchored_directory_pattern_owns_everything_beneath_it():
    contents = "/outcomes/ @owner\n"

    assert _owners(contents, "outcomes", is_dir=True) == ("@owner",)
    assert _owners(contents, "outcomes/epic/an-outcome", is_dir=True) == ("@owner",)
    assert _owners(contents, "outcomes/epic/an-outcome/prompt.md") == ("@owner",)


def test_an_anchored_pattern_does_not_match_the_same_name_deeper():
    contents = "/outcomes/ @owner\n"

    assert _owners(contents, "services/api/outcomes/x.py") == ()


def test_a_directory_pattern_does_not_match_a_file_of_that_name():
    assert _owners("outcomes/ @owner\n", "outcomes") == ()
    assert _owners("outcomes/ @owner\n", "outcomes", is_dir=True) == ("@owner",)


def test_a_pattern_without_a_trailing_slash_still_owns_what_is_beneath_it():
    """A directory that matches carries its contents, the way gitignore
    reads the same pattern."""
    assert _owners("/outcomes @owner\n", "outcomes/epic/an-outcome/test.py") == ("@owner",)


def test_a_bare_name_matches_at_any_depth():
    contents = "outcomes/ @owner\n"

    assert _owners(contents, "outcomes/epic/x.py") == ("@owner",)
    assert _owners(contents, "examples/project/outcomes/epic/x.py") == ("@owner",)


def test_a_star_does_not_cross_a_slash():
    assert _owners("/outcomes/*.py @owner\n", "outcomes/x.py") == ("@owner",)
    assert _owners("/outcomes/*.py @owner\n", "outcomes/epic/x.py") == ()


def test_a_double_star_spans_directories():
    contents = "/outcomes/**/prompt.md @owner\n"

    assert _owners(contents, "outcomes/epic/an-outcome/prompt.md") == ("@owner",)
    assert _owners(contents, "outcomes/prompt.md") == ("@owner",)


def test_a_question_mark_matches_one_character_but_not_a_slash():
    assert _owners("/outcomes/?.py @owner\n", "outcomes/a.py") == ("@owner",)
    assert _owners("/outcomes/?.py @owner\n", "outcomes/ab.py") == ()


def test_a_star_alone_owns_the_whole_repository():
    assert _owners("* @owner\n", "anything/at/all.py") == ("@owner",)


def test_a_bracket_is_a_literal_not_a_character_range():
    """GitHub rejects character ranges, so a project that writes one gets a
    literal bracket matched."""
    assert _owners("/outcomes/[ab].py @owner\n", "outcomes/[ab].py") == ("@owner",)
    assert _owners("/outcomes/[ab].py @owner\n", "outcomes/a.py") == ()


# -- Precedence --------------------------------------------------------------


def test_the_last_matching_rule_wins_not_the_most_specific():
    contents = "/outcomes/epic/ @specific\n* @catch-all\n"

    assert _owners(contents, "outcomes/epic/an-outcome/test.py") == ("@catch-all",)


def test_a_later_ownerless_rule_clears_an_earlier_owned_one():
    contents = "/outcomes/ @owner\n/outcomes/epic/an-outcome/test.py\n"

    assert _owners(contents, "outcomes/epic/an-outcome/test.py") == ()
    assert _owners(contents, "outcomes/epic/an-outcome/prompt.md") == ("@owner",)


def test_the_rule_that_decided_a_path_is_reported(tmp_path):
    """A report that names the line which left a path unowned is the
    difference between a fixable failure and a puzzle."""
    codeowners = parse_codeowners(
        "/outcomes/ @owner\n*.py\n", source=tmp_path / CODEOWNERS_FILENAME, root=tmp_path
    )

    rule = codeowners.deciding_rule(Path("outcomes/epic/an-outcome/test.py"), is_dir=False)

    assert rule == Rule(pattern="*.py", owners=(), line=2)


def test_a_path_no_rule_matches_has_no_deciding_rule(tmp_path):
    codeowners = parse_codeowners(
        "/services/ @owner\n", source=tmp_path / CODEOWNERS_FILENAME, root=tmp_path
    )

    assert codeowners.deciding_rule(Path("outcomes/epic/x"), is_dir=True) is None
    assert codeowners.owners_for(Path("outcomes/epic/x"), is_dir=True) == ()


def test_a_path_outside_the_repository_is_owned_by_nothing(tmp_path):
    _repository(tmp_path)
    _write_codeowners(tmp_path, "* @owner\n")
    outside = tmp_path.parent / "elsewhere" / "outcomes"
    outside.mkdir(parents=True)

    assert find_codeowners(tmp_path).owners_for(outside, is_dir=True) == ()
