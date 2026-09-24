# decky-wowup – Konzept & Planung

> **Stand:** 24.09.2026 · **Version 2** (Entscheidungen und Spike-Ergebnisse eingearbeitet)
> **Testgerät:** ASUS ROG Xbox Ally X, SteamOS 3.8.16 · **Zielgeräte:** alle SteamOS-Handhelds (Steam Deck, Ally X, …)
> **Ziel:** WoW-Addons komplett im Game Mode verwalten – per Controller, ohne Desktop-Modus, für alle WoW-Versionen.

---

## 0. Kurzfassung

- **Architektur: „Cockpit“ für WowUp-CF.** WowUp-CF bleibt dauerhaft die Engine.
  - Das Plugin baut **keine** eigene Addon-Engine und spricht **keine** Addon-APIs an.
  - WowUp-CF deckt bereits CurseForge, WoWInterface, Tukui und GitHub ab.
- **Auf der Ally X nachgewiesen, im Desktop-Modus und im Game Mode**, isoliert und ohne Eingriff in echte Daten:
  - **Unsichtbares Update:** `gamescope --backend headless -- WowUp-CF.AppImage --hidden --quit` aktualisiert Addons ohne Fenster und ohne Display- oder Sitzungsvariablen. Das dauert etwa 5–7 s, danach beendet sich WowUp sauber.
  - **Nur prüfen:** Über vorübergehend gesetzte Flags holt WowUp nur die neuesten Versionen und installiert nichts.
  - **Neue CurseForge-Addons per Projekt-ID:** Das Plugin legt einen Platzhalter in `addons.json` an, WowUp-CF installiert dann das Addon. Einen eigenen Key braucht es dafür nicht.
  - **Alle WoW-Versionen:** Zeigt `blizzard_agent_path` auf die `product.db` im Proton-Präfix, übernimmt WowUp alle installierten Versionen selbst.
- **Stolperfallen:**
  - Sind Benachrichtigungen an, beendet sich WowUp nach einem Update nicht.
  - Der Chromium-Headless-Modus stürzt ab.
  - Fehlt die X-Berechtigung, stürzt WowUp ab und hängt.
  - Folge: Timeouts sind Pflicht, und die Benachrichtigungen werden für jeden Lauf vorübergehend abgeschaltet.
- **Neu im Funktionsumfang: Das Plugin stellt WowUp-CF selbst bereit.**
  - Es lädt das AppImage herunter, prüft es und legt es ab.
  - Es richtet ein frisches Profil ohne Bedienung ein.
  - Es hält WowUp-CF aktuell. Das ist nötig, weil sich WowUp im Modus `--quit` nicht selbst aktualisiert und WoW: Forever WowUp 2.24 braucht.
  - Prüfverfahren und frisches Profil sind auf dem Gerät getestet (V10, V11).
- **Offen:**
  - Lauf aus dem Decky-Backend heraus (kommt mit S3)
  - Plugin-Gerüst und Deployment (S3)
  - Steam-Hooks (S4)
- **Verteilung über GitHub** (`bassobr/decky-wowup`), nach dem Muster deiner übrigen Decky-Plugins:
  - signierte Releases (minisign)
  - `install.sh` für die Erstinstallation
  - Updates im Plugin, installiert durch Decky
  - Der Decky-Store kommt nicht infrage, weil er KI-generierten Code ablehnt.

---

## 1. Entscheidungen (24.09.2026)

| Frage | Entscheidung | Folge |
|---|---|---|
| Bleibt WowUp-CF? | **Ja, dauerhaft** | Das Cockpit ist die Zielarchitektur; eine eigene Engine entfällt |
| Eigener CurseForge-API-Key? | **Nein** | Alle CurseForge-Zugriffe laufen über WowUp-CF; das Plugin ruft keine CF-API auf |
| Welche WoW-Versionen? | **Alle** | Flavor-Tabelle datengetrieben; gebunden an die Client-Typen, die WowUp unterstützt |
| Wie wird verteilt? | **über GitHub**, wie deine anderen Decky-Plugins | signierte Releases, `install.sh`, Updates im Plugin über Decky (Kap. 6.8) |

---

## 2. Ausgangslage auf dem Testgerät (Spike S2)

| Baustein | Befund |
|---|---|
| System | ROG Xbox Ally X (RC73XA), SteamOS 3.8.16; System-Python 3.13.5 mit certifi; `jq`, `rsync`, `gamescope`, `systemd-run` vorhanden |
| Decky | Loader v3.2.9 aktiv, 7 Plugins laufen (u. a. Ally DSP, LSFG-VK, SteamGridDB) → Decky funktioniert auf der Ally X; `sudo` geht ohne Passwort |
| Speicher | `/home` ext4 (1,9 TB), SD-Karte „Sandisk“ (ext4) als zweite Steam-Bibliothek |
| Battle.net | Nicht-Steam-Shortcut „Battle.net“, appid **3781448467**, Proton-GE Latest; Präfix `compatdata/3781448467/pfx` |
| Präfix | `drive_c` mit Casefold-Attribut `F` (case-insensitiv); `d:` → SD-Karte, `z:` → `/` |
| `product.db` | lässt sich lesen: `wow` → `_retail_` 12.1.0.69933 (eu); `wow_classic_beta` → `_classic_beta_` 1.60.1.69977 (us) = **Beta von WoW: Forever** |
| Programme | `_retail_/Wow.exe`, `_classic_beta_/WowB.exe` |
| WowUp-CF | `~/WowUp-CF-2.23.1.AppImage`; Daten in `~/.config/WowUpCf/` (kein `sensitive.json` vorhanden) |
| WowUp-Installationen | **nur Retail** eingetragen; die Forever-Beta fehlt |
| Addons | 1 Datensatz: ConsolePort (Curse 91376, 3.2.6, Auto-Update an) mit 9 Ordnern; alle 9 kompatibel (Interface ≥ 120100) |
| Kritische Einstellung | `enable_system_notifications = "true"` → ein unsichtbarer Lauf hängt (siehe V7) |
| Update-Kanal von WowUp | `wowup_release_channel_2_6 = "1"`; vermutlich Beta, Zuordnung ungeprüft |

---

## 3. Zielbild

**Anwendungsfälle nach Priorität**
1. **Ein Knopf:** Updates prüfen und installieren – im Game Mode, unsichtbar.
2. **Überblick** je WoW-Version: Was ist installiert, was ist veraltet oder inkompatibel?
3. **Automatik:** vor oder beim Spielstart und periodisch; Hinweis per Toast.
4. **Sicherheit:** Rollback nach einem kaputten Update, Backups von WTF/SavedVariables.
5. **Neue Addons installieren:** per CurseForge-Projekt-ID, als kuratiertes Paket oder als WowUp-Exportliste vom PC.
6. **Alle WoW-Versionen:** automatisch erkennen und in WowUp übernehmen.
7. **WowUp-CF selbst bereitstellen:** herunterladen, prüfen, einrichten und aktuell halten, damit keine Handarbeit im Desktop-Modus nötig ist.

**Nicht-Ziele:**
- eigene Addon-Engine oder eigene Provider-Clients
- eigener CurseForge-Key
- Wago (im CF-Build von WowUp deaktiviert)
- Windows oder macOS
- Veröffentlichung im Decky-Store

---

## 4. Spike-Ergebnisse (S1 Desktop-Modus, S1b Game Mode, S2 · 24.09.2026)

### Aufbau der isolierten Testumgebung

