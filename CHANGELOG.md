# Changelog

## 0.1.0 – unreleased

First version.

- Headless WowUp-CF runs from Game Mode (`gamescope --backend headless`): update all, check only,
  update a single addon; flags and notification setting restored after each run (journal).
- Detects every WoW version in Battle.net Proton prefixes (`product.db`, `.build.info`) and lets
  WowUp import the missing ones.
- Installs, adopts and updates the WowUp-CF AppImage with checksum verification and a canary run.
- Hardlink snapshots before each update with "Undo last update".
- TOC compatibility check against the installed game version.
- Signed releases, `install.sh`, in-app plugin updates via Decky Loader.
