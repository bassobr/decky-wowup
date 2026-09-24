"""Static configuration shared by backend, CLI and tests."""
from __future__ import annotations

PLUGIN_NAME = "WoW Addons"
GITHUB_REPO = "bassobr/decky-wowup"
RELEASE_ZIP_TEMPLATE = "wow-addons-{version}.zip"
USER_AGENT = "wow-addons/decky (+https://github.com/bassobr/decky-wowup)"
UPDATE_CHECK_INTERVAL_S = 6 * 3600

# WowUp-CF (CurseForge build of WowUp), used as the addon engine.
WOWUP_REPO = "WowUp/WowUp.CF"
WOWUP_CHECK_INTERVAL_S = 24 * 3600
WOWUP_CONFIG_NAME = "WowUpCf"  # Electron userData folder of the CF build
WOWUP_PROCESS_NAMES = ("wowup-cf",)
WOWUP_APPIMAGE_RE = r"^WowUp-CF-(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)\.AppImage$"
WOWUP_LINK_NAME = "WowUp-CF.AppImage"
# WowUpReleaseChannelType in WowUp: Beta = 0, Stable = 1 (stored as strings).
WOWUP_CHANNEL_PREF = "wowup_release_channel_2_6"
WOWUP_CHANNEL_BETA = "0"

# Headless runs: validated on SteamOS 3.8 (Desktop and Game Mode), typically 5-7 s.
RUN_TIMEOUT_S = 120
KILL_GRACE_S = 5
DOWNLOAD_TIMEOUT_S = 900
SNAPSHOT_KEEP = 5
DISCOVERY_CACHE_S = 60

# WowUp client types (wowup-lib types.ts): id -> (key, flavor folder, label)
CLIENT_TYPES = {
    0: ("retail", "_retail_", "Retail"),
    1: ("classic", "_classic_", "Classic"),
    2: ("retail_ptr", "_ptr_", "Retail PTR"),
    3: ("classic_ptr", "_classic_ptr_", "Classic PTR"),
    4: ("beta", "_beta_", "Beta"),
    5: ("classic_beta", "_classic_beta_", "Classic Beta"),
    6: ("classic_era", "_classic_era_", "Classic Era"),
    7: ("classic_era_ptr", "_classic_era_ptr_", "Classic Era PTR"),
    8: ("retail_xptr", "_xptr_", "Retail XPTR"),
    9: ("anniversary", "_anniversary_", "Anniversary"),
}
FOLDER_TO_CLIENT_TYPE = {folder: cid for cid, (_, folder, _) in CLIENT_TYPES.items()}
# Executable name WowUp uses per client type on Linux (warcraft-platform.linux.ts getExecutableName).
# WowUp's own product.db import matches installations by the exact location string, so entries the
# plugin writes use these names too (even where the real file differs, e.g. WowB.exe for Classic Beta).
WOWUP_EXE_BY_CLIENT_TYPE = {0: "Wow.exe", 1: "WowClassic.exe", 2: "WowT.exe", 3: "WowClassicT.exe", 4: "WowB.exe",
                            5: "WowClassicB.exe", 6: "WowClassic.exe", 7: "WowClassicT.exe", 8: "WowT.exe",
                            9: "WowClassic.exe"}

# Game types derived from the build version; folder names do not tell (_classic_era_ptr_ may run TBC).
GAME_TYPE_LABELS = {
    "mainline": "Retail",
    "vanilla": "Classic Era",
    "forever": "WoW: Forever",
    "tbc": "The Burning Crusade",
    "wrath": "Wrath of the Lich King",
    "titan": "Titan-Reforged",
    "cata": "Cataclysm",
    "mists": "Mists of Pandaria",
}
# Midnight (12.0): retail addons with a lower interface number do not load at all.
RETAIL_MIN_INTERFACE = 120000