Alles lief unter `~/wowup-spike/` auf dem Gerät:
1. **Konfigurationskopie:** WowUp nutzte eine Kopie seiner Konfiguration, umgelenkt per `XDG_CONFIG_HOME`.
2. **Schein-Installation:** eine unechte WoW-Installation mit leerer `Wow.exe` und einer echten Kopie der AddOns (47 MB).
3. **Kopie angepasst:**
   - Die Installation zeigt auf die Schein-Installation.
   - Benachrichtigungen sind aus.
   - ConsolePort ist künstlich als veraltet markiert (`installedExternalReleaseId = "1"`).
4. **Nachweis:** Die Prüfsummen von `addons.json`, `preferences.json` und allen echten AddOns-Dateien waren danach identisch. Auch das echte WowUp-Log blieb unverändert.

| Lauf | Aufbau | Ergebnis | Dauer | Erkenntnis |
|---|---|---|---|---|
| V1 | Desktop-Sitzung (`DISPLAY`, `WAYLAND_DISPLAY`), **ohne** `XAUTHORITY` | ❌ Absturz („Missing X server“), danach Hänger | 310 s (Timeout) | ohne X-Berechtigung geht nichts; ein Timeout ist Pflicht |
| V2 | wie V1, **mit** `XAUTHORITY` der Sitzung | ✅ Update installiert, `[QuitApp]`, Exit-Code 0 | 7,3 s | Der Mechanismus funktioniert. |
| V3 | ohne Display, `--ozone-platform=headless` | ❌ GPU-Init-Absturz, Hänger | 130 s (Timeout) | unbrauchbar |
| V3b | wie V3, zusätzlich `--disable-gpu` | ❌ Absturz (SIGSEGV) | 65 s (Timeout) | unbrauchbar |
| **V4** | **ohne Display, `gamescope --backend headless`** | ✅ **Update installiert, Exit-Code 0** | **6,2 s** | **Zielvariante, unabhängig von jeder Sitzung** |
| V6 | wie V4, alle Auto-Updates aus | ✅ neueste Versionen geholt, nichts installiert | 5,0 s | Der Modus „Nur prüfen“ funktioniert. |
| V7 | wie V4, Benachrichtigungen **an** | ⚠ Update installiert, aber kein Beenden | 90 s (Timeout) | Benachrichtigungen je Lauf abschalten |
| V8 | wie V4, `blizzard_agent_path` = Agent-**Ordner** | ❌ `EISDIR` | 4,8 s | Der Pfad muss auf die Datei zeigen. |
| V8b | wie V4, `blizzard_agent_path` = **`product.db`** | ✅ Forever-Beta als ClassicBeta (Typ 5) übernommen | 4,7 s | WowUp findet alle Versionen selbst. |
| V9 | wie V4, Platzhalter mit Projekt-ID 257550 | ✅ **Immersion 1.4.60 installiert**, Datensatz vervollständigt | 5,2 s | Neue Addons ohne eigenen Key |
| **GM-V4** | **Game Mode**, sonst wie V4 | ✅ Update installiert, Exit-Code 0; der gamescope von Steam läuft unbeeinflusst weiter | 6,0 s | funktioniert parallel zur Steam-Sitzung |
| **GM-V6** | **Game Mode**, sonst wie V6 | ✅ nur geprüft, nichts installiert | 4,7 s | „Nur prüfen“ klappt auch im Game Mode |
| **V10** | Vorhandenes AppImage gegen die Release-Metadaten geprüft | ✅ SHA-256 = GitHub-`digest`, SHA-512 und Größe = `latest-linux.yml` | – | Das Prüfverfahren für Download und Übernahme funktioniert. |
| **V11** | Game Mode, **leeres Profil**, nur `blizzard_agent_path` und Benachrichtigungen vorbelegt | ✅ 2 Installationen importiert, Lauf erledigt, `[QuitApp]`; Log `cmpRequired true`, `telemetry_enabled` bleibt leer, keine `addons.json` | 4,5 s | Eine Neuinstallation ist ohne Bedienung einsatzbereit; die Einwilligungsdialoge blockieren nicht. |

**Weitere Befunde**
- **Maschinenlesbares Log** (`logs/main.log`):
  - `[AddonUpdate] Curse 91376 ConsolePort '3.2.5' -> '3.2.6'`
  - `[AddonUpdateComplete] Curse 91376 ConsolePort 3.2.6`
  - `[QuitApp]`
- **Dateirechte:** Neu geschriebene JSON-Dateien bekamen die Rechte 0666 (umask der SSH-Sitzung). Das Plugin muss die ursprünglichen Rechte beibehalten.
- **Import mit Macken (V8b):**
  - WowUp 2.23.1 trägt für ClassicBeta `WowClassicB.exe` ein, tatsächlich heißt die Datei `WowB.exe`. Der AddOns-Pfad stimmt trotzdem.
  - Hat eine bestehende Installation einen anderen Pfad, legt WowUp sie doppelt an.
- **Coredumps:** Die Absturz-Varianten V1, V3 und V3b haben Coredumps erzeugt, die der SteamOS-Log-Submitter verarbeitet. Solche Varianten gehören nicht ins Plugin.
- **Game-Mode-Sitzung:**
  - Der gamescope von Steam läuft mit `--xwayland-count 2 -w 1280 -h 800`.
  - Steam nutzt `DISPLAY=:0` ohne `XAUTHORITY` (`GAMESCOPE_WAYLAND_DISPLAY=gamescope-0`).
  - `/dev/dri/renderD128` ist für alle Benutzer freigegeben (`crw-rw-rw-`). Der unsichtbare gamescope sollte deshalb auch aus dem Decky-Backend heraus starten.
- **Noch offen (S1c):** der Lauf aus dem Decky-Backend heraus, also als Kindprozess des Systemdiensts `plugin_loader`. Das prüft das Test-Plugin in S3.

---

## 5. Randbedingungen (Recherche, weiterhin gültig)

### 5.1 Decky Loader (v3.2.9)

| Thema | Fakt | Konsequenz |
|---|---|---|
| Laufzeit | eingefrorenes Python 3.11.7 | Code 3.11-kompatibel halten, möglichst nur Stdlib verwenden |
| Fehlende Stdlib-Module | u. a. `xml.etree`, `html.parser`, `glob`, `configparser`, `tomllib`, `unittest` | Import-Guard-Test; `os.scandir` statt `glob` |
| Benutzer | ohne `root`-Flag läuft das Backend als `deck` | **kein** `root`-Flag |
| Aufrufe | `callable` ohne Timeout; Events gehen verloren, wenn kein Frontend verbunden ist | Job-Modell mit abfragbarem Status |
| Plugin-Update | ruft `_uninstall()` auf | dort nie Daten löschen |
| Subprozesse | `LD_LIBRARY_PATH` der PyInstaller-Laufzeit bricht Systemprogramme | mit `env -i` und minimaler Umgebung starten (wie in V4) |
| UI | Steam-Updates brechen `@decky/ui`-Komponenten gelegentlich | UI schlicht halten, Steam-Interna kapseln |
| Store | kein LLM-basierter Code | private Verteilung |

### 5.2 WowUp-CF (2.23.1; 2.24-Betas bereiten WoW: Forever vor)

**Datenablage**
- Dateien: `addons.json` und `preferences.json` in `~/.config/WowUpCf/`.
- Format: JSON (electron-store), bei jedem Zugriff neu eingelesen.
- Schreiben nur, wenn WowUp **nicht** läuft (Single-Instance-Sperre).

**Addon-Datensätze**
- Schlüssel ist `(installationId, providerName, externalId)`, denn die `id` ändert sich bei jedem Rescan.
- Update nötig, wenn `externalLatestReleaseId ≠ installedExternalReleaseId` oder `latestVersion ≠ installedVersion`.

