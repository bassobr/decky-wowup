"""Builders for synthetic Steam/Proton/WoW trees, product.db, shortcuts.vdf and a fake WowUp-CF."""
import json
import os
import stat
import struct
import textwrap

BNET_APPID = 3781448467
RETAIL_ID = "e52f7e70-0598-4895-8172-8cd9a24ef20f"


# ---------------------------------------------------------------- protobuf (product.db)
def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _field(fn: int, wt: int, payload) -> bytes:
    key = _varint((fn << 3) | wt)
    if wt == 0:
        return key + _varint(payload)
    return key + _varint(len(payload)) + payload


def _s(fn, text):
    return _field(fn, 2, text.encode())


def product(uid, code, path, sub, version, family="wow"):
    settings = _s(1, path) + _s(13, sub)
    base = _field(1, 0, 1) + _field(2, 0, 1) + _field(3, 0, 1) + _s(7, version)
    state = _field(1, 2, base)
    return _field(1, 2, _s(1, uid) + _s(2, code) + _field(3, 2, settings) + _field(4, 2, state) + _s(6, family))


def product_db(products) -> bytes:
    agent = _field(1, 2, _s(1, "agent") + _s(2, "agent") + _field(3, 2, _s(1, "C:/ProgramData/Battle.net/Agent")))
    return agent + b"".join(products)


# ---------------------------------------------------------------- binary VDF (shortcuts.vdf)
def _vdf(obj) -> bytes:
    out = b""
    for k, v in obj.items():
        key = k.encode() + b"\x00"
        if isinstance(v, dict):
            out += b"\x00" + key + _vdf(v) + b"\x08"
        elif isinstance(v, int):
            out += b"\x02" + key + struct.pack("<i", v)
        else:
            out += b"\x01" + key + str(v).encode() + b"\x00"
    return out


def shortcuts_vdf(entries) -> bytes:
    return b"\x00shortcuts\x00" + _vdf({str(i): e for i, e in enumerate(entries)}) + b"\x08\x08"


def signed32(n: int) -> int:
    return n - (1 << 32) if n >= (1 << 31) else n


# ---------------------------------------------------------------- trees
def write(path, data, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)
    if mode is not None:
        os.chmod(path, mode)
    return path


def make_steam(home, flavors=(("wow", "_retail_", "12.1.0.69933", "eu", "Wow.exe"),), appid=BNET_APPID):
    steam = os.path.join(home, ".local", "share", "Steam")
    write(os.path.join(steam, "steamapps", "libraryfolders.vdf"),
          '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t}\n}\n' % steam)
    pfx = os.path.join(steam, "steamapps", "compatdata", str(appid), "pfx")
    exe = os.path.join(pfx, "drive_c", "Program Files (x86)", "Battle.net", "Battle.net.exe")
    write(os.path.join(steam, "userdata", "1234", "config", "shortcuts.vdf"),
          shortcuts_vdf([{"appid": signed32(appid), "AppName": "Battle.net", "Exe": f'"{exe}"',
                          "StartDir": f'"{os.path.dirname(exe)}"', "LaunchOptions": ""}]))
    os.makedirs(os.path.join(pfx, "dosdevices"), exist_ok=True)
    os.symlink("../drive_c", os.path.join(pfx, "dosdevices", "c:"))
    root = os.path.join(pfx, "drive_c", "Program Files (x86)", "World of Warcraft")
    rows = ["Branch!STRING:0|Active!DEC:1|Build Key!HEX:16|Version!STRING:0|Product!STRING:0"]
    prods = []
    for code, sub, version, region, exe_name in flavors:
        rows.append(f"{region}|1|abc|{version}|{code}")
        flavor = os.path.join(root, sub)
        write(os.path.join(flavor, exe_name), b"")
        write(os.path.join(flavor, ".flavor.info"), f"Product Flavor!STRING:0\n{code}\n")
        os.makedirs(os.path.join(flavor, "Interface", "AddOns"), exist_ok=True)
        prods.append(product(code, code, "C:/Program Files (x86)/World of Warcraft", sub, version))
    write(os.path.join(root, ".build.info"), "\n".join(rows) + "\n")
    write(os.path.join(pfx, "drive_c", "ProgramData", "Battle.net", "Agent", "product.db"), product_db(prods))
    return {"steam": steam, "pfx": pfx, "root": root}


def make_addon(addons_dir, name, interface="120100", version="1.0", extra_tocs=None, body="print('hi')\n"):
    folder = os.path.join(addons_dir, name)
    write(os.path.join(folder, f"{name}.toc"), f"## Interface: {interface}\n## Title: |cff00ff00{name}|r\n"
                                                f"## Version: {version}\n## X-Curse-Project-ID: 42\n{name}.lua\n")
    for suffix, iface in (extra_tocs or {}).items():
        write(os.path.join(folder, f"{name}_{suffix}.toc"), f"## Interface: {iface}\n## Title: {name}\n{name}.lua\n")
    write(os.path.join(folder, f"{name}.lua"), body)
    return folder


