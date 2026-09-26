"""Command line for diagnostics over SSH (system Python), sharing settings with the plugin.

  cd "$HOME/homebrew/plugins/WoW Addons/py_modules" && python3 -m wowaddons.cli status
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

from . import settings, snapshots, wow, wowup_app, wowup_runner
from .service import Service
from .wowup_store import WowUpStore


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def _progress(msg: str, pct: Optional[float] = None) -> None:
    print(f"… {msg}" + (f" ({pct:.0f}%)" if pct is not None else ""), file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="wowaddons")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="plugin state as JSON")
    sub.add_parser("discover", help="WoW flavors found in Proton prefixes")
    sub.add_parser("diagnostics", help="human-readable summary")
    r = sub.add_parser("run", help="headless WowUp-CF run")
    r.add_argument("--mode", choices=wowup_runner.MODES, default="check")
    r.add_argument("--installation")
    r.add_argument("--key", action="append", help="addon key for --mode selected (repeatable)")
    r.add_argument("--config-home", help="sandbox XDG_CONFIG_HOME instead of the real WowUp profile")
    w = sub.add_parser("wowup", help="WowUp-CF AppImage")
    w.add_argument("action", choices=["info", "candidates", "check", "install", "update", "adopt"])
    w.add_argument("path", nargs="?")
    f = sub.add_parser("search", help="search WoWInterface and WowUp Hub (empty query: popular)")
    f.add_argument("query", nargs="?", default="")
    f.add_argument("--installation", help="WowUp installation id (default: first)")
    m = sub.add_parser("relocate", help="point a WowUp installation at another WoW folder (keeps its addons)")
    m.add_argument("installation")
    m.add_argument("flavor_dir")
    s = sub.add_parser("snapshots", help="AddOns snapshots")
    s.add_argument("action", choices=["list", "restore"])
    s.add_argument("id", nargs="?")
    a = ap.parse_args(argv)

    st = settings.load()
    svc = Service(st, lambda: settings.save(st))
    if a.cmd == "status":
        _print(svc.state(refresh=True))
    elif a.cmd == "discover":
        _print(wow.discover())
    elif a.cmd == "diagnostics":
        print(svc.diagnostics())
    elif a.cmd == "run":
        if a.config_home:
            store = WowUpStore(os.path.join(a.config_home, "WowUpCf"))
            _print(wowup_runner.run(store, svc.appimage() or "", a.mode, a.key, a.installation,
                                    config_home=a.config_home, on_progress=_progress))
        else:
            _print(svc.run_update(a.mode, a.installation, a.key, _progress))
    elif a.cmd == "wowup":
        if a.action == "info":
            _print(svc.wowup_info())
        elif a.action == "candidates":
            _print(wowup_app.find_candidates())
        elif a.action == "check":
            _print(svc.check_wowup_update(force=True))
        elif a.action == "install":
            _print(svc.install_wowup(_progress))
        elif a.action == "update":
            _print(svc.apply_wowup_update(_progress))
        elif a.action == "adopt":
            if not a.path:
                ap.error("wowup adopt needs a path")
            _print(svc.adopt(a.path))
    elif a.cmd == "search":
        inst_id = a.installation or next((i["id"] for i in svc.installations()), None)
        if not inst_id:
            ap.error("WowUp-CF has no installation")
        res = svc.search_addons(inst_id, a.query)
        for group in ("wowinterface", "hub"):
            for r in res[group][:15]:
                flag = "installed" if r["installed"] else ("compatible" if r["compatible"] else ("?" if r["compatible"] is None else "not listed"))
                print(f"{group:12} {r['provider']}:{r['externalId']:<10} {r['name'][:40]:<40} {r['downloads']:>9}  {flag}")
        for e in res["errors"]:
            print("error:", e)
    elif a.cmd == "relocate":
        _print(svc.relocate_installation(a.installation, a.flavor_dir, _progress))
    elif a.cmd == "snapshots":
        if a.action == "list":
            _print(snapshots.list_snapshots())
        else:
            if not a.id:
                ap.error("snapshots restore needs an id")
            _print(svc.restore_snapshot(a.id))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