**`--hidden --quit`**
- Ablauf: Auto-Update-Lauf → Beenden.
- Es gibt **keinen Ordner-Scan und kein Selbst-Update**.
- Installiert werden nur Addons mit `autoUpdateEnabled`. Die neuesten Versionen werden für alle nicht ignorierten Addons geholt.

**Client-Typen, d. h. was „alle Versionen“ technisch heißt**

| Typ | Name | Ordner |
|---|---|---|
| 0 | Retail | `_retail_` |
| 1 | Classic (MoP) | `_classic_` |
| 2 | RetailPtr | `_ptr_` |
| 3 | ClassicPtr | `_classic_ptr_` |
| 4 | Beta | `_beta_` |
| 5 | ClassicBeta | `_classic_beta_` (derzeit Forever-Beta) |
| 6 | ClassicEra | `_classic_era_` |
| 7 | ClassicEraPtr | `_classic_era_ptr_` |
| 8 | RetailXPtr | `_xptr_` |
| 9 | Anniversary | `_anniversary_` |

Offen: Produktcode und Ordner von WoW: Forever nach dem Start am 04.11.2026. Unterstützung kommt erst mit WowUp 2.24 oder neuer.

**Export-String:** Base64-kodiertes JSON `{collection_name, client_type, addons:[{id, name, provider_name, version_id}]}`. Damit lassen sich Addon-Listen vom PC übernehmen.

### 5.3 CurseForge

Das Plugin stellt **keine** Anfragen an die CurseForge-API und keine an das CurseForge-CDN. Alle Zugriffe macht WowUp-CF mit seinem eigenen Key, so wie vorgesehen. Den Key auszulesen oder mitzubenutzen bleibt tabu.

### 5.4 WoW-Spezifika

- **Spieltyp aus der Build-Version:** 1.15 = Vanilla, 1.60 = Forever, 2.5 = TBC, 3.x = Wrath, 4.4 = Cata, 5.5 = Mists, 12 = Retail. Die Interface-Nummer ist Major·10000 + Minor·100 + Patch.
- **Midnight:** Retail-Addons mit Interface < 120000 laden nicht, und es gibt keinen Override.
- **TOC-Varianten** je Flavor (`_Mainline`, `_Mists`, `_TBC`, `_Vanilla`, `_Camelot`, `_Classic` …); `## Interface:` kann eine Liste sein.
- **Groß-/Kleinschreibung:** Das Präfix ist unter SteamOS case-insensitiv (geprüft), unter Bazzite/btrfs nicht. Pfade deshalb immer case-insensitiv auflösen.
- **ROG Ally:** Xbox- und Armoury-Crate-Taste wirken beide als Steam-Taste.
  - Das Plugin muss vollständig mit Steuerkreuz und A/B bedienbar sein.
  - Es braucht einen Einstieg außerhalb des Quick Access Menus (QAM).

---

## 6. Architektur

```
┌──────────────────────── Steam-Oberfläche (CEF, Game Mode) ───────────────────────┐
│ Frontend: TypeScript/React, @decky/ui, @decky/api                                │
│  • QAM-Panel  • Vollbild-Route  • Button auf der Battle.net-Spielseite           │
│  • App-Start-/Ende-Hooks  • „WowUp sichtbar öffnen“ (Steam-Shortcut)             │
│  • src/steam/: einziger Ort mit Steam-Interna                                    │
└──────────────▲───────────── callable (RPC) / Events ─────────────────────────────┘
               │
┌──────────────┴────────── Backend main.py (Python 3.11, User „deck“) ─────────────┐
│ Decky-Adapter: API-Methoden · Job-Manager (1 schreibender Job) · Scheduler       │
│ ┌──────── Engine py_modules/wowcockpit/ (ohne Decky lauffähig und testbar) ────┐ │
│ │ discovery/ steam.py (VDF, compatdata) · battlenet.py (product.db) · wow.py   │ │
│ │ addons/    toc.py · compat.py · health.py                                    │ │
│ │ wowup/     store.py · runner.py · journal.py · placeholders.py · updater.py  │ │
│ │ ops/       snapshots.py · wtf_backup.py                                      │ │
│ │ state.py · net.py (nur GitHub-Releases) · cli.py                             │ │
│ └──────────────────────────────────────────────────────────────────────────────┘ │
└──────┬──────────────────────────────┬──────────────────────────────┬─────────────┘
       │ Dateien                      │ Subprozess                   │ Netz (selten)
  compatdata/…/AddOns, WTF    gamescope --backend headless --   api.github.com
  ~/.config/WowUpCf/*.json      WowUp-CF.AppImage --hidden --quit   (WowUp.CF-Releases)
```

### Leitentscheidungen

1. **WowUp-CF ist die einzige Addon-Engine.** Das Plugin steuert WowUp über drei Wege:
   - seine Datendateien,
   - seine CLI-Schalter,
   - einen unsichtbaren gamescope.
2. **Die Engine hängt nicht von Decky ab.**
   - Tests laufen auf dem Mac.
   - Für die Diagnose gibt es eine CLI, erreichbar per SSH.
   - Das Paket `wowcockpit` läuft auch im System-Python (3.13); deshalb ist ein Start-Wrapper möglich.
3. **Jede Änderung an WowUp-Dateien ist eine Transaktion.**
   - Vorbedingung: WowUp läuft nicht.
   - Vorher legt das Plugin ein Journal an.
   - Geschrieben wird atomar, Rechte und Tab-Einrückung bleiben erhalten, unbekannte Felder bleiben erhalten.
   - Nach einem Absturz stellt das Plugin beim nächsten Start aus dem Journal wieder her.
4. **Job-Modell.**
   - Es gibt höchstens einen schreibenden Job gleichzeitig.
   - Der Status ist jederzeit über `get_state()` abrufbar.
   - Events beschleunigen nur die Anzeige.
5. **Vor jedem Lauf ein Snapshot per Hardlink.** Das ist schnell und spart Platz, denn WowUp legt Dateien neu an statt sie zu überschreiben.
6. **Steam-Interna kapseln** (`src/steam/`), damit Brüche nach Steam-Updates lokal bleiben.

### 6.1 WowUp-Runner (validiert in V4, V6, V7 und V9)

| Punkt | Festlegung |
|---|---|
| Befehl | `gamescope --backend headless -W 1280 -H 800 -- <AppImage> --hidden --quit` |
| Umgebung | `env -i` mit `HOME`, `USER`, `LOGNAME`, `PATH=/usr/local/bin:/usr/bin:/bin`, `LANG`, `XDG_RUNTIME_DIR=/run/user/<uid>`; **kein** `DISPLAY`, `XAUTHORITY`, D-Bus oder `LD_LIBRARY_PATH` |
| Timeout | 120 s, danach `SIGKILL` an die ganze Prozessgruppe. Normal sind 5–7 s plus Downloadzeit. |
| Vorbedingungen | kein `wowup-cf`-Prozess aktiv; `wow_installations` nicht leer; AppImage ausführbar |
| Vor dem Lauf | Journal anlegen; `enable_system_notifications = "false"` setzen und den alten Wert merken; Flags je Lauf-Modus setzen; Snapshot anlegen |
| Nach dem Lauf | Neue Zeilen in `logs/main.log` auswerten (`[AddonUpdate]`, `[AddonUpdateComplete]`, `[QuitApp]`, `[error]`); `addons.json` mit dem Stand vorher vergleichen; Flags und Einstellung zurücksetzen; Journal schließen |
| Verboten | `--ozone-platform=headless` (stürzt ab); Sitzungs-Display ohne `XAUTHORITY` (stürzt ab und hängt) |
| Testmodus | `XDG_CONFIG_HOME` auf eine Sandbox-Kopie (wie im Spike) – für Entwicklung und für den Kanarienvogel-Test (6.5) |

### 6.2 Lauf-Modi über vorübergehend gesetzte Flags

