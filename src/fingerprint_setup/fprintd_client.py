"""The only module that talks to fprintd.

fprintd delivers enrol and verify progress as D-Bus signals rather than
return values, so each operation registers a callback, runs a nested main
loop until fprintd reports `done`, and then disconnects. Keeping that
awkwardness in one file is what lets the rest of the app stay synchronous
and testable.
"""

from gi.repository import Gio, GLib

from fingerprint_setup.client import StatusCallback

BUS_NAME = "net.reactivated.Fprint"
MANAGER_PATH = "/net/reactivated/Fprint/Manager"
MANAGER_IFACE = "net.reactivated.Fprint.Manager"
DEVICE_IFACE = "net.reactivated.Fprint.Device"
PROPS_IFACE = "org.freedesktop.DBus.Properties"


class NoDeviceError(Exception):
    """fprintd reported no fingerprint reader."""


class DeviceBusyError(Exception):
    """Another application is using the reader."""


class FprintdClient:
    def __init__(self, object_path: str) -> None:
        self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self._path = object_path
        self._proxy = Gio.DBusProxy.new_sync(
            self._bus,
            Gio.DBusProxyFlags.NONE,
            None,
            BUS_NAME,
            object_path,
            DEVICE_IFACE,
            None,
        )
        self._claimed = False

    # -- properties -----------------------------------------------------

    def _get_property(self, name: str):
        value = self._proxy.get_cached_property(name)
        return value.unpack() if value is not None else None

    @property
    def num_enroll_stages(self) -> int:
        return int(self._get_property("num-enroll-stages") or 0)

    @property
    def device_name(self) -> str:
        return str(self._get_property("name") or "Fingerprint reader")

    @property
    def scan_type(self) -> str:
        return str(self._get_property("scan-type") or "press")

    # -- lifecycle ------------------------------------------------------

    def claim(self, username: str) -> None:
        try:
            self._proxy.call_sync(
                "Claim", GLib.Variant("(s)", (username,)), Gio.DBusCallFlags.NONE, -1, None
            )
        except GLib.Error as error:
            if "AlreadyInUse" in error.message or "in use" in error.message.lower():
                raise DeviceBusyError(error.message) from error
            raise
        self._claimed = True

    def release(self) -> None:
        if not self._claimed:
            return
        try:
            self._proxy.call_sync("Release", None, Gio.DBusCallFlags.NONE, -1, None)
        finally:
            self._claimed = False

    def __enter__(self) -> "FprintdClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.release()

    # -- prints ---------------------------------------------------------

    def list_enrolled(self, username: str) -> list[str]:
        result = self._proxy.call_sync(
            "ListEnrolledFingers",
            GLib.Variant("(s)", (username,)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )
        return list(result.unpack()[0])

    def delete_finger(self, finger: str) -> None:
        self._proxy.call_sync(
            "DeleteEnrolledFinger",
            GLib.Variant("(s)", (finger,)),
            Gio.DBusCallFlags.NONE,
            -1,
            None,
        )

    # -- enrol / verify -------------------------------------------------

    def _run_until_done(
        self, signal: str, start: str, stop: str, finger: str, on_status: StatusCallback
    ) -> None:
        loop = GLib.MainLoop()

        def handler(_proxy, _sender, signal_name, params):
            if signal_name != signal:
                return
            result, done = params.unpack()
            on_status(result, done)
            if done:
                loop.quit()

        handler_id = self._proxy.connect("g-signal", handler)
        try:
            self._proxy.call_sync(
                start, GLib.Variant("(s)", (finger,)), Gio.DBusCallFlags.NONE, -1, None
            )
            loop.run()
        finally:
            self._proxy.disconnect(handler_id)
            try:
                self._proxy.call_sync(stop, None, Gio.DBusCallFlags.NONE, -1, None)
            except GLib.Error:
                pass

    def enroll_start(self, finger: str, on_status: StatusCallback) -> None:
        self._run_until_done("EnrollStatus", "EnrollStart", "EnrollStop", finger, on_status)

    def enroll_stop(self) -> None:
        pass  # handled by _run_until_done

    def verify_start(self, finger: str, on_status: StatusCallback) -> None:
        self._run_until_done("VerifyStatus", "VerifyStart", "VerifyStop", finger, on_status)

    def verify_stop(self) -> None:
        pass  # handled by _run_until_done


def default_device() -> FprintdClient:
    """The first reader fprintd knows about."""
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    manager = Gio.DBusProxy.new_sync(
        bus, Gio.DBusProxyFlags.NONE, None, BUS_NAME, MANAGER_PATH, MANAGER_IFACE, None
    )
    result = manager.call_sync("GetDevices", None, Gio.DBusCallFlags.NONE, -1, None)
    paths = list(result.unpack()[0])
    if not paths:
        raise NoDeviceError("fprintd reports no fingerprint reader")
    return FprintdClient(paths[0])
