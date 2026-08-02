"""Runs verifications against a finished enrolment and scores the result.

Ten presses is a rough sample, not a false-reject measurement, and the
wording here is deliberately hedged to match. Six presses are natural and
four deliberately offset, so a narrow-but-usable enrolment can be told apart
from one that simply does not work.
"""

from dataclasses import dataclass

from fingerprint_setup.client import VERIFY_MATCH


@dataclass(frozen=True)
class TestPrompt:
    kind: str
    instruction: str


@dataclass(frozen=True)
class Verdict:
    band: str
    matches: int
    total: int
    natural_matches: int
    offset_matches: int
    headline: str
    advice: str


TEST_PROMPTS: list[TestPrompt] = [
    *[TestPrompt("natural", "Press as you normally would") for _ in range(6)],
    TestPrompt("offset", "Press with nearer the tip of your finger"),
    TestPrompt("offset", "Press with nearer the knuckle"),
    TestPrompt("offset", "Press slightly to the left"),
    TestPrompt("offset", "Press slightly to the right"),
]


class QualityTest:
    def __init__(self) -> None:
        self._results: list[tuple[str, bool]] = []

    @property
    def index(self) -> int:
        return len(self._results)

    @property
    def current(self) -> TestPrompt:
        return TEST_PROMPTS[min(self.index, len(TEST_PROMPTS) - 1)]

    @property
    def finished(self) -> bool:
        return len(self._results) >= len(TEST_PROMPTS)

    def record(self, result: str) -> None:
        prompt = TEST_PROMPTS[min(self.index, len(TEST_PROMPTS) - 1)]
        self._results.append((prompt.kind, result == VERIFY_MATCH))

    def verdict(self) -> Verdict:
        if not self.finished:
            raise RuntimeError("test is not finished")

        natural = sum(1 for kind, ok in self._results if kind == "natural" and ok)
        offset = sum(1 for kind, ok in self._results if kind == "offset" and ok)
        matches = natural + offset
        total = len(self._results)

        if matches >= 9:
            band = "good"
            headline = "Your enrolment looks solid"
            advice = "Ready to use for logging in."
        elif matches >= 7:
            band = "fair"
            headline = "Your enrolment works, with occasional retries"
            advice = "Usable. Re-enrolling with wider coverage would make it more reliable."
        else:
            band = "weak"
            headline = "Your enrolment is unreliable"
            advice = "Re-enrol, covering more of your fingertip each press."

        if natural >= 5 and offset <= 1:
            advice = (
                "Your usual press works well, but the enrolment is narrow — "
                "presses that land off-centre fail. Re-enrol covering more of "
                "your fingertip if you want it to be more forgiving."
            )

        return Verdict(
            band=band,
            matches=matches,
            total=total,
            natural_matches=natural,
            offset_matches=offset,
            headline=headline,
            advice=advice,
        )
