"""Entry point. Use --simulate to run without a fingerprint reader."""

import getpass
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from fingerprint_setup.window import MainWindow

APP_ID = "io.github.tsteppy.FingerprintSetup"


class FingerprintSetupApp(Adw.Application):
    def __init__(self, client_factory) -> None:
        super().__init__(application_id=APP_ID)
        self._client_factory = client_factory
        self._window: MainWindow | None = None

    def do_activate(self) -> None:
        if self._window is None:
            # The factory call (which for the real client only reaches
            # fprintd's Manager, not a specific device) can't raise
            # DeviceBusyError -- the first Claim happens inside
            # MainWindow.__init__ (via _render_fingers), which catches it
            # itself (fetch_enrolled_fingers), so DeviceBusyError never
            # reaches here. Any other startup failure (no fprintd running
            # at all, ServiceUnknown, no reader present, ...) must produce
            # a message, not an uncaught exception through this GObject
            # vfunc.
            try:
                client = self._client_factory()
                self._window = MainWindow(self, client, getpass.getuser())
            except Exception as error:  # noqa: BLE001 - shown to the user
                self._show_error(str(error))
                return
        self._window.present()

    def _show_error(self, message: str) -> None:
        window = Adw.ApplicationWindow(application=self)
        window.set_title("Fingerprint Setup")
        window.set_default_size(420, 240)
        status = Adw.StatusPage(
            title="Fingerprint Setup could not start",
            description=message,
            icon_name="dialog-warning-symbolic",
        )
        window.set_content(status)
        window.present()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    simulate = "--simulate" in argv
    if simulate:
        argv.remove("--simulate")
        from fingerprint_setup.fake_client import FakeClient

        # A short per-stage delay so the enrol/test dialogs are actually
        # watchable under --simulate instead of flashing open and closed --
        # see FakeClient.__init__ for why the default (used by tests) is 0.
        factory = lambda: FakeClient(num_enroll_stages=8, stage_delay=0.6)  # noqa: E731
    else:
        from fingerprint_setup.fprintd_client import default_device

        factory = default_device

    app = FingerprintSetupApp(factory)
    return app.run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
