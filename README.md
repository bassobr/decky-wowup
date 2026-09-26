# WoW Addons (Decky plugin)

Update World of Warcraft addons from **Game Mode** on SteamOS handhelds (Steam Deck, ROG Xbox Ally X, …),
without switching to Desktop Mode.

The plugin does not talk to any addon site itself. It drives
[WowUp-CF](https://github.com/WowUp/WowUp.CF) – the CurseForge build of WowUp – **headlessly**:
`gamescope --backend headless -- WowUp-CF.AppImage --hidden --quit` updates your addons in a few seconds
with no window. The Quick Access menu has "Update all" for every WoW version; everything else is in the
plugin's full-screen view (Quick Access menu → Open WoW Addons).

> Unofficial. Not affiliated with WowUp, CurseForge/Overwolf or Blizzard Entertainment.

## Features

- **Update all** from the Quick Access menu; in the full-screen view per WoW version, per addon, or
  check only.
- **Installed**: every addon with version, source and compatibility; **remove** addons (optionally with
  required dependencies nothing else needs, like WowUp) and folders WowUp does not manage.
- **Get addons**: search WoWInterface and WowUp Hub, sorted by best match, popularity, downloads,
  favorites, last update or name; install from CurseForge by project ID, or open WowUp-CF's own window
  for CurseForge search (a CurseForge search needs an API key the plugin does not have). Everything is
  installed by WowUp-CF, so it keeps updating those addons.
- **All WoW versions, wherever they live**: Steam/Proton prefixes (incl. NonSteamLaunchers), Bottles, Lutris,
  Heroic, plain Wine, CrossOver, your own search folders, SD cards/USB drives, or a folder you pick. Found via
  Battle.net's `product.db` or a WoW folder's `.build.info`, and added to WowUp in WowUp's own format.
- **Installs and updates WowUp-CF itself**: downloads the AppImage from GitHub, checks it against the
  release's `latest-linux.yml` (SHA-512) and the GitHub asset digest (SHA-256), and test-runs a new
  version on a copy of your profile before switching. An existing AppImage is adopted after the same check.
- **Snapshot before every update and removal** (hardlinks, nearly free); the "Undo" page puts them back.
- **Compatibility check**: flags addons whose TOC interface does not match the installed game
  (e.g. retail addons below 120000 do not load since Midnight).
- Your WowUp settings stay yours: flags the plugin changes for a run (auto-update, notifications) are
  restored afterwards, also after a crash.

## Requirements

- SteamOS 3.8+ (or another distribution with gamescope) and [Decky Loader](https://decky.xyz).
- WoW installed through Battle.net in any Wine prefix (Steam/Proton, Bottles, Lutris, Heroic, Wine, CrossOver),
  or a WoW folder copied from another PC.
- WowUp-CF: the plugin can install it, or picks up an existing `WowUp-CF-<version>.AppImage` in
  `~`, `~/Applications` or `~/Downloads`. Set up your addons in WowUp once (the headless run updates
  the addons WowUp knows; it does not scan for new folders).

## Install

With Decky Loader installed, open Konsole in Desktop Mode:

```bash
curl -sL https://github.com/bassobr/decky-wowup/raw/main/install.sh -o /tmp/wow-addons-install.sh && sudo bash /tmp/wow-addons-install.sh
```

Then open the Quick Access menu → Decky → WoW Addons. Updates are offered in the plugin;
`install.sh` can be re-run at any time.

## Development

```bash
pnpm install && pnpm build          # frontend
python3 -m pytest tests -q          # backend (Python 3.9+)
scripts/dev-deploy.sh deck@<ip>     # copy to the handheld and restart Decky
```

Diagnostics on the device:

```bash
cd "$HOME/homebrew/plugins/WoW Addons/py_modules" && python3 -m wowaddons.cli diagnostics
```

Releases: tag `vX.Y.Z` matching `package.json`. GitHub Actions builds, tests, packages
`wow-addons-X.Y.Z.zip`, signs `SHA256SUMS` with the `MINISIGN_SEED` secret and publishes the release.

The design notes (German) are in [docs/konzept.md](docs/konzept.md).

## License

MIT
