import json
import os

from helpers import write

from wowaddons import catalog, paths, util

FILELIST = [
    {"UID": "11190", "UIName": "Bartender4", "UIAuthorName": "Nevcairiel", "UIVersion": "4.17.9.1", "UIDate": 1786522127000,
     "UIDownloadTotal": "1445629", "UIDownloadMonthly": "900", "UIDir": ["Bartender4"],
     "UICompatibility": [{"version": "12.0.7", "name": "Revelations"}, {"version": "1.15.7", "name": "Classic"}],
     "UIFileInfoURL": "https://www.wowinterface.com/downloads/info11190", "UIIMG_Thumbs": ["https://x/t.jpg"]},
    {"UID": "21492", "UIName": "Bartender4 Arched", "UIAuthorName": "nullberri", "UIDownloadTotal": "5579",
     "UIDownloadMonthly": "3", "UIDir": ["Bartender4Arched"], "UICompatibility": None},
    {"UID": "23056", "UIName": "Details! Damage Meter", "UIAuthorName": "Tercioo", "UIDownloadTotal": "515655",
     "UIDownloadMonthly": "50", "UIDir": ["Details", "Details_DataStorage"],
     "UICompatibility": [{"version": "8.3.0", "name": "Visions of N'Zoth"}]},
    {"UID": "3826", "UIName": "CTMod", "UIAuthorName": "DahkCeles", "UIDownloadTotal": "598577", "UIDownloadMonthly": "22",
     "UIDir": ["CT_Core"], "UICompatibility": [{"version": "1.15.2", "name": "Classic"}]},
]

HUB = {"addons": [{"id": 2797846, "repository_name": "MyBags", "owner_name": "MyGamesDev", "total_download_count": 42,
                   "repository": "https://github.com/x/MyBags",
                   "description": "<h1>MyBags</h1><p>Bags &amp; more &#8211; <b>fast</b></p>",
                   "releases": [{"tag_name": "3.37", "game_versions": [{"game_type": "retail"}, {"game_type": "mists"}]}]}]}


def _catalog(sandbox):
    write(os.path.join(paths.RUNTIME_DIR, "catalog", "wowi-filelist.json"), json.dumps(FILELIST))
    catalog._wowi_cache.update(mtime=0.0, entries=[])


def test_html_to_text_and_norm():
    assert catalog.html_to_text(HUB["addons"][0]["description"]) == "MyBags Bags & more – fast"
    assert catalog.html_to_text("<script>alert(1)</script>x") == "alert(1) x"
    assert catalog.norm("Details! Damage-Meter") == "details damage meter"


def test_search_ranks_exact_and_compatible_first(sandbox):
    _catalog(sandbox)
    names = [r["name"] for r in catalog.search_wowi("bartender", "mainline")]
    assert names == ["Bartender4", "Bartender4 Arched"]
    hit = catalog.search_wowi("details", "mainline")[0]
    assert hit["externalId"] == "23056" and hit["gameTypes"] == []  # 8.3.0: retail before Midnight, does not load
    assert catalog.loadable_game_types(["12.0.7", "8.3.0", "5.5.3", "1.15.7"]) == ["mainline", "mists", "vanilla"]
    assert "_norm" not in hit
    assert catalog.search_wowi("ct_core", "vanilla")[0]["name"] == "CTMod"  # folder name match
    assert catalog.search_wowi("", "mainline") == []


def test_popular_filters_by_game_type(sandbox):
    _catalog(sandbox)
    assert [r["name"] for r in catalog.popular_wowi("mainline")] == ["Bartender4"]
    assert [r["name"] for r in catalog.popular_wowi("vanilla")] == ["Bartender4", "CTMod"]


def test_hub_entries(monkeypatch):
    calls = []

    def fake_json(url, timeout=20, github=True):
        calls.append(url)
        return HUB

    monkeypatch.setattr(util, "curl_json", fake_json)
    res = catalog.search_hub("my bags", 1)
    assert calls[0].endswith("/addons/search/mists?query=my%20bags&limit=20")
    assert res[0]["provider"] == "WowUpHub" and res[0]["externalId"] == "2797846"
    assert res[0]["gameTypes"] == ["mainline", "mists"] and res[0]["summary"].startswith("MyBags Bags & more")
    catalog.featured_hub(9)
    assert "/addons/featured/burningCrusade?" in calls[1]