| Modus | `autoUpdateEnabled` während des Laufs | Ergebnis |
|---|---|---|
| **Nur prüfen** | überall `false` | neueste Versionen aktualisiert, nichts installiert (V6) |
| **Auswahl aktualisieren** | nur die gewählten Addons `true` | genau diese werden aktualisiert |
| **Automatisch** | Einstellungen des Nutzers unverändert | Verhalten wie beim normalen WowUp-Start |

Nach dem Lauf stellt das Plugin die ursprünglichen Flags wieder her. Bei einem Absturz geschieht das beim nächsten Start aus dem Journal.

### 6.3 Installationen (alle WoW-Versionen)

1. **Eigene Erkennung:**
   - `shortcuts.vdf` → compatdata → `product.db` (Decoder in S2 geprüft) → `.build.info`/`.flavor.info`.
   - Ergebnis: alle Produkte mit Ordner, Version, Spieltyp und Interface.
2. **Übernahme in WowUp:** `blizzard_agent_path` auf `<pfx>/drive_c/ProgramData/Battle.net/Agent/product.db` setzen (die Datei, nicht den Ordner). Beim nächsten Lauf trägt WowUp fehlende Installationen selbst ein (V8b).
3. **Nacharbeit durch das Plugin:**
   - Doppelte Einträge erkennen und bereinigen (derselbe Pfad unter anderem Label).
   - Abweichende exe-Namen tolerieren.
   - Fallback: Installationen direkt in `wow_installations` schreiben, etwa bei anderen Laufwerken (`d:` → SD-Karte, ungetestet) oder bei mehreren Battle.net-Präfixen, denn WowUp kennt nur einen Agent-Pfad.
4. **Unbekannte Versionen:** Findet das Plugin einen Flavor, den WowUp noch nicht kennt (etwa WoW: Forever vor WowUp 2.24), zeigt es „von WowUp noch nicht unterstützt“ und verweist auf das WowUp-Update (6.5).

### 6.4 Neue Addons per Projekt-ID (validiert mit Immersion in V9)

1. **Platzhalter anlegen:** Ein vorhandener Datensatz dient als Vorlage.
   - Folgende Felder werden neu gesetzt:
     - neue `id` (UUID)
     - `providerName: "Curse"` und `externalId: "<Projekt-ID>"`
     - `installationId` und `clientType` der Ziel-Installation
     - `installedVersion: ""`, `installedExternalReleaseId: "0"`, `externalLatestReleaseId: "0"`
     - `installedFolderList: []`
     - `autoUpdateEnabled: true`, `isIgnored: false`
   - Alle übrigen Listen und Texte werden geleert.
2. **Installieren:** ein Lauf im Modus *Auswahl aktualisieren* nur für diesen Datensatz. WowUp-CF installiert die neueste passende Datei und ergänzt Name, Autor, Version und Ordner.
3. **Abhängigkeiten:** Nach dem Lauf `dependencies` auf Pflicht-Abhängigkeiten (Typ 2) prüfen und bei Bedarf weitere Platzhalter anlegen. WowUp installiert Abhängigkeiten nicht automatisch.
4. **Woher die Projekt-IDs kommen:**
   - aus kuratierten Paketen im Plugin (Projekt-IDs sind öffentliche Angaben),
   - aus einer WowUp-Exportliste vom PC,
   - per Eingabe (die ID steht auf der CurseForge-Seite des Addons).
   - Suchen ohne CF-API geht nicht; dafür bleibt „WowUp sichtbar öffnen“.
5. **Andere Quellen:** Für WoWInterface und GitHub vermutlich analog (`providerName` `WowInterface` bzw. `GitHub`, `externalId` = WoWI-ID bzw. `owner/repo`). Das ist noch nicht getestet.

### 6.5 WowUp-CF bereitstellen und aktuell halten

**Neuinstallation** (Einrichtungsassistent, „WowUp-CF nicht gefunden → Installieren“)
1. **Neuestes Release ermitteln:** über `api.github.com/repos/WowUp/WowUp.CF/releases`, je nach Kanal Stable oder Beta.
2. **Herunterladen und prüfen:**
   - `WowUp-CF-<ver>.AppImage` und `latest-linux.yml` in einen Arbeitsordner laden.
   - Das AppImage prüfen gegen `sha512` und `size` aus `latest-linux.yml` sowie gegen den `digest` (SHA-256) der GitHub-API (V10).
3. **Ablegen:**
   - Die Datei mit Rechten 0755 unter `~/Applications/WowUp-CF/WowUp-CF-<ver>.AppImage` speichern.
   - Den festen Link `~/Applications/WowUp-CF/WowUp-CF.AppImage` auf die aktuelle Version setzen.
   - Shortcuts und Menüeinträge zeigen auf den Link und müssen deshalb bei Updates nicht angepasst werden.
   - Die vorige Version bleibt für ein Rollback liegen.
4. **Erststart vorbelegen**, aber nur, wenn noch kein Profil existiert:
   - `~/.config/WowUpCf/preferences.json` mit `blizzard_agent_path` (auf `product.db`) und `enable_system_notifications: "false"` anlegen.
   - Der erste unsichtbare Lauf importiert dann alle Installationen (V11).
5. **Einwilligungen:** Telemetrie fragt der Assistent ab und schreibt dann `telemetry_enabled`. Die Werbe-Einwilligung von Overwolf bleibt bei WowUp und erscheint nur bei sichtbarer Nutzung.

**Vorhandenes AppImage übernehmen**
- **Suchen:** in `~`, `~/Applications`, `~/Downloads` und in Steam-Shortcuts.
- **Prüfen:** Die Datei gegen die Metadaten ihres Releases prüfen.
- **Übernehmen:** Die Datei bleibt, wo sie ist. Erst beim nächsten Update wechselt das Plugin in den verwalteten Ordner und bietet an, die alte Datei zu löschen.
- **Stand:** Bei dir gilt das für `~/WowUp-CF-2.23.1.AppImage`, die Prüfung hat gepasst (V10).

**Vorhandene Addons bei frischem Profil**
- **Problem:** `--quit` scannt keine Ordner. Addons, die schon im AddOns-Ordner liegen, kennt ein neues Profil deshalb nicht.
- **Ansätze (Spike S6):**
  - `--hidden` ohne `--quit` starten: Die unsichtbare Oberfläche scannt vermutlich; danach beendet das Plugin WowUp gezielt.
  - Einmal sichtbar öffnen (F23).
  - Platzhalter für Ordner anlegen, deren TOC eine `X-Curse-Project-ID` enthält.

**Integration (optional, im Assistenten)**
- `.desktop`-Eintrag in `~/.local/share/applications/`, damit WowUp im Desktop-Modus im Menü steht.
- Steam-Shortcut „WowUp-CF“ für die sichtbare Nutzung im Game Mode (F23). Beides zeigt auf den festen Link.

**Updates**
- **Warum:** Mit `--quit` aktualisiert sich WowUp nie selbst. Neue WoW-Versionen (Forever) und Änderungen bei CurseForge verlangen aber aktuelle WowUp-Versionen.
- **Prüfen:** einmal täglich die Releases unter `api.github.com/repos/WowUp/WowUp.CF/releases` abrufen.
  - Betas sind als `prerelease` markiert, derzeit etwa `v2.24.0-beta.5`.
  - Den WowUp-Kanal berücksichtigen (Stable oder Beta). Wie `wowup_release_channel_2_6` darauf abbildet, ist noch zu prüfen.
- **Laden:** `WowUp-CF-<ver>.AppImage` herunterladen und zweifach prüfen (am 24.09. nachgesehen, beides vorhanden):
  - gegen `latest-linux.yml` aus demselben Release (electron-builder: `sha512` in Base64 und `size`),
  - gegen den `digest` der GitHub-API (`sha256:…` je Asset).
