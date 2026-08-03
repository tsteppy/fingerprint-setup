"""Guides the user through one enrolment, position by position."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from fingerprint_setup.client import FingerprintClient
from fingerprint_setup.enrollment import EnrollmentCoach
from fingerprint_setup.fingertip_map import FingertipMap
from fingerprint_setup.fprintd_client import DeviceBusyError


class EnrollDialog(Adw.Window):
    def __init__(
        self,
        parent: Gtk.Window,
        client: FingerprintClient,
        username: str,
        finger: str,
    ) -> None:
        super().__init__(transient_for=parent, modal=True)
        self.set_title("Enrol a finger")
        self.set_default_size(420, 560)

        self._client = client
        self._username = username
        self._finger = finger
        self._coach = EnrollmentCoach(client.num_enroll_stages, client.scan_type)
        self._completed = False
        self._cancelled = False
        # Set from the terminal CoachEvent's message (or, if the reader was
        # taken before we could claim it, a busy message) so the caller can
        # tell the user what actually happened -- previously this was
        # computed and then discarded, leaving the user to guess.
        self._final_message: str | None = None

        self._map = FingertipMap()
        self._instruction = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self._instruction.add_css_class("title-3")
        self._counter = Gtk.Label()
        self._counter.add_css_class("dim-label")
        self._legend = Gtk.Label(label="Positions completed")
        self._legend.add_css_class("caption")
        self._legend.add_css_class("dim-label")
        self._progress = Gtk.ProgressBar(show_text=False)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)
        box.append(self._counter)
        box.append(self._map)
        box.append(self._legend)
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

        # Covers dismissal via the window manager / titlebar close button or
        # Escape, which goes through this signal rather than through close().
        self.connect("close-request", self._on_close_request)

        self._refresh()

    def _maybe_cancel(self) -> None:
        """Stop any in-flight enrolment unless it already finished on its own.

        Called from every dismissal path (Cancel button, close-request,
        `run()`'s own final `close()`). `enroll_stop()` is safe to call
        even when nothing is running -- it no-ops without an active loop.
        Only mark the dialog as cancelled if the coach had not already
        reached a terminal state, so a normal successful/failed finish is
        not mistaken for the user cancelling.
        """
        if not self._coach.finished:
            self._cancelled = True
        self._client.enroll_stop()

    def _on_close_request(self, _window) -> bool:
        self._maybe_cancel()
        return False

    def close(self) -> None:
        self._maybe_cancel()
        Gtk.Window.close(self)

    def _refresh(self) -> None:
        position = self._coach.current
        self._instruction.set_text(position.instruction)
        self._counter.set_text(
            f"Press {min(self._coach.completed + 1, self._coach.total)} "
            f"of {self._coach.total}"
        )
        self._map.set_completed(self._coach.completed_zones)
        self._map.set_target(position.map_zone)
        self._progress.set_fraction(
            self._coach.completed / self._coach.total if self._coach.total else 0
        )

    def _on_status(self, result: str, done: bool) -> None:
        event = self._coach.on_status(result, done)
        if event.kind == "retry":
            self._instruction.set_text(event.message)
        else:
            self._refresh()
        if event.kind == "completed":
            self._completed = True
        if event.kind in ("completed", "duplicate", "failed"):
            self._final_message = event.message
        # let the UI repaint between presses
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)

    @property
    def final_message(self) -> str | None:
        """What happened, in words -- set once the dialog has a terminal
        outcome (success, duplicate, failure, cancellation or a busy
        reader). None only if run() has not returned yet.
        """
        return self._final_message

    def run(self) -> bool:
        """Enrol, blocking until fprintd reports the operation is done."""
        self.present()
        try:
            self._client.claim(self._username)
        except DeviceBusyError:
            self._final_message = (
                "The fingerprint reader is in use -- try again in a moment."
            )
            self.close()
            return False
        try:
            self._client.enroll_start(self._finger, self._on_status)
        finally:
            self._client.release()
        self.close()
        if self._cancelled:
            if self._final_message is None:
                self._final_message = "Enrolment was cancelled."
            return False
        return self._completed
