import pytest

from fingerprint_setup.client import VERIFY_MATCH, VERIFY_NO_MATCH
from fingerprint_setup.quality import TEST_PROMPTS, QualityTest


def test_there_are_six_natural_and_four_offset_prompts():
    assert len(TEST_PROMPTS) == 10
    assert sum(1 for p in TEST_PROMPTS if p.kind == "natural") == 6
    assert sum(1 for p in TEST_PROMPTS if p.kind == "offset") == 4


def _run(results):
    test = QualityTest()
    for result in results:
        test.record(result)
    return test


def test_all_matches_is_good():
    verdict = _run([VERIFY_MATCH] * 10).verdict()
    assert verdict.band == "good"
    assert verdict.matches == 10


def test_nine_matches_is_still_good():
    assert _run([VERIFY_MATCH] * 9 + [VERIFY_NO_MATCH]).verdict().band == "good"


def test_eight_matches_is_fair():
    assert _run([VERIFY_MATCH] * 8 + [VERIFY_NO_MATCH] * 2).verdict().band == "fair"


def test_seven_matches_is_fair():
    assert _run([VERIFY_MATCH] * 7 + [VERIFY_NO_MATCH] * 3).verdict().band == "fair"


def test_six_matches_is_weak():
    # 3 natural matches + 3 offset matches = 6 total, not narrow case, should be weak
    assert _run([VERIFY_MATCH] * 3 + [VERIFY_NO_MATCH] * 3 + [VERIFY_MATCH] * 3 + [VERIFY_NO_MATCH] * 1).verdict().band == "weak"


def test_natural_and_offset_are_counted_separately():
    # first six prompts are natural, last four are offset
    verdict = _run([VERIFY_MATCH] * 6 + [VERIFY_NO_MATCH] * 4).verdict()
    assert verdict.natural_matches == 6
    assert verdict.offset_matches == 0


def test_passing_natural_but_failing_offset_gives_narrow_advice():
    verdict = _run([VERIFY_MATCH] * 6 + [VERIFY_NO_MATCH] * 4).verdict()
    assert "narrow" in verdict.advice.lower()


def test_finished_only_after_all_prompts():
    test = QualityTest()
    for _ in range(9):
        test.record(VERIFY_MATCH)
    assert test.finished is False
    test.record(VERIFY_MATCH)
    assert test.finished is True


def test_verdict_before_finishing_is_refused():
    test = QualityTest()
    test.record(VERIFY_MATCH)
    with pytest.raises(RuntimeError, match="not finished"):
        test.verdict()


def test_prompts_advance_from_natural_to_offset():
    test = QualityTest()
    assert test.index == 0
    assert test.current.kind == "natural"

    for _ in range(6):
        test.record(VERIFY_MATCH)

    assert test.index == 6
    assert test.current.kind == "offset"
    assert test.current.instruction == "Press with the tip of your finger"


def test_narrow_enrolment_is_fair_not_weak():
    # natural=6, offset=0 gives 6 total matches, which would normally be "weak",
    # but the narrow case should elevate it to "fair" with appropriate messaging.
    verdict = _run([VERIFY_MATCH] * 6 + [VERIFY_NO_MATCH] * 4).verdict()
    assert verdict.band == "fair"
    assert "unreliable" not in verdict.headline.lower()
    assert "narrow" in verdict.advice.lower()


def test_eleventh_record_raises():
    test = QualityTest()
    for _ in range(10):
        test.record(VERIFY_MATCH)
    assert test.finished is True
    with pytest.raises(RuntimeError, match="already finished"):
        test.record(VERIFY_MATCH)
