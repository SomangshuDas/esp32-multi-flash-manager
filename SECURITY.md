# Security Policy

## Scope

This policy covers the ESP32 Multi Flash Manager application itself (the
code in `app/`, `packaging/`, and this repository's build/release
tooling). It does **not** cover:

- The `esptool`, `espsecure`, or `espefuse` tools this app wraps as
  subprocesses — those are maintained by Espressif in the
  [`espressif/esptool`](https://github.com/espressif/esptool) repository.
  Please report vulnerabilities in those tools there.
- Vulnerabilities in ESP32/ESP8266 chip silicon, ROM bootloaders, or
  Espressif's eFuse/Secure Boot/Flash Encryption implementations
  themselves — report those directly to Espressif.
- PySide6/Qt itself, or any other third-party dependency listed in
  `requirements.txt` — report those to the respective upstream project.

## Supported Versions

As a single-maintainer open-source project, only the **latest tagged
release** receives security fixes. There is currently no long-term
support branch for older versions; please upgrade to the latest release
before reporting an issue in case it has already been fixed.

## Reporting a Vulnerability

If you believe you've found a security vulnerability in this
application — for example, something that could let flash-encryption or
secure-boot key material leak, corrupt a device's eFuses unexpectedly, or
execute arbitrary code via a crafted project (`.emfm`) file — please
**do not open a public GitHub issue**. Instead:

1. Use GitHub's private
   [**Report a vulnerability**](https://github.com/SomangshuDas/esp32-multi-flash-manager/security/advisories/new)
   feature on this repository, if enabled, **or**
2. Reach out directly through the contact information on the maintainer's
   profile at [github.com/SomangshuDas](https://github.com/SomangshuDas).

Please include:

- A description of the issue and its potential impact.
- Steps to reproduce, including OS, Python version, and `esptool` version
  (`pip show esptool`).
- Any relevant logs — **but first strip out real device MAC addresses,
  eFuse dumps, flash-encryption keys, or secure-boot signing keys** from
  anything you attach. See "Handling sensitive data" below.

You should expect an initial response within a reasonable timeframe;
since this is a single-maintainer project, please be patient, and feel
free to follow up if you haven't heard back.

## Handling Sensitive Data

A few reminders specific to this project's domain, for anyone reporting
an issue or reviewing code:

- **Never commit or attach real flash-encryption keys, secure-boot
  signing keys, or eFuse key-block dumps** to an issue, pull request, or
  log file — these are exactly the artifacts this application is
  designed to protect, and a leaked key can permanently compromise a
  physical device's security.
- The app's own confirmation dialogs for eFuse burning and encrypted
  writes exist specifically because these operations are irreversible on
  real hardware. If you find a way to bypass those confirmations (e.g. a
  code path that burns an eFuse or writes an encrypted image without the
  user explicitly acknowledging it), that is a security bug — please
  report it privately per the process above rather than filing a public
  issue.
- Read-only inspection features (Chip Info, Read Flash, eFuse Summary,
  Security Info) never write to a device, but their **output** can
  contain sensitive data (MAC addresses, key-block contents if
  read-protection was never enabled). Treat saved read-back files the
  same way you'd treat any other secret material.

## Disclosure

Once a reported vulnerability is confirmed and a fix is released, details
will be published in that release's notes, with credit to the reporter
unless they request otherwise.
