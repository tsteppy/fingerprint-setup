from pathlib import Path

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
    assert status.enabled is False
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
