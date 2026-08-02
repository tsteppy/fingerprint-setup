import pytest

from fingerprint_setup.client import (
    ENROLL_COMPLETED,
    STAGE_PASSED,
    VERIFY_MATCH,
    VERIFY_NO_MATCH,
)
from fingerprint_setup.fake_client import FakeClient


# Test retry value that doesn't start with "enroll-retry" prefix
RETRY_CENTER_FINGER = "enroll-finger-not-centered"


def test_lists_nothing_before_enrolment():
    client = FakeClient()
    client.claim("alice")
    assert client.list_enrolled("alice") == []


def test_enrol_emits_queued_results_and_records_the_finger():
    client = FakeClient(num_enroll_stages=3)
    client.claim("alice")
    client.queue_enroll_results([STAGE_PASSED, STAGE_PASSED, ENROLL_COMPLETED])

    seen = []
    client.enroll_start("right-index-finger", lambda r, d: seen.append((r, d)))

    assert seen == [
        (STAGE_PASSED, False),
        (STAGE_PASSED, False),
        (ENROLL_COMPLETED, True),
    ]
    assert client.list_enrolled("alice") == ["right-index-finger"]


def test_verify_emits_queued_results():
    client = FakeClient()
    client.claim("alice")
    client.queue_verify_results([VERIFY_MATCH, VERIFY_NO_MATCH])

    seen = []
    client.verify_start("right-index-finger", lambda r, d: seen.append(r))
    client.verify_start("right-index-finger", lambda r, d: seen.append(r))

    assert seen == [VERIFY_MATCH, VERIFY_NO_MATCH]


def test_delete_removes_the_finger():
    client = FakeClient(num_enroll_stages=1)
    client.claim("alice")
    client.queue_enroll_results([ENROLL_COMPLETED])
    client.enroll_start("left-index-finger", lambda r, d: None)

    client.delete_finger("left-index-finger")

    assert client.list_enrolled("alice") == []


def test_operations_require_a_claim():
    client = FakeClient()
    with pytest.raises(RuntimeError, match="not claimed"):
        client.enroll_start("right-index-finger", lambda r, d: None)


def test_release_is_tracked():
    client = FakeClient()
    client.claim("alice")
    client.release()
    assert client.released is True


def test_retry_without_enroll_retry_prefix_is_not_done():
    """Test that retry values not starting with 'enroll-retry' are still reported as done=False.

    This specifically tests enroll-finger-not-centered, which doesn't have the
    'enroll-retry' prefix but must still be treated as a retry (done=False).
    """
    client = FakeClient(num_enroll_stages=2)
    client.claim("alice")
    client.queue_enroll_results([RETRY_CENTER_FINGER, ENROLL_COMPLETED])

    seen = []
    client.enroll_start("right-index-finger", lambda r, d: seen.append((r, d)))

    assert seen == [
        (RETRY_CENTER_FINGER, False),
        (ENROLL_COMPLETED, True),
    ]
    assert client.list_enrolled("alice") == ["right-index-finger"]
