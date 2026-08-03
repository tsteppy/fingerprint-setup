from fingerprint_setup.client import (
    ENROLL_COMPLETED,
    ENROLL_DUPLICATE,
    ENROLL_FAILED,
    STAGE_PASSED,
)
from fingerprint_setup.enrollment import BASE_POSITIONS, EnrollmentCoach, build_sequence


def test_sequence_matches_the_requested_length_exactly():
    for n in (1, 3, 8, 9, 12):
        assert len(build_sequence(n)) == n


def test_sequence_of_eight_is_the_full_base_set():
    assert build_sequence(8) == BASE_POSITIONS


def test_short_sequence_keeps_centred_first():
    assert build_sequence(3)[0].key == "centred"


def test_long_sequence_reuses_positions_without_crashing():
    seq = build_sequence(12)
    assert len(seq) == 12
    assert {p.key for p in seq} <= {p.key for p in BASE_POSITIONS}


def test_stage_passed_advances_to_the_next_position():
    coach = EnrollmentCoach(num_stages=8)
    first = coach.current
    event = coach.on_status(STAGE_PASSED, False)
    assert event.kind == "advanced"
    assert coach.current != first
    assert coach.completed == 1


def test_retry_does_not_advance_the_position():
    coach = EnrollmentCoach(num_stages=8)
    before = coach.current
    event = coach.on_status("enroll-retry-center-finger", False)
    assert event.kind == "retry"
    assert coach.current == before
    assert coach.completed == 0
    assert "flatter" in event.message


def test_completed_zones_grows_only_on_success():
    coach = EnrollmentCoach(num_stages=8)
    coach.on_status(STAGE_PASSED, False)
    coach.on_status("enroll-retry-remove-finger", False)
    assert len(coach.completed_zones) == 1


def test_completion_is_reported_and_marks_finished():
    coach = EnrollmentCoach(num_stages=2)
    coach.on_status(STAGE_PASSED, False)
    event = coach.on_status(ENROLL_COMPLETED, True)
    assert event.kind == "completed"
    assert coach.finished is True


def test_failure_is_reported():
    coach = EnrollmentCoach(num_stages=8)
    event = coach.on_status(ENROLL_FAILED, True)
    assert event.kind == "failed"


def test_duplicate_is_reported_distinctly():
    coach = EnrollmentCoach(num_stages=8)
    event = coach.on_status(ENROLL_DUPLICATE, True)
    assert event.kind == "duplicate"
    assert "already" in event.message.lower()


def test_advancing_past_the_end_clamps_to_the_last_position():
    coach = EnrollmentCoach(num_stages=2)
    last = build_sequence(2)[-1]
    coach.on_status(STAGE_PASSED, False)
    coach.on_status(STAGE_PASSED, False)
    assert coach.current == last


def test_swipe_devices_get_swipe_instructions():
    coach = EnrollmentCoach(num_stages=3, scan_type="swipe")
    assert "swipe" in coach.current.instruction.lower()
