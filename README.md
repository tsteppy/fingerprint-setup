# Fingerprint Setup

Enrol fingerprints on Linux that actually work, and find out whether they do.

Laptop fingerprint readers image a small patch of your finger — often around
5x4mm. A press only matches if it lands on skin the enrolment covered, so
enrolling every press the same way is the usual reason fingerprint login feels
unreliable. On the reader that motivated this app, eight presses at one
position gave a 60% false-reject rate; the same eight spread across the
fingertip gave 10%.

Fingerprint Setup guides each press to a different part of your fingertip,
then runs ten verifications and tells you how well the enrolment performs
before you rely on it.

Works with any reader supported by fprintd.

## Install

Submitted to Flathub — https://github.com/flathub/flathub/pull/9613 — after
which:

    flatpak install flathub io.github.tsteppy.FingerprintSetup

Until then, build it yourself:

    git clone https://github.com/tsteppy/fingerprintsetup.git
    cd fingerprintsetup
    flatpak install flathub org.gnome.Platform//50 org.gnome.Sdk//50
    flatpak run org.flatpak.Builder --user --install --force-clean build-dir \
        io.github.tsteppy.FingerprintSetup.json
    flatpak run io.github.tsteppy.FingerprintSetup

A Flathub build cannot read your PAM configuration (Flathub does not permit
host `/etc` access), so it reports whether fingerprint login is currently on
as *unknown* and gives you the command for your distribution. Running from
source has no such restriction.

## Running from source

    python -m pytest              # the logic modules, no hardware needed
    python -m fingerprint_setup --simulate    # the whole app, no reader needed
    python -m fingerprint_setup               # against your real reader

`--simulate` runs the entire UI against an in-memory reader, so you can develop
and review every part of the app without owning a fingerprint sensor.

## What it does not do

It never changes your PAM configuration. It reports whether fingerprint login
is enabled and gives you the command for your distribution to run yourself, in
a terminal, where you can see what it does to your login stack.

The coverage map shows **instructed** coverage. fprintd never reports where a
press landed, so a filled zone means you were asked to press there and the
reader accepted it — not that the sensor confirmed which part of your finger
it saw.

## Licence

GPL-3.0-or-later.