- **Kanarienvogel-Test:** Die neue Version läuft zuerst einmal gegen eine Sandbox-Kopie im Modus „Nur prüfen“. Erst wenn der Lauf sauber endet und `addons.json` plausibel ist, schaltet das Plugin um. Die alte Version bleibt für ein Rollback liegen.
- **Umschalten:** nur, solange WowUp nicht läuft.

### 6.6 Backend-API (Entwurf)

| Methode | Zweck |
|---|---|
| `get_state()` | Gesamtstatus: Installationen, laufender Job, letztes Ergebnis, WowUp-Version, Warnungen |
| `detect_installations()` · `import_installations_into_wowup()` | Erkennung und Übernahme in WowUp (6.3) |
| `list_addons(installation_id)` | Addons mit Update-Status, Kompatibilität und Gesundheit |
| `run_update(installation_id \| null, mode, selection \| null)` → `job_id` | Lauf: `check` / `selected` / `auto` |
| `set_addon_flags(addon_key, flags)` | dauerhaft: Auto-Update / Ignorieren / Kanal |
| `install_by_project_id(installation_id, project_id, channel)` → `job_id` | Neuinstallation (6.4) |
| `install_bundle(installation_id, bundle_id)` · `import_wowup_export(installation_id, text \| path)` | Pakete und PC-Liste |
| `remove_addon(addon_key)` | Ordner und Datensatz entfernen (mit Snapshot) |
| `list_snapshots()` · `restore_snapshot(id, addon_key \| null)` | Rollback |
| `backup_wtf(installation_id)` · `list_wtf_backups()` · `restore_wtf(id)` | WTF-Backups |
| `find_wowup()` · `install_wowup(channel)` · `adopt_wowup(path)` | WowUp-CF finden, installieren oder vorhandene Datei übernehmen (6.5) |
| `check_wowup_update()` · `apply_wowup_update()` | WowUp-CF aktuell halten, mit Kanarienvogel-Test (6.5) |
| `get_settings()` · `set_settings(patch)` | Einstellungen |
| `check_for_update(force)` · `prepare_update()` | Update des Plugins prüfen und vorbereiten (6.8) |

**Events:** `job_progress`, `job_finished`, `updates_available`, `wowup_update_available`, `update_state`, `update_installed`.

### 6.7 Datenmodell (Skizze)

```jsonc
// settings.json  (DECKY_PLUGIN_SETTINGS_DIR)
{
  "schema": 1,
  "wowup": { "appImage": "/home/deck/WowUp-CF-2.23.1.AppImage", "keepPrevious": 1, "channel": "follow-wowup" },
  "runner": { "timeoutSec": 120, "disableNotificationsDuringRun": true },
  "automation": { "updateOnLaunch": true, "periodicHours": 6, "onlyOnAC": true,
                  "wtfBackupOnExit": true, "keepWtfBackups": 10 },
  "snapshots": { "keep": 5 }
}

// journal.json  (DECKY_PLUGIN_RUNTIME_DIR) – nur während eines Laufs vorhanden
{
  "runId": "2026-09-24T10:45:00Z-ab12", "mode": "selected",
  "prefs": { "enable_system_notifications": "true" },
  "flags": { "e52f7e70…|Curse|91376": { "autoUpdateEnabled": true } },
  "placeholders": ["<uuid>"], "snapshot": "snap-20260924-104500"
}
```

### 6.8 Auslieferung und Updates des Plugins (GitHub)

Vorbild ist `bassobr/decky-ally-dsp`, dein ausgereiftestes Plugin. Decky-CachyOS-Updater und Decky-Wifi-Streaming-Optimizer folgen demselben Muster. Übernommen wird dein eigener MIT-Code:
- `minisign.py` und `ed25519.py`
- das Updater-Muster
- `package.sh`, `dev-deploy.sh`, `gen-version.mjs`
- die Workflows und `install.sh`
- die Gliederung von `SECURITY.md`

| Baustein | Umsetzung für decky-wowup |
|---|---|
| Repo | `bassobr/decky-wowup`, öffentlich, MIT, Branch `main` |
| Rechte | `plugin.json` mit `"flags": []`, also ohne root |
| CI (`ci.yml`) | bei Push und Pull-Request: `pnpm install --frozen-lockfile` → build → typecheck → `pnpm audit --prod` → `compileall` und pytest (Python 3.11) → `bash -n` → unsigniertes ZIP als Artefakt; alle Actions per Commit-SHA fixiert |
| Release (`release.yml`) | Tag `vX.Y.Z` muss zur Version in `package.json` passen; gleiche Prüfungen; `scripts/package.sh` baut `<slug>-X.Y.Z.zip` und `SHA256SUMS` |
| Signatur | `SHA256SUMS` wird mit minisign signiert, mit **eigenem** Schlüsselpaar für dieses Repo. Das Secret `MINISIGN_SEED` liegt in GitHub Actions, `minisign.pub` ist eingecheckt. Danach folgt eine Gegenprüfung und `gh release create --generate-notes`. |
| Erstinstallation | `curl -sL …/raw/main/install.sh -o /tmp/… && sudo bash /tmp/…`. Das Skript holt das neueste Release, prüft Hash und Signatur, installiert nach `~/homebrew/plugins/<Name>`, setzt `chown deck` und startet `plugin_loader` neu. |
| Updates im Plugin | 1. `check_for_update` fragt alle 6 h die GitHub-API ab.<br>2. `prepare_update` prüft die Signatur von `SHA256SUMS` gegen den fest hinterlegten Schlüssel und liefert `{artifact, name, version, hash}`.<br>3. Das Frontend ruft `window.DeckyBackend.callable("utilities/install_plugin")(…, 2)` auf; Decky lädt, prüft den Hash und installiert. |
| Daten beim Update | Die Markierungsdatei `.update-pending` sorgt dafür, dass `_uninstall` beim Austausch nichts löscht. Nach dem Start meldet das Event `update_installed` die neue Version; optional folgt ein Steam-Neustart für das frische Frontend-Bundle. |
| Entwicklung | `scripts/dev-deploy.sh deck@10.10.10.21` baut, überträgt per tar über SSH, führt `sudo -n mv/chown` aus und startet `plugin_loader` neu |

Namen einheitlich halten, z. B.: Anzeigename „WoW Addons“ → Paket `wow-addons` → `wow-addons-X.Y.Z.zip` → Ordner `~/homebrew/plugins/WoW Addons`. Der Ordnername bestimmt auch, wo Daten und Einstellungen liegen. Die endgültige Wahl ist offen (Kap. 14).

---

## 7. Funktionsumfang

**Prio:** **M** = Must, **S** = Should, **C** = Could

### Kern (Phase 1)

