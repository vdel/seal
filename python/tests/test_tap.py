"""What a runner's TAP stream says, and what it doesn't.

A `tap` group is started once and reports one test point per outcome (see
/rfcs/0014-seal-on-seal.md). Everything here is checked against
strings: the reader has no idea a description might be a slug, and that is
what keeps these tests about the protocol rather than about a tree.

The cases that matter most are the ones where a stream says *less* than it
promised. A promise nothing tested and a promise that failed are different
things, and only the plan and the bail-out can tell them apart.
"""

from seal.tap import SKIP, TODO, read


def test_a_plan_and_the_points_it_promised():
    report = read("1..3\nok 1 - first\nnot ok 2 - second\nok 3 - third\n")

    assert report.planned == 3
    assert [(point.description, point.ok) for point in report.points] == [
        ("first", True),
        ("second", False),
        ("third", True),
    ]
    assert not report.is_short
    assert report.bailed_out is None


def test_a_plan_at_the_end_counts_the_same():
    """A producer that only knows its count once it has finished puts the
    plan last, which is as legal as putting it first."""
    report = read("ok 1 - first\nok 2 - second\n1..2\n")

    assert report.planned == 2
    assert not report.is_short


def test_a_point_with_no_number_or_dash_is_still_a_result():
    """Both are optional in TAP, and a producer that omits them is still
    saying what it found."""
    report = read("ok first\nnot ok second\n")

    assert [(point.description, point.ok) for point in report.points] == [
        ("first", True),
        ("second", False),
    ]


def test_a_skipped_point_established_nothing():
    report = read("1..1\nok 1 - a promise # SKIP no cluster here\n")
    (point,) = report.points

    assert point.description == "a promise"
    assert point.directive == SKIP
    assert point.reason == "no cluster here"
    assert not point.established_something


def test_a_todo_point_established_nothing_either():
    report = read("1..1\nnot ok 1 - a promise # TODO being written\n")
    (point,) = report.points

    assert point.directive == TODO
    assert not point.established_something


def test_a_directive_is_recognised_whatever_its_case_and_needs_no_reason():
    report = read(
        "ok 1 - one # skip\nok 2 - two # Skip\nok 3 - three # SKIP\nok 4 - four # sKiP why\n"
    )

    assert [point.directive for point in report.points] == [SKIP] * 4
    assert [point.reason for point in report.points] == ["", "", "", "why"]


def test_a_hash_inside_a_description_does_not_start_a_directive():
    """Only a directive keyword right after the `#` counts as one, or a
    promise whose name mentions one would report itself untested."""
    report = read("ok 1 - the # in a name\n")
    (point,) = report.points

    assert point.description == "the # in a name"
    assert point.established_something


def test_a_dash_inside_a_description_survives():
    """Slugs are hyphenated, so this is the ordinary case rather than an
    edge one."""
    report = read("ok 1 - gating/a-promise-that-holds\n")
    (point,) = report.points

    assert point.description == "gating/a-promise-that-holds"


def test_what_a_point_printed_belongs_to_that_point():
    report = read(
        "ok 1 - first\n"
        "  ---\n"
        "  message: nothing to say\n"
        "  ...\n"
        "# a comment under the first\n"
        "not ok 2 - second\n"
        "  ---\n"
        "  message: it broke\n"
        "  ...\n"
    )
    first, second = report.points

    assert "message: nothing to say" in "\n".join(first.diagnostics)
    assert "# a comment under the first" in "\n".join(first.diagnostics)
    assert "message: it broke" in "\n".join(second.diagnostics)
    assert "it broke" not in "\n".join(first.diagnostics)


def test_anything_before_the_first_point_is_dropped_rather_than_misattributed():
    """A runner prints on the way in -- progress, a banner, a cluster coming
    up. None of it is an account of a promise nobody has reported yet."""
    report = read("bringing the cluster up\nstill going\nok 1 - first\n")
    (point,) = report.points

    assert point.diagnostics == ()


def test_a_bail_out_is_reported_and_the_points_before_it_are_kept():
    report = read("1..4\nok 1 - first\nok 2 - second\nBail out! the cluster died\n")

    assert report.bailed_out == "the cluster died"
    assert [point.description for point in report.points] == ["first", "second"]
    assert report.is_short


def test_nothing_after_a_bail_out_is_read():
    """The producer has said it is no longer reporting, so what follows is
    noise -- and a verdict read out of it would be one nothing established."""
    report = read("ok 1 - first\nBail out!\nok 2 - second\n")

    assert report.bailed_out == ""
    assert [point.description for point in report.points] == ["first"]


def test_a_stream_shorter_than_its_plan_says_so():
    report = read("1..5\nok 1 - first\nok 2 - second\nok 3 - third\n")

    assert report.is_short
    assert len(report.points) == 3


def test_a_stream_with_no_plan_is_never_short():
    """Without a plan there is nothing a stream could fall short of. What
    the caller does about the outcomes it asked for and did not hear about
    is its own business."""
    report = read("ok 1 - first\n")

    assert report.planned is None
    assert not report.is_short


def test_a_plan_of_zero_is_a_run_that_covered_nothing():
    report = read("1..0\n")

    assert report.planned == 0
    assert report.points == ()
    assert not report.is_short


def test_an_empty_stream_says_nothing():
    report = read("")

    assert report.points == ()
    assert report.planned is None
    assert report.bailed_out is None


def test_output_that_is_not_tap_yields_no_points():
    """A runner is a program somebody wrote, and it prints. Refusing the
    first unrecognised line would turn a promise that was kept into a run
    nobody could read."""
    report = read("Traceback (most recent call last):\n  File nowhere\nboom\n")

    assert report.points == ()


def test_a_repeated_description_is_reported_and_the_last_wins():
    report = read("ok 1 - one\nnot ok 2 - one\nok 3 - two\n")

    assert report.duplicated() == ("one",)
    assert report.by_description()["one"].ok is False
    assert set(report.by_description()) == {"one", "two"}


def test_points_are_read_in_the_order_they_arrive_whatever_they_are_numbered():
    """The number is the producer's bookkeeping. What a caller matches on is
    the description, so an out-of-order stream is not a broken one."""
    report = read("ok 3 - third\nok 1 - first\nok 2 - second\n")

    assert [point.description for point in report.points] == ["third", "first", "second"]


def test_a_point_with_no_description_is_preserved_as_having_none():
    """Legal TAP, and useless to a caller matching on names -- so it is kept
    as what it is rather than given a name it never had."""
    report = read("1..1\nok 1\n")
    (point,) = report.points

    assert point.description == ""
    assert point.ok


def test_a_line_that_merely_starts_with_ok_is_not_a_point():
    """`\\b` after the keyword, or a runner narrating its own progress would
    file verdicts."""
    report = read("okay then\nnot okay either\n")

    assert report.points == ()
