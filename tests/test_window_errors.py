"""Busy-reader handling in window.py.

MainWindow itself needs a live Adw.Application and, transitively, a
display -- not something this suite should require. The logic that has to
tolerate a busy `DeviceBusyError` claim (used by both `_render_fingers` and
`_on_delete_clicked`) is pulled out into the module-level
`fetch_enrolled_fingers` / `delete_finger_safe` helpers precisely so it can
be exercised headlessly, against a `FakeClient` whose `claim()` is made to
raise on demand.
"""

from fingerprint_setup.fake_client import FakeClient
from fingerprint_setup.fprintd_client import DeviceBusyError
from fingerprint_setup.window import delete_finger_safe, fetch_enrolled_fingers


class BusyClaimClient(FakeClient):
    """A FakeClient whose claim() raises DeviceBusyError on chosen calls.

    `busy_on_calls` names which 1-indexed claim() calls should raise --
    e.g. {1} makes only the first claim busy, {2} makes only the second.
    """

    def __init__(self, busy_on_calls: set[int], **kwargs) -> None:
        super().__init__(**kwargs)
        self._busy_on_calls = busy_on_calls
        self._claim_calls = 0

    def claim(self, username: str) -> None:
        self._claim_calls += 1
        if self._claim_calls in self._busy_on_calls:
            raise DeviceBusyError("device is in use")
        super().claim(username)


def test_fetch_enrolled_fingers_does_not_raise_when_busy():
    client = BusyClaimClient(busy_on_calls={1})

    fingers, busy = fetch_enrolled_fingers(client, "tester")

    assert busy is True
    assert fingers == []
    # A failed claim never succeeded, so release() must not have been
    # called on its behalf either.
    assert client.released is False


def test_fetch_enrolled_fingers_normal_path_is_unaffected():
    client = FakeClient()
    client.claim("tester")
    client.queue_enroll_results([])
    client._enrolled["tester"] = ["left-thumb"]
    client.release()

    fingers, busy = fetch_enrolled_fingers(client, "tester")

    assert busy is False
    assert fingers == ["left-thumb"]
    assert client.released is True


def test_delete_finger_safe_does_not_raise_when_busy_on_second_claim():
    """Reproduces the window's real sequence: one successful claim while
    building the row list (the window's initial render), then a second
    claim -- made busy here -- when the user clicks Delete.
    """
    client = BusyClaimClient(busy_on_calls={2})
    client.claim("tester")
    client._enrolled["tester"] = ["left-thumb"]
    client.release()

    deleted = delete_finger_safe(client, "tester", "left-thumb")

    assert deleted is False
    # Nothing was removed -- the busy claim must not touch state.
    assert client.list_enrolled("tester") == ["left-thumb"]


def test_delete_finger_safe_deletes_when_not_busy():
    client = FakeClient()
    client.claim("tester")
    client._enrolled["tester"] = ["left-thumb"]
    client.release()

    deleted = delete_finger_safe(client, "tester", "left-thumb")

    assert deleted is True
    assert client.list_enrolled("tester") == []
