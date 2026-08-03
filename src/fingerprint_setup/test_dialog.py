"""Runs ten verifications and reports how the enrolment actually performs."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from fingerprint_setup.client import FingerprintClient
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
        self._client.claim(self._username)
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
