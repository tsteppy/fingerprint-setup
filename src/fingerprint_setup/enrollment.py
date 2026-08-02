"""Decides what to ask the user to do next while enrolling.

Small-area readers only match a press that lands on skin the enrolment
covered. Eight presses at one comfortable position measured a 60% false
reject rate on the reader that motivated this app; the same eight spread
across the fingertip measured 10%. This module is what spreads them.
"""

from dataclasses import dataclass

from fingerprint_setup.client import (
    ENROLL_COMPLETED,
    ENROLL_DISCONNECTED,
    ENROLL_DUPLICATE,
    ENROLL_FAILED,
    RETRY_MESSAGES,
    RETRY_RESULTS,
    STAGE_PASSED,
)


@dataclass(frozen=True)
class Position:
    key: str
    instruction: str
    map_zone: str


@dataclass(frozen=True)
class CoachEvent:
    kind: str
    message: str


BASE_POSITIONS: list[Position] = [
    Position("centred", "Flat and centred — your normal unlock press", "centre"),
    Position("tip", "Slide up, so the reader sees nearer the tip", "top"),
    Position("knuckle", "Slide down, so the reader sees nearer the knuckle", "bottom"),
    Position("left", "Shift left", "left"),
    Position("right", "Shift right", "right"),
    Position("roll-left", "Roll your finger onto its left side", "roll-left"),
    Position("roll-right", "Roll your finger onto its right side", "roll-right"),
    Position("centred-again", "Flat and centred again, at a slightly different angle", "centre-2"),
]

SWIPE_POSITIONS: list[Position] = [
    Position("swipe-centred", "Swipe with the centre of your fingertip", "centre"),
    Position("swipe-left", "Swipe slightly to the left of centre", "left"),
    Position("swipe-right", "Swipe slightly to the right of centre", "right"),
    Position("swipe-tip", "Swipe using nearer the tip of your finger", "top"),
]


def build_sequence(num_stages: int, scan_type: str = "press") -> list[Position]:
    """Produce exactly `num_stages` positions.

    The device decides how many presses it needs, so the sequence is fitted
    to it rather than the other way round. Fewer stages than positions takes
    an evenly spaced sample that always begins centred; more stages cycles
    the list.
    """
    base = SWIPE_POSITIONS if scan_type == "swipe" else BASE_POSITIONS
    if num_stages <= 0:
        return []
    if num_stages == len(base):
        return list(base)
    if num_stages < len(base):
        # always start centred, then spread the remainder evenly
        step = len(base) / num_stages
        return [base[min(int(i * step), len(base) - 1)] for i in range(num_stages)]
    return [base[i % len(base)] for i in range(num_stages)]


class EnrollmentCoach:
    def __init__(self, num_stages: int, scan_type: str = "press") -> None:
        self._sequence = build_sequence(num_stages, scan_type)
        self._index = 0
        self._completed_zones: list[str] = []
        self.finished = False

    @property
    def current(self) -> Position:
        if not self._sequence:
            raise RuntimeError("device reported no enrolment stages")
        return self._sequence[min(self._index, len(self._sequence) - 1)]

    @property
    def completed(self) -> int:
        return len(self._completed_zones)

    @property
    def total(self) -> int:
        return len(self._sequence)

    @property
    def completed_zones(self) -> list[str]:
        return list(self._completed_zones)

    def on_status(self, result: str, done: bool) -> CoachEvent:
        if result in RETRY_RESULTS:
            return CoachEvent(
                "retry",
                RETRY_MESSAGES.get(result, "That press did not register — try again."),
            )
        if result == STAGE_PASSED:
            self._completed_zones.append(self.current.map_zone)
            self._index += 1
            return CoachEvent("advanced", self.current.instruction)
        if result == ENROLL_COMPLETED:
            self.finished = True
            return CoachEvent("completed", "Finger enrolled.")
        if result == ENROLL_DUPLICATE:
            self.finished = True
            return CoachEvent(
                "duplicate", "That finger is already enrolled on this reader."
            )
        if result == ENROLL_DISCONNECTED:
            self.finished = True
            return CoachEvent("failed", "The reader disconnected.")
        if result == ENROLL_FAILED or done:
            self.finished = True
            return CoachEvent("failed", "Enrolment failed. Try again.")
        return CoachEvent("retry", "That press did not register — try again.")
