"""Reports whether fingerprint login is enabled. Never changes it.

Editing PAM wrongly locks a user out of their own machine, and the correct
command differs per distribution. So this module reads, reports, and hands
the user the exact command to run themselves in a terminal, where they can
see what it does.
"""

import os
from dataclasses import dataclass

# Files that carry the primary auth stack, by distribution family.
PAM_FILES = {
    "debian": "common-auth",
    "fedora": "system-auth",
    "arch": "system-auth",
    "unknown": "system-auth",
}

COMMANDS = {
    "debian": (
        "sudo pam-auth-update --enable fprintd",
        "sudo pam-auth-update --disable fprintd",
    ),
    "fedora": (
        "sudo authselect enable-feature with-fingerprint",
        "sudo authselect disable-feature with-fingerprint",
    ),
    "arch": ("", ""),
    "unknown": ("", ""),
}


@dataclass(frozen=True)
class PamStatus:
    enabled: bool
    family: str
    enable_command: str
    disable_command: str
    explanation: str


def detect_family(os_release_text: str) -> str:
    fields: dict[str, str] = {}
    for line in os_release_text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip().strip('"')

    ids = [fields.get("ID", "")] + fields.get("ID_LIKE", "").split()
    for name in ids:
        if name in ("debian", "ubuntu", "linuxmint"):
            return "debian"
        if name in ("fedora", "rhel", "centos"):
            return "fedora"
        if name in ("arch", "archlinux", "manjaro"):
            return "arch"
    return "unknown"


def is_enabled(pam_text: str) -> bool:
    for line in pam_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "pam_fprintd.so" in stripped:
            return True
    return False


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def detect_pam_status(
    pam_dir: str = "/etc/pam.d", os_release: str = "/etc/os-release"
) -> PamStatus:
    family = detect_family(_read(os_release))
    pam_text = _read(os.path.join(pam_dir, PAM_FILES[family]))
    enabled = is_enabled(pam_text)
    enable_command, disable_command = COMMANDS[family]

    if enable_command:
        explanation = (
            "Fingerprint login is configured through PAM. This app does not "
            "change PAM — run the command in a terminal so you can see what it "
            "does to your login configuration."
        )
    else:
        explanation = (
            "This app could not determine how your distribution manages PAM, "
            "so it will not guess. See your distribution's documentation for "
            "enabling pam_fprintd."
        )

    return PamStatus(
        enabled=enabled,
        family=family,
        enable_command=enable_command,
        disable_command=disable_command,
        explanation=explanation,
    )