| # | Funktion | Prio | Status |
|---|---|---|---|
| F1 | Installationen erkennen (alle Versionen) und in WowUp übernehmen, inkl. Nacharbeit | M | Mechanismus ✅ (S2, V8b) |
| F2 | Addon-Übersicht je Installation: Version, Update, Quelle, Kanal, Flags | M | Daten ✅ (S2) |
| F3 | Unsichtbarer Update-Lauf mit Ergebnis aus Log und `addons.json`-Vergleich | M | ✅ (V4) |
| F4 | Lauf-Modi „Nur prüfen“, „Auswahl“, „Automatisch“ über Flags, mit Journal | M | ✅ (V6) |
| F5 | Flags dauerhaft setzen: Auto-Update, Ignorieren, Kanal | S | – |
| F6 | Snapshot vor jedem Lauf (Hardlinks) und Rollback je Addon oder komplett | M | – |
| F7 | WTF-Backup nach Spielende (Zip, rotierend) und Wiederherstellen | S | – |
| F8 | Kompatibilitäts-Check: TOC-Interface gegen Spielversion (OK / veraltet / inkompatibel) | S | Prototyp ✅ (S2) |
| F9 | Gesundheitscheck: Case-Duplikate, verwaiste bzw. nicht verwaltete Ordner, fehlende Abhängigkeiten | C | Prototyp teilweise (S2) |
| F10 | Einrichtungsassistent: WowUp-CF finden oder installieren, Benachrichtigungen, Installationen, Vorbedingungen | M | – |
| F11 | Diagnose: Protokoll-Ansicht, Support-Paket | S | – |
| F12 | WowUp-CF bereitstellen und aktuell halten: herunterladen, prüfen, ablegen, Erststart vorbelegen, Updates mit Kanarienvogel-Test (6.5) | M | Prüfung ✅ (V10), frisches Profil ✅ (V11) |

### Automatik und Einstiege

| # | Funktion | Prio |
|---|---|---|
| F13 | Start-Hook: Startet Battle.net, läuft das Update parallel mit; Ergebnis als Toast | S |
| F14 | Button „Addons aktualisieren & spielen“ auf der Battle.net-Spielseite, mit Update-Zähler (Einstieg ohne QAM) | S |
| F15 | Start-Wrapper als Startoption (`…/pre-launch %command%`), Update garantiert vor dem Start, mit Timeout | C |
| F16 | Periodischer Check (nur am Netzteil, nicht während WoW läuft) und nach dem Standby | C |
| F17 | Bibliothekseintrag „WoW-Addons“ (Dummy-Shortcut öffnet die Vollbildseite) | C |

### Neue Addons (über WowUp-CF)

| # | Funktion | Prio | Status |
|---|---|---|---|
| F18 | Installation per CurseForge-Projekt-ID (Platzhalter) | S | ✅ (V9) |
| F19 | Kuratierte Pakete, z. B. das Controller-Paket: ConsolePort 91376 ✔, Immersion 257550 ✔, weitere IDs ergänzen | S | – |
| F20 | WowUp-Exportliste vom PC importieren (Base64-JSON, als Datei oder Text) → Platzhalter → WowUp installiert | S | – |
| F21 | Pflicht-Abhängigkeiten automatisch nachziehen | C | – |
| F22 | Addon entfernen (Ordner laut `installedFolderList` und Datensatz; mit Snapshot) | S | – |
| F23 | „WowUp sichtbar öffnen“ als Rückfallebene für Suche und Rescan (Touch/Trackpad), per Steam-Shortcut | S | – |

### Extras

| # | Funktion | Prio |
|---|---|---|
| F24 | Geräte-Sync (Addon-Liste als Export-String bzw. Datei, dazu WTF), z. B. zwischen Ally X, Deck und PC | C |
| F25 | Addon-Profile über `AddOns.txt` je Charakter, während WoW geschlossen ist | C |
| F26 | WeakAuras-/Plater-Updates von wago.io, wie beim WeakAuras Companion (Classic) | C |
| F27 | Speicherplatz-Übersicht, Snapshots und Backups aufräumen | C |
| F28 | Eigene Liste im WowUp-Format exportieren, z. B. für den PC | C |

---

## 8. UX-Konzept

**Prinzipien**
- **Controller zuerst:** Alles ist mit Steuerkreuz und A/B erreichbar; X, Y und ☰ sind nur Abkürzungen.
- **Einstiege:**
  - Das QAM zeigt Status und Schnellaktionen.
  - Die Vollbildseite dient der Verwaltung.
  - Die Battle.net-Spielseite ist der Einstieg im Kontext.
  - Optional kommt ein Bibliothekseintrag dazu.
- **Keine blockierenden Dialoge:** Läufe arbeiten im Hintergrund und melden das Ergebnis per Toast.
- **Lesbarkeit:** für 1280×800 (Deck) und 1920×1080 (Ally X).

**QAM-Panel**
```
┌ WoW-Addons ───────────────────────────┐
│ Version   [ Retail · Midnight 12.1 ▾ ]│
│ 12 Addons · 3 Updates · 1 inkompatibel│
│ Zuletzt geprüft: heute 10:42          │
│                                       │
│ [   Alle aktualisieren (3)   ]        │
│ [   Nach Updates suchen      ]        │
│ ── Updates ────────────────────────── │
│ ConsolePort       3.2.6 → 3.2.7       │
│ Immersion         1.4.60 → 1.4.61     │
│                                       │
│ [   Addons verwalten …       ]        │
│ ⓘ WowUp 2.24.0 verfügbar  [Update]    │
└───────────────────────────────────────┘
```

**Vollbildseite**
```
 Installiert │ Updates (3) │ Neu │ Versionen │ Backups │ Einstellungen │ Protokoll
┌──────────────────────────────────────────────────────────────────────────┐
│ ● ConsolePort            3.2.6 → 3.2.7      CurseForge   Stable   Auto   │
│ ○ Immersion              1.4.60             CurseForge   Stable   Auto   │
│ ⚠ AltesAddon             1.2 · Interface 110207 → lädt nicht (Retail)    │
│ ? Unbekannt: MeinOrdner  nicht von WowUp verwaltet                        │
└──────────────────────────────────────────────────────────────────────────┘
 Ⓐ Details   Ⓧ Aktualisieren   Ⓨ Filter   ☰ Mehr
```

**Tabs**
- **„Neu“:** Pakete (Controller-Paket …), „Projekt-ID eingeben“, „Liste vom PC importieren“, „WowUp öffnen (Suche)“.
- **„Versionen“:** alle erkannten WoW-Versionen mit Status in WowUp und Button „In WowUp übernehmen“.

**Detail-Dialog**
- **Angaben:** Name, Autor, Quelle, installierte und verfügbare Version, Kanal, Ordner, Interface und Kompatibilität, Changelog (nur als bereinigter Text).
- **Aktionen:** Aktualisieren · Auto-Update an/aus · Ignorieren · Kanal · Zurückrollen · Entfernen.

---

## 9. Sicherheit und Robustheit

- **Rechte:**
  - kein `root`-Flag
  - `sudo` nur für das Deployment in der Entwicklung, nie zur Laufzeit
- **Release-Integrität des Plugins:**
  - Der Updater vertraut einer Prüfsumme erst nach erfolgreicher Signaturprüfung gegen den eingebauten Schlüssel. Unsignierte Releases lehnt er ab.
  - Decky lehnt das ZIP ab, wenn der Hash nicht stimmt.
  - Grenzen: Der Seed liegt als Secret in GitHub Actions, und minisign kennt keinen Widerruf. Wie bei decky-ally-dsp in `SECURITY.md` dokumentieren.
- **Keine eigenen Zugriffe auf Addon-APIs:**
  - Das Plugin selbst spricht nur mit GitHub (WowUp-Releases).
  - Downloads nur über HTTPS mit Prüfsumme.
- **WowUp-Dateien:**
  - nur bei geschlossenem WowUp schreiben
  - vorher eine Kopie und ein Journal anlegen
  - atomar per `rename` schreiben
  - Rechte (0644), Einrückung und unbekannte Felder erhalten
- **Kein Datenverlust:**
  - vor jedem Lauf ein Snapshot
  - WTF nur bei geschlossenem WoW sichern
  - `_uninstall()` löscht nichts
- **Keine Hänger und Abstürze:**
  - harte Timeouts
  - nur die validierte Startvariante (gamescope headless)
  - Benachrichtigungen während des Laufs aus
