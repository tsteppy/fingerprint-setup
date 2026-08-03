from pathlib import Path

from fingerprint_setup import pam_status
from fingerprint_setup.pam_status import detect_family, detect_pam_status, is_enabled

DEBIAN_ENABLED = """\
auth	[success=2 default=ignore]	pam_fprintd.so max-tries=1 timeout=10
auth	[success=1 default=ignore]	pam_unix.so nullok try_first_pass
auth	requisite			pam_deny.so
"""

DEBIAN_DISABLED = """\
auth	[success=1 default=ignore]	pam_unix.so nullok
auth	requisite			pam_deny.so
"""

COMMENTED_OUT = """\
# auth	[success=2 default=ignore]	pam_fprintd.so
auth	[success=1 default=ignore]	pam_unix.so nullok
"""


def test_detects_enabled():
    assert is_enabled(DEBIAN_ENABLED) is True


def test_detects_disabled():
    assert is_enabled(DEBIAN_DISABLED) is False


def test_commented_lines_do_not_count_as_enabled():
    assert is_enabled(COMMENTED_OUT) is False


def test_family_from_os_release():
    assert detect_family('ID=ubuntu\nID_LIKE=debian\n') == "debian"
    assert detect_family('ID=linuxmint\nID_LIKE=ubuntu debian\n') == "debian"
    assert detect_family('ID=fedora\n') == "fedora"
    assert detect_family('ID=arch\n') == "arch"
    assert detect_family('ID=plan9\n') == "unknown"


def test_status_reads_the_real_file_layout(tmp_path: Path):
    pam_dir = tmp_path / "pam.d"
    pam_dir.mkdir()
    (pam_dir / "common-auth").write_text(DEBIAN_ENABLED)
    os_release = tmp_path / "os-release"
    os_release.write_text("ID=linuxmint\nID_LIKE=ubuntu debian\n")

    status = detect_pam_status(str(pam_dir), str(os_release))

    assert status.enabled is True
    assert status.family == "debian"
    assert "pam-auth-update" in status.enable_command


def test_missing_files_do_not_raise(tmp_path: Path):
    status = detect_pam_status(str(tmp_path / "nope"), str(tmp_path / "nope"))
    # Unreadable is "unknown", never "off" -- claiming fingerprint login is
    # disabled when we simply could not look would be a false statement about
    # the user's own security configuration.
    assert status.enabled is None
    assert status.family == "unknown"


def test_unknown_family_explains_rather_than_guessing(tmp_path: Path):
    pam_dir = tmp_path / "pam.d"
    pam_dir.mkdir()
    (pam_dir / "system-auth").write_text(DEBIAN_DISABLED)
    os_release = tmp_path / "os-release"
    os_release.write_text("ID=plan9\n")

    status = detect_pam_status(str(pam_dir), str(os_release))

    assert status.family == "unknown"
    assert status.enable_command == ""
    assert "distribution" in status.explanation.lower()


def test_host_paths_win_when_they_exist(tmp_path: Path, monkeypatch):
    """A sandboxed build must read the host's /etc, not the empty one inside."""
    host = tmp_path / "run" / "host"
    (host / "etc" / "pam.d").mkdir(parents=True)
    (host / "etc" / "pam.d" / "common-auth").write_text(DEBIAN_ENABLED)
    (host / "os-release").write_text("ID=linuxmint\nID_LIKE=ubuntu debian\n")

    monkeypatch.setattr("fingerprint_setup.pam_status.HOST_PREFIX", str(host))
    pam_dir, os_release = pam_status.default_paths()

    assert pam_dir == str(host / "etc" / "pam.d")
    assert os_release == str(host / "os-release")

    status = detect_pam_status(pam_dir, os_release)
    assert status.enabled is True
    assert status.family == "debian"


def test_falls_back_to_etc_when_not_sandboxed(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "fingerprint_setup.pam_status.HOST_PREFIX", str(tmp_path / "nonexistent")
    )
    pam_dir, os_release = pam_status.default_paths()
    assert pam_dir == "/etc/pam.d"
    assert os_release == "/etc/os-release"


def test_unreadable_pam_reports_unknown_not_off(tmp_path: Path):
    """A sandbox that cannot read /etc must not claim login is off."""
    os_release = tmp_path / "os-release"
    os_release.write_text("ID=linuxmint\nID_LIKE=ubuntu debian\n")

    status = detect_pam_status(str(tmp_path / "empty-pam.d"), str(os_release))

    assert status.enabled is None, "unreadable state must be None, never False"
    assert status.family == "debian", "the distribution is still detectable"
    assert "pam-auth-update" in status.enable_command
    assert "cannot read" in status.explanation.lower()
