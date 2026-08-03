"""The fingerprint manager: what is enrolled, and what you can do about it."""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from fingerprint_setup.client import FingerprintClient
from fingerprint_setup.enroll_dialog import EnrollDialog
from fingerprint_setup.fprintd_client import DeviceBusyError
from fingerprint_setup.pam_status import COMMANDS, detect_pam_status
from fingerprint_setup.quality_dialog import QualityTestDialog, ResultDialog

# The window only ever imports this module for the DeviceBusyError type --
# never a concrete client -- so it never touches D-Bus. Importing
# fprintd_client at module scope only pulls in Gio/GLib symbols, which
# PyGObject already provides as a hard dependency of Gtk/Adw, so this stays
# safe on a machine with no fprintd at all (--simulate never calls anything
# in fprintd_client; it only needs the exception class to exist).

FINGER_LABELS = {
    "left-thumb": "Left thumb",
    "left-index-finger": "Left index finger",
    "left-middle-finger": "Left middle finger",
    "left-ring-finger": "Left ring finger",
    "left-little-finger": "Left little finger",
    "right-thumb": "Right thumb",
    "right-index-finger": "Right index finger",
    "right-middle-finger": "Right middle finger",
    "right-ring-finger": "Right ring finger",
    "right-little-finger": "Right little finger",
}

# Distribution families detect_pam_status() can name but has no command for.
# Its own `explanation` text says "could not determine how your distribution
# manages PAM", which is wrong once the family *is* known -- there is simply
# no command wired up for it yet. Render that case honestly here instead of
# repeating the misleading text, without touching pam_status.py. Derived
# from COMMANDS in pam_status.py rather than hardcoded, so a new
# no-command-yet family added there is picked up automatically instead of
# needing this set edited in lockstep: every family with an empty command
# tuple, other than the genuinely-undetected "unknown" bucket.
_KNOWN_UNSUPPORTED_FAMILIES = {
    family
    for family, (enable, disable) in COMMANDS.items()
    if not enable and not disable and family != "unknown"
}


def fetch_enrolled_fingers(
    client: FingerprintClient, username: str
) -> tuple[list[str], bool]:
    """Claim the reader and list what is enrolled.

    Returns `(fingers, busy)`. `busy` is True when another process (the
    login greeter, another copy of this app, an in-flight
    `fprintd-verify`) already holds the claim -- `DeviceBusyError` is
    caught here rather than left to propagate, so callers never need a
    live GTK window or display to exercise this path. Only claims that
    succeed are released; a failed claim holds nothing to release.
    """
    try:
        client.claim(username)
    except DeviceBusyError:
        return [], True
    try:
        return client.list_enrolled(username), False
    finally:
        client.release()