- **Changelogs:** fremdes HTML nur bereinigt anzeigen. Das Frontend läuft im privilegierten Steam-Kontext, eingeschleustes Script (XSS) wäre dort gefährlich.
- **Privates:**
  - WowUps `sensitive.json` (falls vorhanden) nie lesen
  - Logs vor dem Export im Support-Paket von Pfaden mit Benutzernamen befreien

---

## 10. Risiken

| Risiko | Wahrsch. | Folge | Gegenmaßnahme |
|---|---|---|---|
| Der unsichtbare Lauf klappt aus dem Decky-Backend heraus nicht (anderer Prozesskontext als per SSH) | gering | kein unsichtbarer Lauf | Test-Plugin in S3; Fallback: `systemd-run --user` oder Display der Steam-Sitzung (`DISPLAY=:0`) |
| Eine neue WowUp-Version ändert Datenformat, `--quit` oder den Umgang mit Platzhaltern | mittel | Cockpit oder Neuinstallation gestört | Kanarienvogel-Test vor dem Umschalten, Versionsprüfung, defensiv lesen |
| CurseForge oder Overwolf ändern etwas an WowUp-CF | mittel | Updates stocken | liegt außerhalb des Plugins; WowUp aktuell halten (F12) |
| WoW: Forever bekommt am 04.11.2026 neuen Ordner oder Produktcode | sicher | Version unbekannt | datengetriebene Tabelle; Hinweis „WowUp-Update nötig“ |
| Steam-Update bricht Decky-UI oder Patches | mittel | UI zeitweise defekt | schlichte UI, Interna gekapselt, CLI als Rückfall |
| Decky entfernt weitere Stdlib-Module | mittel | Importfehler | Import-Guard-Test, möglichst nur Stdlib |
| Plugin und WowUp-Desktop schreiben gleichzeitig | gering | kaputte JSON | Prozessprüfung, atomare Writes, Journal |
| QAM auf der Ally schwer erreichbar | mittel | Bedienhürde | Spielseiten-Button (F14), Bibliothekseintrag (F17) |
| AppImage startet nicht, weil FUSE fehlt (z. B. auf anderen Distributionen) | gering | kein Lauf | Fallback `--appimage-extract-and-run` oder das AppImage einmalig entpacken |
| Neues Profil kennt die schon vorhandenen Addons nicht | mittel (nur bei Neuinstallation) | Addons bleiben unverwaltet | Spike S6; Rückfall: WowUp einmal sichtbar öffnen |

---

## 11. Roadmap

### Phase 0 – Spikes

| Spike | Status |
|---|---|
| S1 Unsichtbarer Lauf (Desktop-Modus) | ✅ V1–V9 |
| S1b Unsichtbarer Lauf im Game Mode (per SSH) | ✅ GM-V4 (6,0 s), GM-V6 (4,7 s) |
| **S1c** Unsichtbarer Lauf aus dem Decky-Backend heraus | ⏳ mit dem Test-Plugin (S3) |
| S2 Daten und Erkennung | ✅ |
| **S3** Repo `bassobr/decky-wowup` und Gerüst nach dem Muster von decky-ally-dsp (CI, signierte Releases, `install.sh`, Updater), Dev-Deployment, CEF-Debugging | ⏳ braucht Freigabe: Repo anlegen, Schlüssel erzeugen, Deployment |
| **S4** Steam-Hooks: App-ID des Battle.net-Shortcuts in `RegisterForAppLifetimeNotifications` (Quellen widersprechen sich), Spielseiten-Patch | ⏳ zusammen mit S3 |
| S5 CurseForge-Key | entfällt (Entscheidung) |
| **S6** Frisches Profil: vorhandene Addons ohne sichtbares Fenster erkennen lassen (z. B. `--hidden` ohne `--quit`, danach gezielt beenden) | ⏳ |

### Phase 1 – MVP „Cockpit“

1. **Engine:** `discovery`, `wowup/store`, `wowup/runner`, `wowup/journal`, `state`, CLI, Tests. Die Testfälle stammen aus den Spikes.
2. **Backend:** API, Job-Manager, `get_state`.
3. **Frontend:** QAM-Panel und Vollbildliste mit F2, F3, F4.
4. **Absicherung:** Snapshots mit Rollback (F6) und Einrichtungsassistent (F10).
5. **Übernahme aller Versionen** (F1) sowie WowUp-CF bereitstellen und aktuell halten (F12).

**Fertig, wenn:**
- alle Addons jeder Version im Game Mode unsichtbar aktualisiert werden,
- „Nur prüfen“ und Rollback funktionieren,
- keine root-eigenen Dateien entstehen,
- WowUp danach normal weiterläuft,
- das Ganze eine Woche Alltag übersteht.

### Phase 2 – Komfort und neue Addons

- **Komfort:** F5, F7, F8, F11, F13, F14
- **Neue Addons:** F18–F20, F22, F23

### Phase 3 – Extras

- F9, F15–F17, F21, F24–F28

---

## 12. Projektstruktur (Vorschlag)

Die Struktur folgt `decky-ally-dsp`.

```
decky-wowup/
├── .github/workflows/       # ci.yml · release.yml (Actions per SHA fixiert)
├── plugin.json              # "flags": [] – ohne root; api_version 1
├── package.json             # "type": "module", Version = Release-Tag
├── pnpm-lock.yaml · pnpm-workspace.yaml · rollup.config.js · tsconfig.json
├── main.py · decky.pyi      # dünner Decky-Adapter
├── py_modules/wowcockpit/   # Engine (Python ≥ 3.11, nur Stdlib, keine Decky-Imports)
│   ├── discovery/ · addons/ · wowup/ · ops/
│   ├── state.py · net.py · cli.py · paths.py · constants.py · log.py
│   └── minisign.py · ed25519.py · updater.py      # aus decky-ally-dsp übernommen
├── src/
│   ├── index.tsx · backend.ts · updateFlow.ts · appWatcher.ts · strings.ts
│   ├── components/ · hooks/
│   └── steam/               # SteamClient-Hooks, Spielseiten-Patch, Shortcuts
├── scripts/                 # package.sh · dev-deploy.sh · gen-version.mjs · spike/
├── tests/                   # pytest; conftest.py, fixtures/ aus S2 (anonymisiert)
├── docs/                    # konzept.md (dieses Dokument), architecture.md
├── install.sh · minisign.pub · SECURITY.md · CHANGELOG.md · README.md
└── LICENSE                  # MIT
```

- **Name:** In der README als **inoffiziell** kennzeichnen, also ohne Verbindung zum WowUp-Projekt.
- **Plugin-Ordnername:** überall gleich halten, er bestimmt, wo Daten und Einstellungen liegen (siehe 6.8).

---

## 13. Entwicklungs-Setup (Mac → Ally X)

- **Gerät:** `ssh deck@10.10.10.21` (SSH-Key); `sudo` geht ohne Passwort. Es wird nur fürs Deployment genutzt, und nur nach Freigabe.
- **Build:** `pnpm i && pnpm build` nativ am Mac. Kein Docker nötig, weil das Plugin kein eigenes Backend-Binary hat.
- **Dev-Deployment:** `scripts/dev-deploy.sh deck@10.10.10.21`, wie bei decky-ally-dsp:
  1. baut das Plugin,
  2. überträgt es per tar über SSH nach `/tmp`,
  3. verschiebt es mit `sudo -n` nach `~/homebrew/plugins/<Name>` und setzt `chown deck`,
  4. startet `plugin_loader` neu.
- **Release:** Tag `vX.Y.Z` passend zur Version in `package.json` setzen. GitHub Actions baut, testet, signiert und veröffentlicht; das Gerät holt das Update dann über den Updater im Plugin.
- **Debugging:**
  - Frontend: Decky → Einstellungen → Entwicklermodus → „Allow Remote CEF Debugging“; am Mac `chrome://inspect` → `10.10.10.21:8081`. Der Entwicklermodus ist derzeit **aus**.
  - Backend-Logs: `~/homebrew/logs/decky-wowup/` und `journalctl -u plugin_loader`.
