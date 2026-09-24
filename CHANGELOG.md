# Changelog

## 0.1.0 – 2026-09-24

First version.

- Headless WowUp-CF runs from Game Mode (`gamescope --backend headless`): update all, check only,
  update a single addon; flags and notification setting restored after each run (journal).
- Detects every WoW version in Battle.net Proton prefixes (`product.db`, `.build.info`) and lets
  WowUp import the missing ones.
- Installs, adopts and updates the WowUp-CF AppImage with checksum verification and a canary run.
- Hardlink snapshots before each update with "Undo last update".
- TOC compatibility check against the installed game version.
- Signed releases, `install.sh`, in-app plugin updates via Decky Loader.
- Full-screen "Get addons" page: search WoWInterface and WowUp Hub (popular/featured without a query),
  install from CurseForge by project ID, open WowUp-CF's own window for CurseForge search; installs run
  through WowUp-CF, required CurseForge dependencies are added automatically.
- Progress bar no longer pushed to the right (raw ProgressBar instead of ProgressBarWithInfo).
- WoW versions from every route: Steam/Proton (incl. NonSteamLaunchers), Bottles, Lutris, Heroic, Wine,
  CrossOver, search folders, SD cards/USB drives and folders picked by hand; added to WowUp directly in
  WowUp's own format (no duplicates with WowUp's own import). New full-screen page "WoW versions".