def record(rid, name, installation_id=RETAIL_ID, external_id="100", installed="1", latest="1",
           version="1.0", latest_version="1.0", auto=True, folders=None, provider="Curse"):
    return {"id": rid, "name": name, "providerName": provider, "externalId": external_id,
            "installationId": installation_id, "installedExternalReleaseId": installed,
            "externalLatestReleaseId": latest, "installedVersion": version, "latestVersion": latest_version,
            "autoUpdateEnabled": auto, "isIgnored": False, "channelType": 0,
            "installedFolderList": folders or [name], "installedFolders": ",".join(folders or [name])}


def write_wowup(config_dir, prefs, addons, mode=0o666):
    os.makedirs(os.path.join(config_dir, "logs"), exist_ok=True)
    write(os.path.join(config_dir, "preferences.json"), json.dumps(prefs, indent="\t"), mode)
    write(os.path.join(config_dir, "addons.json"), json.dumps(addons, indent="\t"), mode)


# ---------------------------------------------------------------- fake WowUp-CF
FAKE_WOWUP = textwrap.dedent('''\
    #!/usr/bin/env python3
    """Fake WowUp-CF: updates addons with autoUpdateEnabled whose latest release differs, then quits."""
    import json, os, sys, time
    cfg = os.path.join(os.environ["XDG_CONFIG_HOME"], "WowUpCf")
    behavior = open(os.path.join(cfg, "fake-behavior")).read().strip() if os.path.exists(os.path.join(cfg, "fake-behavior")) else "normal"
    def log(level, msg):
        with open(os.path.join(cfg, "logs", "main.log"), "a") as f:
            f.write("[2026-09-24 10:42:26.169] [%s]  %s\\n" % (level, msg))
    assert sys.argv[1:] == ["--hidden", "--quit"], sys.argv
    log("info", "ARGV { _: [], serve: false, hidden: true, quit: true }")
    if behavior == "hang":
        time.sleep(60)
    prefs = json.load(open(os.path.join(cfg, "preferences.json")))
    addons = json.load(open(os.path.join(cfg, "addons.json")))
    updated = 0
    catalog_path = os.path.join(cfg, "fake-catalog.json")
    catalog = json.load(open(catalog_path)) if os.path.exists(catalog_path) else {}
    locations = {w["id"]: w["location"] for w in prefs.get("wow_installations", [])}
    for a in addons.values():
        entry = catalog.get("%s|%s" % (a.get("providerName"), a.get("externalId")))
        if a.get("autoUpdateEnabled") and a.get("installedVersion") == "0" and entry:
            log("info", "[AddonUpdate] %s %s %s '0' -> '%s'" % (a["providerName"], a["externalId"], entry["name"], entry["version"]))
            a.update(name=entry["name"], installedVersion=entry["version"], latestVersion=entry["version"],
                     installedExternalReleaseId=entry.get("releaseId", "1"), externalLatestReleaseId=entry.get("releaseId", "1"),
                     installedFolderList=entry["folders"], installedFolders=",".join(entry["folders"]),
                     dependencies=entry.get("dependencies", []))
            addons_dir = os.path.join(os.path.dirname(locations[a["installationId"]]), "Interface", "AddOns")
            for folder in entry["folders"]:
                os.makedirs(os.path.join(addons_dir, folder), exist_ok=True)
                open(os.path.join(addons_dir, folder, folder + ".toc"), "w").write("## Interface: 120100\\n")
            updated += 1
            continue
        a["externalLatestReleaseId"] = a.get("_fakeLatestId", a.get("externalLatestReleaseId"))
        a["latestVersion"] = a.get("_fakeLatestVersion", a.get("latestVersion"))
        if a.get("autoUpdateEnabled") and str(a["externalLatestReleaseId"]) != str(a["installedExternalReleaseId"]):
            log("info", "[AddonUpdate] %s %s %s '%s' -> '%s'" % (a["providerName"], a["externalId"], a["name"], a["installedVersion"], a["latestVersion"]))
            a["installedExternalReleaseId"] = a["externalLatestReleaseId"]
            a["installedVersion"] = a["latestVersion"]
            log("info", "[AddonUpdateComplete] %s %s %s %s" % (a["providerName"], a["externalId"], a["name"], a["latestVersion"]))
            updated += 1
    json.dump(addons, open(os.path.join(cfg, "addons.json"), "w"), indent="\\t")
    if behavior == "error":
        log("error", "Failed to update addon: boom")
    if updated and prefs.get("enable_system_notifications") != "false":
        time.sleep(60)  # like WowUp: waits for the desktop notification to close
    log("info", "[QuitApp]")
''')


def make_fake_wowup(directory, name="WowUp-CF-2.23.1.AppImage"):
    return write(os.path.join(directory, name), FAKE_WOWUP, stat.S_IRWXU)
