"""Guards two whole-branch review findings against recurring:

1. The AttributeError class of bug -- Adw.Toast has no add_css_class(), so
   applying BAND_STYLE to a toast raised before the toast was ever shown.
   ResultDialog is the replacement; build one from a Verdict of every band
   and just make sure it does not raise.
2. The claim/release invariant -- a claim the app forgets to release makes
   the reader unusable for every other application on the machine,
   including the login screen. EnrollDialog and QualityTestDialog both
   claim in run(); this drives both through normal completion, a
   busy-reader claim() failure, and a cancellation that lands mid-operation,
   and checks the claim depth is back to zero every time.

These dialogs are real GTK widgets (Adw.Window subclasses), so this suite
needs a live display and Adw to be initialised -- unlike the rest of the
test suite, which is deliberately display-free.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

Adw.init()

from fingerprint_setup.enroll_dialog import EnrollDialog
from fingerprint_setup.fake_client import FakeClient
from fingerprint_setup.fprintd_client import DeviceBusyError
from fingerprint_setup.quality import Verdict
from fingerprint_setup.quality_dialog import QualityTestDialog, ResultDialog


def _parent() -> Gtk.Window:
    return Gtk.Window()


def _verdict(band: str) -> Verdict:
    return Verdict(
        band=band,
        matches=7,
        total=10,
        natural_matches=5,
        offset_matches=2,
        headline=f"headline for {band}",
        advice=f"advice for {band}",
    )


# -- 1. the result dialog must build for every band ----------------------


def test_result_dialog_builds_for_every_band():
    for band in ("good", "fair", "weak"):
        dialog = ResultDialog(_parent(), _verdict(band))
        assert dialog is not None
        dialog.destroy()


def test_result_dialog_builds_for_an_unrecognised_band():
    """BAND_STYLE.get() and the icon lookup both default gracefully --
    Verdict.band is a plain str, not an enum, so nothing enforces the
    known set at construction time.
    """
    dialog = ResultDialog(_parent(), _verdict("mystery"))
    assert dialog is not None
    dialog.destroy()


# -- claim/release balance ------------------------------------------------


class ClaimTrackingClient(FakeClient):
    """Counts outstanding claims and lets a caller-supplied hook fire from
    inside an in-flight enrol/verify call, to simulate a cancellation that
    arrives mid-operation rather than only between operations.
    """

    def __init__(self, *args, busy_on_calls: set[int] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.depth = 0
        self.max_depth = 0
        self._claim_calls = 0
        self._busy_on_calls = busy_on_calls or set()
        self.mid_operation_hook = None  # type: ignore[var-annotated]

    def claim(self, username: str) -> None:
        self._claim_calls += 1
        if self._claim_calls in self._busy_on_calls:
            raise DeviceBusyError("device is in use")
        super().claim(username)
        self.depth += 1
        self.max_depth = max(self.max_depth, self.depth)

    def release(self) -> None:
        super().release()
        self.depth = max(0, self.depth - 1)

    def enroll_start(self, finger, on_status) -> None:  # noqa: ANN001
        if self.mid_operation_hook is not None:
            hook, self.mid_operation_hook = self.mid_operation_hook, None
            hook()
        super().enroll_start(finger, on_status)

    def verify_start(self, finger, on_status) -> None:  # noqa: ANN001
        if self.mid_operation_hook is not None:
            hook, self.mid_operation_hook = self.mid_operation_hook, None
            hook()
        super().verify_start(finger, on_status)


def test_enroll_dialog_claim_release_balances_on_normal_completion():
    client = ClaimTrackingClient(num_enroll_stages=2)
    dialog = EnrollDialog(_parent(), client, "tester", "right-index-finger")

    completed = dialog.run()

    assert completed is True
    assert client.depth == 0
    assert client.max_depth == 1


def test_enroll_dialog_claim_release_balances_when_busy():
    client = ClaimTrackingClient(num_enroll_stages=2, busy_on_calls={1})
    dialog = EnrollDialog(_parent(), client, "tester", "right-index-finger")

    completed = dialog.run()

    assert completed is False
    assert "in use" in dialog.final_message
    # claim() raised before it ever incremented depth -- nothing to release.
    assert client.depth == 0
    assert client.max_depth == 0


def test_enroll_dialog_claim_release_balances_when_cancelled_mid_operation():
    client = ClaimTrackingClient(num_enroll_stages=2)
    dialog = EnrollDialog(_parent(), client, "tester", "right-index-finger")
    # Simulate the user hitting Cancel partway through the enrolment: the
    # hook fires from inside enroll_start(), before any stage has reported,
    # exactly like a close-request arriving mid-press on real hardware.
    client.mid_operation_hook = dialog.close

    completed = dialog.run()

    assert completed is False
    assert client.depth == 0
    assert client.max_depth == 1


def test_quality_dialog_claim_release_balances_on_normal_completion():
    client = ClaimTrackingClient()

    dialog = QualityTestDialog(_parent(), client, "tester", "right-index-finger")
    verdict = dialog.run()

    assert verdict is not None
    assert dialog.busy is False
    assert client.depth == 0
    assert client.max_depth == 1


def test_quality_dialog_claim_release_balances_when_busy():
    client = ClaimTrackingClient(busy_on_calls={1})

    dialog = QualityTestDialog(_parent(), client, "tester", "right-index-finger")
    verdict = dialog.run()

    assert verdict is None
    assert dialog.busy is True
    assert client.depth == 0
    assert client.max_depth == 0


def test_quality_dialog_claim_release_balances_when_cancelled_mid_operation():
    client = ClaimTrackingClient()
    dialog = QualityTestDialog(_parent(), client, "tester", "right-index-finger")
    client.mid_operation_hook = dialog.close

    verdict = dialog.run()

    assert verdict is None
    assert client.depth == 0
    assert client.max_depth == 1
