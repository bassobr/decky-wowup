# Changelog

## Unreleased

- Central full-screen view (Quick Access menu → Open WoW Addons) with the pages Installed, Get addons,
  WoW versions, Undo, WowUp-CF and Notes. The Quick Access menu keeps "Update all" (now for every WoW
  version at once) and the plugin update.
- Remove addons: deletes their folders and WowUp records like WowUp does, optionally together with
  required dependencies no other addon needs; folders another addon uses stay. Folders WowUp does not
  manage can be removed too. A snapshot is taken first; "Undo" puts removed addons back.
- Get addons: sort by best match, popular, most downloads, most favorites (WoWInterface), recently updated
  or name; results show favorites and the last update.
- WowUp's own `wowup_data_addon` folder is no longer listed as "not managed".

## 0.1.1 – 2026-09-26

- WowUp installations whose folder is gone or holds only `Interface/AddOns` (e.g. a deleted Proton prefix)
  are marked and never updated: WowUp would otherwise recreate the folder and install addons there.
- "Move to the installed game": points such an installation at the detected WoW folder, keeps its addon
  list, copies the addon folders and replaces an empty entry for the same folder. CLI: `relocate`.
- Leftover AddOns folders are no longer detected as WoW versions.

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