def delete_finger_safe(client: FingerprintClient, username: str, finger: str) -> bool:
    """Claim the reader and delete `finger`. Returns False if it was busy.

    Mirrors `fetch_enrolled_fingers`: `DeviceBusyError` from `claim()` is
    reported through the return value instead of raised, so this is
    testable without a display and so callers can show a toast instead of
    crashing.
    """
    try:
        client.claim(username)
    except DeviceBusyError:
        return False
    try:
        client.delete_finger(finger)
    finally:
        client.release()
    return True


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self, app: Adw.Application, client: FingerprintClient, username: str
    ) -> None:
        super().__init__(application=app)
        self.set_title("Fingerprint Setup")
        self.set_default_size(460, 560)

        self._client = client
        self._username = username

        self._fingers_group = Adw.PreferencesGroup(title="Enrolled fingers")
        self._pam_group = Adw.PreferencesGroup(title="Fingerprint login")
        # Adw.PreferencesGroup wraps each added row in an internal Box, so
        # get_first_child() on the group does not return the rows that were
        # add()-ed -- remove() only accepts the exact widget add() was given.
        # Track what we add so _rebuild() can remove exactly that.
        self._finger_rows: list[Gtk.Widget] = []
        self._pam_rows: list[Gtk.Widget] = []

        # Enrolling needs to know WHICH finger, so the button opens a picker
        # listing only fingers that are not already enrolled.
        self._picker = Gtk.Popover()
        add_button = Gtk.MenuButton(label="Enrol a finger", popover=self._picker)
        add_button.add_css_class("suggested-action")

        page = Adw.PreferencesPage()
        page.add(self._fingers_group)
        page.add(self._pam_group)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.append(page)
        button_row = Gtk.Box(halign=Gtk.Align.CENTER)
        button_row.set_margin_bottom(18)
        button_row.append(add_button)
        content.append(button_row)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Fingerprint Setup",
                                                subtitle=client.device_name))
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(header)
        toolbar.set_content(content)

        # Toasts require this wrapper; without it verdicts silently go nowhere.
        self._toasts = Adw.ToastOverlay()
        self._toasts.set_child(toolbar)
        self.set_content(self._toasts)

        self._render_fingers()
        self._render_pam()

    # -- rendering ------------------------------------------------------

    def _render_fingers(self) -> None:
        fingers, busy = fetch_enrolled_fingers(self._client, self._username)

        if busy:
            # Reader held elsewhere (login greeter, another copy of this
            # app, an in-flight fprintd-verify). Show it without raising --
            # this is called from __init__ and from every _rebuild(), so an
            # uncaught DeviceBusyError here used to kill the whole app.
            row = Adw.ActionRow(
                title="The fingerprint reader is in use",
                subtitle=(
                    "Another application is using it right now -- for "
                    "example a login prompt. Try again in a moment."
                ),
            )
            retry = Gtk.Button(label="Retry")
            retry.set_valign(Gtk.Align.CENTER)
            retry.connect("clicked", lambda _b: self._rebuild())
            row.add_suffix(retry)
            self._fingers_group.add(row)
            self._finger_rows.append(row)
            self._picker.set_child(
                Gtk.Label(
                    label="The reader is in use",
                    margin_top=8,
                    margin_bottom=8,
                    margin_start=12,
                    margin_end=12,
                )
            )
            return

        self._populate_picker(fingers)

        if not fingers:
            row = Adw.ActionRow(
                title="No fingers enrolled",
                subtitle="Enrol one to use your fingerprint to log in",
            )
            self._fingers_group.add(row)
            self._finger_rows.append(row)
            return

        for finger in fingers:
            row = Adw.ActionRow(title=FINGER_LABELS.get(finger, finger))

            test = Gtk.Button(label="Test")
            test.set_valign(Gtk.Align.CENTER)
            test.connect("clicked", self._on_test_clicked, finger)
            row.add_suffix(test)

            delete = Gtk.Button(icon_name="user-trash-symbolic")
            delete.set_valign(Gtk.Align.CENTER)
            delete.add_css_class("flat")
            delete.connect("clicked", self._on_delete_clicked, finger)
            row.add_suffix(delete)

            self._fingers_group.add(row)
            self._finger_rows.append(row)

    def _render_pam(self) -> None:
        status = detect_pam_status()
        command = status.disable_command if status.enabled else status.enable_command

        # detect_pam_status() names the distribution family even when it has
        # no command for it (family="arch" or "unknown" both carry empty
        # commands), but its explanation text is written only for the
        # genuinely-unknown case. Don't tell the user we couldn't figure out
        # their distribution when we did -- we just don't have a command for
        # it yet.
        if not command and status.family in _KNOWN_UNSUPPORTED_FAMILIES:
            subtitle = (
                f"This app detected a {status.family}-family distribution, but "
                "does not yet know the command for managing fingerprint login "
                "on it. See your distribution's documentation for enabling "
                "pam_fprintd."
            )
        else:
            subtitle = status.explanation

        row = Adw.ActionRow(
            title="Fingerprint login is "
            + ("on" if status.enabled else "off"),
            subtitle=subtitle,
        )
        if command:
            copy = Gtk.Button(icon_name="edit-copy-symbolic")
            copy.set_valign(Gtk.Align.CENTER)
            copy.set_tooltip_text(f"Copy: {command}")
            copy.connect("clicked", self._on_copy_command, command)
            row.add_suffix(copy)
        self._pam_group.add(row)
        self._pam_rows.append(row)

    def _populate_picker(self, enrolled: list[str]) -> None:
        """Offer every finger that is not already enrolled."""
        listbox = Gtk.ListBox()
        listbox.add_css_class("navigation-sidebar")
        available = [f for f in FINGER_LABELS if f not in enrolled]

        if not available:
            listbox.append(Gtk.Label(label="Every finger is enrolled", margin_top=8,
                                     margin_bottom=8, margin_start=12, margin_end=12))
        else:
            for finger in available:
                row = Gtk.ListBoxRow()
                row.set_child(Gtk.Label(label=FINGER_LABELS[finger], xalign=0,
                                        margin_top=6, margin_bottom=6,
                                        margin_start=10, margin_end=10))
                row.finger = finger  # type: ignore[attr-defined]
                listbox.append(row)
            listbox.connect("row-activated", self._on_finger_chosen)

        # Propagate the natural width as well as the height, or the popover
        # collapses to its minimum and truncates labels like "Right middle
        # finger". The floor keeps the list from looking cramped when only
        # short labels remain.
        scroller = Gtk.ScrolledWindow(propagate_natural_height=True,
                                      propagate_natural_width=True,
                                      min_content_width=200,
                                      max_content_height=320)
        scroller.set_child(listbox)
        self._picker.set_child(scroller)

    # -- actions --------------------------------------------------------

    def _on_finger_chosen(self, _listbox, row) -> None:
        self._picker.popdown()
        dialog = EnrollDialog(self, self._client, self._username, row.finger)
        succeeded = dialog.run()
        message = dialog.final_message
        if message:
            toast = Adw.Toast(title=message if succeeded else f"Not enrolled: {message}")
            toast.set_timeout(6)
            self._toast_overlay_show(toast)
        self._rebuild()

    def _on_test_clicked(self, _button, finger: str) -> None:
        dialog = QualityTestDialog(self, self._client, self._username, finger)
        verdict = dialog.run()
        if verdict is None:
            if dialog.busy:
                toast = Adw.Toast(
                    title="The fingerprint reader is in use -- try again in a moment."
                )
                toast.set_timeout(6)
                self._toast_overlay_show(toast)
            return
        ResultDialog(self, verdict).present()

    def _on_delete_clicked(self, _button, finger: str) -> None:
        deleted = delete_finger_safe(self._client, self._username, finger)
        if not deleted:
            toast = Adw.Toast(
                title="The fingerprint reader is in use — the finger was not deleted."
            )
            toast.set_timeout(6)
            self._toast_overlay_show(toast)
            return
        self._rebuild()

    def _on_copy_command(self, _button, command: str) -> None:
        self.get_clipboard().set(command)

    def _toast_overlay_show(self, toast: Adw.Toast) -> None:
        self._toasts.add_toast(toast)

    def _rebuild(self) -> None:
        """Refresh the finger list and PAM row in place.

        A rebuild-by-recreate (close this window, construct a new
        MainWindow, present it) was the original approach, but closing
        `self` while a caller further up the stack (`_on_finger_chosen`,
        `_on_delete_clicked`) still holds a reference to `self` invites use
        of a disposed GTK widget once those methods return, and there is no
        need to tear down the whole window -- and the toplevel, its header
        bar and its toast overlay -- just to redraw two lists. Clearing and
        repopulating the existing groups is the smaller, equally correct
        fix.

        Adw.PreferencesGroup.remove() only accepts the exact widget that was
        passed to add() (it wraps each row internally, so
        get_first_child()/iterate-the-widget-tree does not find them) --
        hence the explicit `_finger_rows`/`_pam_rows` bookkeeping instead of
        walking the group's own child list.
        """
        for row in self._finger_rows:
            self._fingers_group.remove(row)
        self._finger_rows.clear()
        for row in self._pam_rows:
            self._pam_group.remove(row)
        self._pam_rows.clear()

        self._render_fingers()
        self._render_pam()
