"""The interface every fingerprint backend satisfies.

Two implementations exist: `FprintdClient`, which talks to fprintd over
D-Bus, and `FakeClient`, which is scripted in memory. Everything else in the
application is written against this protocol, which is what allows the whole
app to run and be tested without a fingerprint reader.
"""

from typing import Callable, Protocol, runtime_checkable

# Results fprintd reports through EnrollStatus and VerifyStatus.
STAGE_PASSED = "enroll-stage-passed"
ENROLL_COMPLETED = "enroll-completed"
ENROLL_FAILED = "enroll-failed"
ENROLL_DUPLICATE = "enroll-duplicate"
ENROLL_DISCONNECTED = "enroll-disconnected"
VERIFY_MATCH = "verify-match"
VERIFY_NO_MATCH = "verify-no-match"
VERIFY_RETRY = "verify-retry-scan"

# A retry means the press was not usable. The coaching sequence must NOT
# advance on these -- advancing would silently destroy the coverage this
# application exists to produce.
RETRY_RESULTS = frozenset(
    {
        "enroll-retry-scan-too-short",
        "enroll-retry-center-finger",
        "enroll-retry-remove-finger",
        "enroll-swipe-too-short",
        "enroll-finger-not-centered",
        "enroll-remove-and-retry",
    }
)

RETRY_MESSAGES = {
    "enroll-retry-scan-too-short": "That press was too brief — hold a moment longer.",
    "enroll-retry-center-finger": "Not enough of your finger reached the reader — press flatter.",
    "enroll-retry-remove-finger": "Lift your finger, then press again.",
    "enroll-swipe-too-short": "That swipe was too short — try a longer one.",
    "enroll-finger-not-centered": "Centre your finger a little more on the reader.",
    "enroll-remove-and-retry": "Lift your finger, then press again.",
}

StatusCallback = Callable[[str, bool], None]


@runtime_checkable
class FingerprintClient(Protocol):
    """A fingerprint reader, real or simulated."""

    @property
    def num_enroll_stages(self) -> int:
        """How many successful presses the device needs to enrol."""

    @property
    def device_name(self) -> str: ...

    @property
    def scan_type(self) -> str:
        """Either "press" or "swipe"."""

    def claim(self, username: str) -> None: ...

    def release(self) -> None: ...

    def list_enrolled(self, username: str) -> list[str]: ...

    def delete_finger(self, finger: str) -> None: ...

    def enroll_start(self, finger: str, on_status: StatusCallback) -> None: ...

    def enroll_stop(self) -> None: ...

    def verify_start(self, finger: str, on_status: StatusCallback) -> None: ...

    def verify_stop(self) -> None: ...