- **Tests:** pytest am Mac (Python 3.11 und 3.13). Dazu ein Sandbox-Integrationstest auf dem Gerät wie im Spike, mit `XDG_CONFIG_HOME` und Schein-Installation.
- **Sandbox:** `~/wowup-spike/` liegt noch auf dem Gerät (47 MB AddOns-Kopie, Konfigurationskopie, `run.sh`) und wird für weitere Tests wiederverwendet (S1c, Kanarienvogel-Test).

---

## 14. Offene Fragen

| # | Frage | Vorschlag |
|---|---|---|
| 1 | Darf ich das öffentliche Repo `bassobr/decky-wowup` anlegen, ein eigenes Signaturschlüsselpaar erzeugen und den Seed als Secret `MINISIGN_SEED` hinterlegen? | ja, wie bei deinen anderen Plugins |
| 2 | Wie soll das Plugin heißen (Anzeige, ZIP, Plugin-Ordner)? | „WoW Addons“ / `wow-addons-X.Y.Z.zip` |
| 3 | Dev-Deployment per `scripts/dev-deploy.sh` (`sudo -n`, Neustart von `plugin_loader`)? | ja, wie bei decky-ally-dsp |
| 4 | Decky-Entwicklermodus einschalten (CEF-Debugging)? | ja, für die Entwicklungszeit |
| 5 | WowUp-Benachrichtigungen: nur während Plugin-Läufen aus oder dauerhaft? | nur während der Läufe |
| 6 | Updates beim Spielstart ohne Rückfrage? | ja für Addons mit Auto-Update |
| 7 | Soll das Plugin WowUp-CF aktualisieren, und über welchen Kanal? | ja, gleicher Kanal wie in WowUp |
| 8 | Welche Addons gehören ins Controller-Paket? | ConsolePort, Immersion, weitere nach Wunsch |
| 9 | Wohin soll WowUp-CF installiert werden, und soll die vorhandene Datei in `~` übernommen werden? | `~/Applications/WowUp-CF/` mit festem Link; vorhandene Datei nach Prüfung übernehmen |
| 10 | Menüeintrag im Desktop-Modus und Steam-Shortcut für WowUp anlegen? | ja, beides optional im Assistenten |

## 15. Nächste Schritte

1. **Repo und Gerüst (S3):**
   - `bassobr/decky-wowup` anlegen.
   - Gerüst nach dem Muster von decky-ally-dsp aufbauen: CI, signierte Releases, `install.sh`, Updater.
   - Signaturschlüssel als Secret hinterlegen.
2. **Erstes Dev-Deployment** per `scripts/dev-deploy.sh`. Danach S1c (unsichtbarer Lauf aus dem Decky-Backend) und S4 (Steam-Hooks) testen.
3. **Phase 1:** Engine-Kern (`discovery`, `wowup/*`) mit Tests aus den Spike-Daten, danach das MVP-UI. Das erste Release ist `v0.1.0`.

---

## Anhang A: Merkzettel

**Unsichtbarer Lauf (validiert):**
```bash
env -i HOME="$HOME" USER=deck LOGNAME=deck PATH=/usr/local/bin:/usr/bin:/bin LANG=C.UTF-8 \
    XDG_RUNTIME_DIR=/run/user/1000 \
  timeout -k 5 120 gamescope --backend headless -W 1280 -H 800 -- \
    "$HOME/WowUp-CF-2.23.1.AppImage" --hidden --quit
```

**Relevante Logzeilen (`~/.config/WowUpCf/logs/main.log`):**
```
[info]  onAutoUpdateInterval
[info]  [AddonUpdate] Curse 91376 ConsolePort '3.2.5' -> '3.2.6'
[info]  [AddonUpdateComplete] Curse 91376 ConsolePort 3.2.6
[info]  [QuitApp]
[info]  Cannot import wow installations, no agent path      ← ohne blizzard_agent_path
[info]  Setting wow installations: 3                        ← nach Import über product.db
```

**Sandbox für Tests:** Das Plugin prüft neue WowUp-Versionen (Kanarienvogel-Test) mit `XDG_CONFIG_HOME=<kopie>`. Die Kopie enthält eine Schein-Installation mit leerer `Wow.exe` und einer AddOns-Kopie.

**Erststart eines frischen Profils vorbelegen (validiert in V11):**
```json
{
	"blizzard_agent_path": "<pfx>/drive_c/ProgramData/Battle.net/Agent/product.db",
	"enable_system_notifications": "false"
}
```
Das ist `~/.config/WowUpCf/preferences.json`, nur anlegen, wenn noch kein Profil existiert. WowUp ergänzt beim ersten Lauf alle Standardwerte und die Installationen.

**Prüfsummen eines WowUp-CF-Release (validiert in V10):** SHA-512 als Base64 aus `latest-linux.yml` und `sha256:<hex>` aus dem Feld `assets[].digest` der GitHub-API.

**Bekannte Projekt-IDs:** ConsolePort `91376`, Immersion `257550`.

---

## Anhang B: Quellen (Auswahl, geprüft am 24.09.2026)

- **Eigene Vorlage**
  - decky-ally-dsp (Build, Signatur, Updater, `install.sh`): https://github.com/bassobr/decky-ally-dsp
  - Release-Metadaten von WowUp-CF (`latest-linux.yml`): https://github.com/WowUp/WowUp.CF/releases/latest
- **Decky**
  - Plugin-Vorlage: https://github.com/SteamDeckHomebrew/decky-plugin-template
  - Loader v3.2.9: https://github.com/SteamDeckHomebrew/decky-loader/releases/tag/v3.2.9
  - Fehlende Stdlib-Module: https://github.com/SteamDeckHomebrew/decky-loader/issues/968
  - Store-Regeln: https://wiki.deckbrew.xyz/en/plugin-dev/submitting-plugins
  - CEF-Debugging: https://wiki.deckbrew.xyz/en/plugin-dev/cef-debugging
- **WowUp**
  - Quellcode: https://github.com/WowUp/WowUp (`wowup-electron/app/main.ts`, `src/app/app.component.ts`, `src/common/wowup/product-db.ts`)
  - CF-Build (Releases): https://github.com/WowUp/WowUp.CF/releases
- **CurseForge**
  - Nutzungsbedingungen: https://support.curseforge.com/support/solutions/articles/9000207405
  - Download-Key: https://blog.curseforge.com/introducing-api-key-authentication-for-curseforge-file-downloads/
- **WoW**
  - TOC-Format: https://warcraft.wiki.gg/wiki/TOC_format
  - Midnight-API: https://warcraft.wiki.gg/wiki/Patch_12.0.0/Planned_API_changes
  - WoW: Forever: https://news.blizzard.com/en-us/article/24301508/pre-purchase-world-of-warcraft-forever-upgrades-and-begin-your-next-journey-in-azeroth
- **Steam, Proton und Geräte**
  - `product.db` (Lutris): https://github.com/lutris/lutris/blob/master/lutris/services/battlenet.py
  - Shortcut-IDs (protontricks): https://github.com/Matoking/protontricks/blob/master/src/protontricks/steam.py
  - SteamOS 3.8: https://store.steampowered.com/news/app/1675200
  - Ally-Tasten: https://github.com/ValveSoftware/SteamOS/issues/2540
  - gamescope-Headless: https://github.com/ValveSoftware/gamescope/issues/1984
- **Projekt-ID Immersion:** https://www.curseforge.com/wow/addons/immersion
