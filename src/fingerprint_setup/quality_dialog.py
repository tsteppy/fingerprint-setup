"""Runs ten verifications and reports how the enrolment actually performs."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from fingerprint_setup.client import FingerprintClient
from fingerprint_setup.fprintd_client import DeviceBusyError
from fingerprint_setup.quality import TEST_PROMPTS, QualityTest, Verdict

BAND_STYLE = {"good": "success", "fair": "warning", "weak": "error"}


class QualityTestDialog(Adw.Window):
    def __init__(
        self,
        parent: Gtk.Window,
        client: FingerprintClient,
        username: str,
        finger: str,
    ) -> None:
        super().__init__(transient_for=parent, modal=True)
        self.set_title("Test this enrolment")
        self.set_default_size(420, 340)

        self._client = client
        self._username = username
        self._finger = finger
        self._test = QualityTest()
        self._verdict: Verdict | None = None
        self._cancelled = False
        # True only when run() had to bail out because the reader was taken
        # before we could claim it -- distinct from a normal cancellation,
        # so the caller can tell the two apart even though both make run()
        # return None.
        self.busy = False

        self._instruction = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self._instruction.add_css_class("title-2")
        self._counter = Gtk.Label()
        self._counter.add_css_class("dim-label")
        self._progress = Gtk.ProgressBar(show_text=False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        for edge in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{edge}")(24)
        box.set_valign(Gtk.Align.CENTER)
        box.append(self._counter)
        box.append(self._instruction)
        box.append(self._progress)

        header = Adw.HeaderBar()
        cancel = Gtk.Button(label="Cancel")
        cancel.connect("clicked", lambda _b: self.close())
        header.pack_start(cancel)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(box)
        self.set_content(toolbar)

        # Every dismissal path -- the Cancel button, Escape, the title-bar
        # close -- must stop the operation, not just hide the window. run()
        # is blocked inside verify_start(), which holds the fprintd claim;
        # a claim left held makes the reader unusable for every other
        # application on the machine, including the login screen. This
        # mirrors EnrollDialog's _maybe_cancel/close override so both
        # dialogs handle cancellation the same way.
        self.connect("close-request", self._on_close_request)

        self._refresh()

    def _maybe_cancel(self) -> None:
        """Stop any in-flight verification unless the test already finished.

        Called from every dismissal path (Cancel button, close-request,
        `run()`'s own final `close()`). `verify_stop()` is safe to call even
        when nothing is running -- it no-ops without an active loop. Only
        mark the dialog as cancelled if the test had not already reached
        its final press, so a normal finish is not mistaken for the user
        cancelling.
        """
        if not self._test.finished:
            self._cancelled = True
        self._client.verify_stop()

    def _on_close_request(self, _window) -> bool:
        self._maybe_cancel()
        return False

    def close(self) -> None:
        self._maybe_cancel()
        Gtk.Window.close(self)

    def _refresh(self) -> None:
        self._counter.set_text(
            f"Press {min(self._test.index + 1, len(TEST_PROMPTS))} of {len(TEST_PROMPTS)}"
        )
        self._instruction.set_text(self._test.current.instruction)
        self._progress.set_fraction(self._test.index / len(TEST_PROMPTS))

    def run(self) -> Verdict | None:
        self.present()
        try:
            self._client.claim(self._username)
        except DeviceBusyError:
            self.busy = True
            self.close()
            return None
        try:
            while not self._test.finished and not self._cancelled:
                self._refresh()
                while GLib.MainContext.default().pending():
                    GLib.MainContext.default().iteration(False)

                outcome: list[str] = []
                self._client.verify_start(
                    self._finger, lambda result, done: outcome.append(result)
                )
                # A cancellation that arrives mid-press (e.g. after fprintd
                # has already delivered a non-final status such as
                # verify-retry-scan, which leaves `outcome` non-empty) must
                # not be recorded as a result -- check _cancelled before
                # consulting `outcome` at all.
                if self._cancelled:
                    break
                if not outcome:
                    break
                self._test.record(outcome[-1])
        finally:
            self._client.release()

        if self._test.finished:
            self._verdict = self._test.verdict()
        self.close()
        if self._cancelled:
            return None
        return self._verdict


class ResultDialog(Adw.Window):
    """Shows a finished quality test's verdict: headline, the natural/offset
    match breakdown, and the advice -- the whole reason the test ran.

    A toast could not carry this (Adw.Toast has no add_css_class -- it is a
    GObject.Object, not a Gtk.Widget -- so applying BAND_STYLE to a toast
    raises AttributeError before the toast is ever shown) and a six-second
    toast could not have held this much text anyway.
    """

    def __init__(self, parent: Gtk.Window, verdict: Verdict) -> None:
        super().__init__(transient_for=parent, modal=True)
        self.set_title("Test result")
        self.set_default_size(420, 360)

        status = Adw.StatusPage(
            title=verdict.headline,
            icon_name={
                "good": "emblem-ok-symbolic",
                "fair": "dialog-warning-symbolic",
                "weak": "dialog-error-symbolic",
            }.get(verdict.band, "dialog-information-symbolic"),
        )

        counts = Gtk.Label(
            label=(
                f"{verdict.matches} of {verdict.total} matched "
                f"({verdict.natural_matches} of 6 natural presses, "
                f"{verdict.offset_matches} of 4 offset presses)"
            ),
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        counts.add_css_class("title-4")
        style = BAND_STYLE.get(verdict.band)
        if style:
            counts.add_css_class(style)

        advice = Gtk.Label(
            label=verdict.advice,
            wrap=True,
            justify=Gtk.Justification.CENTER,
        )
        advice.add_css_class("body")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for edge in ("top", "bottom", "start", "end"):
            getattr(body, f"set_margin_{edge}")(12)
        body.append(counts)
        body.append(advice)
        status.set_child(body)

        header = Adw.HeaderBar()
        close = Gtk.Button(label="Close")
        close.connect("clicked", lambda _b: self.close())
        header.pack_end(close)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(status)
        self.set_content(toolbar)
