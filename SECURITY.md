# Security Policy

WoW Addons runs **without root** inside Decky Loader (`"flags": []`). It writes only below the user's
home directory:

- `~/homebrew/{settings,data,logs}/WoW Addons` – settings, snapshots of AddOns folders, run logs;
- `~/.config/WowUpCf/{addons,preferences}.json` – only while WowUp-CF is closed, only the fields a run
  needs (`autoUpdateEnabled`, `enable_system_notifications`, `blizzard_agent_path`,
  `wow_installations`), restored after each run via a journal;
- the `Interface/AddOns` folders of your WoW installations – only through WowUp-CF or a snapshot restore;
- `~/Applications/WowUp-CF/` – the WowUp-CF AppImage the plugin installs or updates.

It starts WowUp-CF in a private headless gamescope and never modifies the SteamOS root filesystem.
It never reads WowUp's `sensitive.json`.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:

https://github.com/bassobr/decky-wowup/security/advisories/new

Do not open public issues for security problems. This is a solo-maintained project; reports are
handled on a best-effort basis.

## Supported versions

Only the latest release receives fixes. The in-app updater moves installations forward; older
versions can be reinstalled with `install.sh`.

## Release integrity

- Releases are built by GitHub Actions from a tag and ship `SHA256SUMS` plus a minisign-compatible
  signature `SHA256SUMS.minisig`.
- The updater verifies the signature against the public key pinned in the plugin (`minisign.pub`)
  before trusting any checksum, then hands the zip URL and its SHA-256 to Decky Loader, which downloads
  the zip and rejects it on a checksum mismatch. Unsigned releases are refused.
- Manual check: `minisign -Vm SHA256SUMS -p minisign.pub`.
- Limits: the signing seed lives in a GitHub Actions secret, so a full account takeover could still
  produce valid signatures. minisign has no revocation; a compromised key requires an out-of-band key
  rotation and a reinstall.

## Downloaded third-party content

WowUp-CF AppImages are downloaded from the `WowUp/WowUp.CF` GitHub releases over HTTPS and must match
both the SHA-512 in the release's `latest-linux.yml` and the SHA-256 digest GitHub reports for the asset.
WowUp does not sign its releases, so trust is anchored in that GitHub repository. A new version is
test-run against a copy of the WowUp profile before it replaces the one in use.
