"""Reports whether fingerprint login is enabled. Never changes it.

Editing PAM wrongly locks a user out of their own machine, and the correct
command differs per distribution. So this module reads, reports, and hands
the user the exact command to run themselves in a terminal, where they can
see what it does.
"""

import os
from dataclasses import dataclass

# Flatpak reserves /etc inside the sandbox and refuses to mount the host's
# copy there, so a sandboxed build sees an empty /etc and would report
# "fingerprint login off, distribution unknown" for a machine where it is on.
# The host filesystem is exposed under /run/host instead. Prefer that when it
# exists, which is exactly when we are sandboxed.
HOST_PREFIX = "/run/host"

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
    enabled: bool | None   # None means "could not be determined"
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


def _first_existing(*candidates: str) -> str:
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[-1]


def default_paths() -> tuple[str, str]:
    """Where to read PAM state, host paths first when running sandboxed."""
    pam_dir = _first_existing(f"{HOST_PREFIX}/etc/pam.d", "/etc/pam.d")
    os_release = _first_existing(
        f"{HOST_PREFIX}/os-release", f"{HOST_PREFIX}/etc/os-release", "/etc/os-release"
    )
    return pam_dir, os_release


def detect_pam_status(
    pam_dir: str | None = None, os_release: str | None = None
) -> PamStatus:
    if pam_dir is None or os_release is None:
        default_pam_dir, default_os_release = default_paths()
        pam_dir = default_pam_dir if pam_dir is None else pam_dir
        os_release = default_os_release if os_release is None else os_release

    family = detect_family(_read(os_release))

    # Flathub forbids granting a sandboxed app access to the host's /etc, so
    # in that build the PAM stack simply cannot be read. Distinguish "read it,
    # fingerprint login is off" from "could not read it at all" -- reporting a
    # confident "off" we did not verify would be exactly the kind of false
    # statement this app exists to avoid. The distribution is still detectable,
    # because /run/host/os-release needs no permission, so the right command
    # can still be offered.
    pam_file = os.path.join(pam_dir, PAM_FILES[family])
    enabled = is_enabled(_read(pam_file)) if os.path.exists(pam_file) else None

    enable_command, disable_command = COMMANDS[family]

    if enabled is None and enable_command:
        explanation = (
            "This app cannot read your login configuration from inside its "
            "sandbox, so it cannot tell whether fingerprint login is currently "
            "on. Run the command in a terminal to turn it on, or the matching "
            "--disable to turn it off."
        )
    elif enable_command:
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
