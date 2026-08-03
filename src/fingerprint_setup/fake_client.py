"""An in-memory fingerprint reader for tests and for --simulate.

Results are queued by the caller, so a test can reproduce any sequence of
stage passes, retries and failures without hardware.
"""

import time

from fingerprint_setup.client import (
    ENROLL_COMPLETED,
    RETRY_RESULTS,
    STAGE_PASSED,
    StatusCallback,
    VERIFY_MATCH,
)


class FakeClient:
    def __init__(
        self,
        num_enroll_stages: int = 8,
        device_name: str = "Fake Reader",
        scan_type: str = "press",
        stage_delay: float = 0.0,
    ) -> None:
        self._num_enroll_stages = num_enroll_stages
        self._device_name = device_name
        self._scan_type = scan_type
        # Real fprintd delivers each EnrollStatus signal as its own D-Bus
        # round trip, so the dialogs get a chance to repaint between them.
        # Left at the default of 0, every enroll_start() stage fires back
        # to back with no pause -- fine for tests, but it means --simulate
        # flashes both dialogs open and closed instantly and neither can
        # actually be reviewed. main() passes a small delay for
        # --simulate; tests never do, so they stay fast.
        self._stage_delay = stage_delay
        self._claimed_by: str | None = None
        self._enrolled: dict[str, list[str]] = {}
        self._enroll_queue: list[str] = []
        self._verify_queue: list[str] = []
        self.released = False

    @property
    def num_enroll_stages(self) -> int:
        return self._num_enroll_stages

    @property
    def device_name(self) -> str:
        return self._device_name

    @property
    def scan_type(self) -> str:
        return self._scan_type

    def queue_enroll_results(self, results: list[str]) -> None:
        self._enroll_queue.extend(results)

    def queue_verify_results(self, results: list[str]) -> None:
        self._verify_queue.extend(results)

    def _require_claim(self) -> str:
        if self._claimed_by is None:
            raise RuntimeError("device is not claimed")
        return self._claimed_by

    def claim(self, username: str) -> None:
        self._claimed_by = username
        self._enrolled.setdefault(username, [])

    def release(self) -> None:
        self._claimed_by = None
        self.released = True

    def list_enrolled(self, username: str) -> list[str]:
        return list(self._enrolled.get(username, []))

    def delete_finger(self, finger: str) -> None:
        username = self._require_claim()
        self._enrolled[username] = [
            f for f in self._enrolled.get(username, []) if f != finger
        ]

    def enroll_start(self, finger: str, on_status: StatusCallback) -> None:
        username = self._require_claim()
        results = self._enroll_queue or [
            *[STAGE_PASSED] * (self._num_enroll_stages - 1),
            ENROLL_COMPLETED,
        ]
        self._enroll_queue = []
        for result in results:
            done = result not in (STAGE_PASSED,) and result not in RETRY_RESULTS
            on_status(result, done)
            if result == ENROLL_COMPLETED:
                fingers = self._enrolled.setdefault(username, [])
                if finger not in fingers:
                    fingers.append(finger)
            if self._stage_delay:
                # on_status() above already pumped the GTK main loop (see
                # EnrollDialog._on_status), so the frame for this stage is
                # already on screen -- a plain sleep here is enough to make
                # it watchable instead of needing its own event pumping.
                time.sleep(self._stage_delay)

    def enroll_stop(self) -> None:
        pass

    def verify_start(self, finger: str, on_status: StatusCallback) -> None:
        self._require_claim()
        result = self._verify_queue.pop(0) if self._verify_queue else VERIFY_MATCH
        on_status(result, True)

    def verify_stop(self) -> None:
        pass
