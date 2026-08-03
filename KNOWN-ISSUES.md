# Known issues and follow-ups

Findings raised during the build and triaged as safe to ship. Each was
reviewed and judged not to block a first release. Recorded here so they are
not silently forgotten.

## Behaviour

- **`build_sequence(3)` skips the lateral positions.** For a device reporting
  only three enrolment stages, the evenly-spaced sample yields centred,
  toward-the-knuckle and rolled-left — missing the tip and both side shifts.
  Five stages and above spread correctly. Selecting a maximally-spread subset
  would be better than a fixed stride. Rare in practice: most press devices
  report five or more.
  `src/fingerprint_setup/enrollment.py`

- **A verification that times out is scored as a genuine miss.** The client
  reports `verify-no-match` when its 120-second deadline expires, so a user who
  walks away mid-test has that press counted against their enrolment. Low
  frequency, but it means the app can record a result it did not actually
  measure. A distinct "timed out" result that the quality test discards would
  be more honest.
  `src/fingerprint_setup/fprintd_client.py`

- **No "already terminated" guard on an operation.** A timeout and a real
  terminal signal dispatched in the same main-loop iteration could both report
  a result. The 120-second window makes this practically untriggerable.
  `src/fingerprint_setup/fprintd_client.py`

## Consistency and style

- **`EnrollmentCoach.finished` is a plain attribute** while `QualityTest.finished`
  is a property. Cosmetic drift between two modules written to the same pattern.

- **Both dialogs call `Gtk.Window.close(self)` rather than `super().close()`**,
  which would skip any `Adw.Window`-level close behaviour if libadwaita ever
  adds one. Consistently wrong in both places, so at least there is no drift.

- **`Gtk.Widget.get_style_context()` is deprecated as of GTK 4.10** and is used
  by the coverage map to read theme colours. Still functional.
  `src/fingerprint_setup/fingertip_map.py`

- **The two dialogs duplicate ~20 lines of cancellation handling** verbatim
  (`_maybe_cancel`, `_on_close_request`, the `close()` override). A shared mixin
  would remove the duplication; the duplication currently agrees exactly, which
  was judged preferable to a premature abstraction.

## Packaging

- **Flatpak reserves `/etc`.** A sandboxed build cannot be given
  `--filesystem=/etc/...`; flatpak refuses the mount and the app sees an empty
  `/etc`. The host filesystem appears under `/run/host` instead, which is why
  `pam_status.default_paths()` prefers it and the manifest grants
  `--filesystem=host-etc:ro`. Anything else added later that reads host config
  must do the same.

- **`appstreamcli validate` reports unreachable URLs** because the homepage and
  bugtracker links point at a repository that has not been pushed yet. Resolves
  on publication. Passes with `--no-net` today apart from a pedantic
  `developer-info-missing` hint.

- **No console-script entry point.** Running from a checkout requires
  `python -m fingerprint_setup`; the Flatpak launcher hardcodes `/app/lib`.
  Documented in the README.

## Testing

- **`fprintd_client.py` has no automated tests.** It is the only module that
  touches D-Bus, and mocking Gio would test the mock rather than the code, so it
  is verified by running against real hardware instead. The claim/release
  invariant it implements *is* covered, via the dialogs, in
  `tests/test_dialogs.py`.
