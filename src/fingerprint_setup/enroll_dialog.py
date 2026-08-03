"""Guides the user through one enrolment, position by position."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from fingerprint_setup.client import FingerprintClient
from fingerprint_setup.enrollment import EnrollmentCoach
from fingerprint_setup.fingertip_map import FingertipMap


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

        self._refresh()

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
        # let the UI repaint between presses
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)

    def run(self) -> bool:
        """Enrol, blocking until fprintd reports the operation is done."""
        self.present()
        self._client.claim(self._username)
        try:
            self._client.enroll_start(self._finger, self._on_status)
        finally:
            self._client.release()
        self.close()
        return self._completed
