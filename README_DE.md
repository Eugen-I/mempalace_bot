# MemPalace Bot 🤖

Telegram-Bot für KI-Kommunikation (lokal oder via API), Suche in persönlichen Notizen (MemPalace), YouTube-Downloads, Transkriptionen und vieles mehr. Läuft nur auf Ihrem Computer. Solange der Computer läuft, läuft auch der Bot.

> Der Bot wurde für den **persönlichen Gebrauch** entwickelt und wird nach Bedarf des Autors erweitert.

---

## 📦 Installation

### Voraussetzungen

- **Mac-Computer** (Intel, 4× langsamer, oder Apple Silicon M1/M2/M3/M4)
- **Internetverbindung**
- **Telegram-Konto**
- Grundlegende Kenntnisse zum Kopieren/Einfügen von Text

### Schritt 1: Homebrew installieren (falls nicht vorhanden)

Terminal öffnen (`⌘ + Leertaste`, „Terminal" eingeben, Enter):

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Schritt 2: Python und FFmpeg installieren

```bash
brew install python@3.12 ffmpeg tesseract tesseract-lang
```

### Schritt 3: MemPalace installieren

```bash
brew install anomalyco/tap/mempalace
```

### Schritt 4: Bot herunterladen

```bash
cd ~/Documents
git clone https://github.com/Eugen-I/mempalace_bot.git
cd mempalace_bot
```

### Schritt 5: Virtuelle Umgebung erstellen

```bash
python3.12 -m venv venv
source venv/bin/activate
```

### Schritt 6: Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### Schritt 7: Konfigurationsdatei erstellen

```bash
cp .env.example .env
```

`.env` mit einem Texteditor öffnen und ausfüllen:

```
TELEGRAM_BOT_TOKEN= — Token von @BotFather
ADMIN_ID= — Ihre Telegram-ID
ALLOWED_USERS= — Weitere Benutzer-IDs (kommagetrennt)
GEMINI_API_KEY= — Google-Gemini-API-Schlüssel
OPENAI_API_KEY= — OpenAI-API-Schlüssel (optional)
```

Falls Ihr MemPalace-Ordner **nicht** in `~/Documents/mempalace` liegt:
```
MEMPALACE_DATA_DIR=/pfad/zu/ihrem/mempalace
```

### Schritt 8: Bot starten

```bash
python3 main.py
```

Erwartete Ausgabe: `🦾 MemPalace запущен.`  
Dann in Telegram den Bot öffnen und `/start` senden.

---

## 🎮 Bedienung

### Hauptmenü-Buttons

| Button | Funktion |
|--------|----------|
| 🆕 Neuer Dialog | Neues KI-Gespräch starten |
| 📂 Chat-Liste | Alle Dialoge anzeigen |
| ⚙️ Einstellungen | KI-Modell, Sprachmodus wählen |
| 🔍 Flügel-Suche | In Notizen nach Thema suchen |
| 🔄 Synchronisierung | Dialog in MemPalace speichern |
| 📹 Video downloaden | YouTube-Video (480/720p) |
| 🎵 MP3 downloaden | YouTube-Audio + Transkription |
| 📝 Persönliche Notiz | Schnelle Gedankennotiz |
| 📖 Meine Gedanken | Gespeicherte Notizen verwalten |
| 🏰 Palast | Wissenspalast-Menü |

### 🤖 KI-Kommunikation

Einfach Nachrichten senden – der Bot antwortet via KI (Gemini / Ollama / OpenAI).

**Spezielle Befehle in Nachrichten:**

| Symbol | Aktion |
|--------|--------|
| `!` Text | Notiz schnell in `my_notes` speichern |
| `!!` | Einsicht aus der letzten KI-Antwort extrahieren |
| `???` | Letzte Antwort als Recherche in `research` speichern |
| `/search text` | Suche in der MemPalace-Datenbank |
| `/search --wing dreams text` | Suche in einem bestimmten Flügel |
| `/philosophy: was ist sein?` | Flügel via `/` angeben |

### 📄 PDF-Verarbeitung

PDF senden – der Bot:
1. Extrahiert Text (mit OCR auf Deutsch, Russisch, Englisch)
2. Erkennt Dokumenttyp (Medizin / Finanzen / Persönlich)
3. Führt präzise Analyse durch (Zahlen, Daten, Begriffe erhalten)
4. Speichert Original im Archiv

**Befehle:**
- `/pdfs` — Liste gespeicherter PDFs, erneute Analyse möglich
- Button „Vergleichen" — Fragen zum Dokument (2 Min. Timer)
- Automatisches Chunking großer PDFs (>25K Zeichen)

### 🎤 Sprachnachrichten

Sprachnachricht senden – der Bot:
1. Erkennt Sprache via Whisper (lokal auf Ihrem Mac)
2. Antwortet per Text oder Stimme (einstellbar)

Drei Modi: nur Text / nur Stimme / beides.

### 📸 Fotoanalyse

Foto senden – der Bot analysiert es, wenn die Nachricht Stichworte wie „Foto", „analysiere", „image" enthält.
Unterstützt alle multimodalen Modelle.

### 🧠 Langzeitgedächtnis

Der Bot extrahiert automatisch:
1. Schlüsselfakten aus jedem Dialog
2. Speichert sie in einer separaten Gedächtnisdatenbank
3. Fügt bei Folgefragen relevante Fakten in den KI-Kontext ein

Alle 5 Nachrichten wird der Dialog automatisch mit MemPalace synchronisiert.

### 🔄 Reaktionen auf KI-Antworten

Reaktion auf eine Bot-Nachricht:
- 👍 → in `my_notes` speichern
- ❤️ → als Einsicht in `insights` speichern
- 🤷 → als Recherche in `research` speichern

---

## 📋 Vollständiger Funktionsumfang

### 🏰 Wissenspalast (Palace)

**Navigation:**
- `🕸️ Flügel` — Übersicht der Hauptbereiche (Projekte, Personen, Themen) mit Anzahl Einträgen
- `🪪 Räume` — Unterbereiche eines Flügels anzeigen
- `🏛️ Taxonomie` — Vollständiger Baum: Flügel → Raum → Einträge
- `📊 Graph` — Kreuzungsstatistik, Tunnelanzahl zwischen Flügeln

**Tunnel (Verbindungen zwischen Räumen verschiedener Flügel):**
- `📋 Liste` — Alle erstellten Tunnel
- `🔍 Zwischen Flügeln` — Gemeinsame Räume zweier Flügel finden
- `➡️ Betreten` — Raum mit verknüpften Einträgen durchlaufen
- `➕ Erstellen` — 4-Schritte-Assistent zur Tunnel-Erstellung
- `🔀 Traversieren` — Graph ab Raum mit N Schritten durchlaufen

**Wissensgraph (KG):**
- `📊 Statistik` — Entitäten, Fakten, Beziehungstypen
- `🔍 Entität suchen` — Alle Fakten über eine Entität (mit Paginierung, Verweis auf Quellen)
- `➕ Fakt hinzufügen` — 3-Schritte-Assistent (Subjekt → Prädikat → Objekt)

**Wartung:**
- `🔁 Index neu aufbauen` — Vollständige Neuindizierung
- `🗜️ DB komprimieren` — Alte ChromaDB-Segmente bereinigen
- `📦 Text komprimieren` — Duplikate entfernen, ähnliche Einträge zusammenführen
- `🌙 In Kontext laden` — Flügel in Arbeitsspeicher laden

### 📝 Persönliche Notizen

**„📝 Persönliche Notiz"** — Schnell eine Gedankennotiz:
1. Text oder Sprachnachricht senden
2. KI formatiert (Zeichensetzung, Absätze, keine Interpretation)
3. KI klassifiziert – schlägt Flügel und Raum basierend auf Taxonomie vor
4. Bestätigen oder manuell ändern
5. Speichern + Kopie in `persönliche_gedanken/inbox`

**„📖 Meine Gedanken"** — Verwalten:
- Liste aus `persönliche_gedanken/inbox` (5er-Paginierung)
- Vorschau → Vollansicht (>4000 Zeichen werden aufgeteilt)
- `💾 In Palast` — Notiz in anderen Flügel/Raum kopieren
- `💬 Zitat` — Fragment auswählen und speichern
- `🗑️ Löschen` — mit Bestätigung, endgültig

### 📸 Fotos

- Auto-Speicherung gesendeter Fotos in `photos/`
- Buttons „Letztes analysieren" / „Letztes löschen"
- `/photos` — Alle Fotos mit Löschbuttons
- Auto-Einfügung der letzten 2 Fotos in KI-Kontext bei Foto-Erwähnung

### 🎙️ Sprache & Sprachausgabe

- Spracherkennung via `faster-whisper` (lokal, CPU, Base Model)
- Sprachausgabe via macOS `say` + ffmpeg (OGG, 64k, Stimme Milena)
- Drei Modi: nur Text / nur Stimme / beides
- Geschwindigkeit: 100–300 wpm (einstellbar)

### 🎬 YouTube

- `📹 Video downloaden` — Qualität 480p / 720p via yt-dlp
- `🎵 MP3 downloaden` — Audio extrahieren, transkribieren, in `transkript/` speichern

### 📄 PDF

- Auto-Extraktion (PyMuPDF + Tesseract OCR für Scans)
- 9 Analysetypen (Medizin, Psychologie, Literatur, Programmierung, Sport u.a.)
- Zwei PDFs vergleichen (`/compare`)
- `/pdfs` — PDF-Archiv mit erneuter Analysemöglichkeit
- Auto-Chunking (>25K Zeichen)
- Vorlesen der Ergebnisse

### 💬 Chats

- `🆕 Neuer Dialog` — Neuen Chat erstellen
- `📂 Chat-Liste` — Chats anzeigen und löschen
- `/history` — Letzte 10 Nachrichten
- `/export` — Chat als `.md` exportieren
- `~` / `#ctx` — Zusammenfassung anzeigen/generieren
- Auto-Zusammenfassung alle 5 Nachrichten
- `🔄 Synchronisierung` — Chat in MemPalace exportieren (manuell oder alle 5 Nachrichten)

### 🧠 Langzeitgedächtnis

- Faktenextraktion aus jedem Dialog (im Hintergrund via `asyncio.create_task`)
- Speicherung in `memory_store/mem_{user_id}.json`
- Einfügung relevanter Fakten in KI-Kontext

### ⚙️ Einstellungen

- KI-Modell wählen: Gemini Flash / Ollama (beliebig) / OpenAI
- Drei Antwortmodi: Text, Stimme, beides
- Sprachgeschwindigkeit einstellen
- MCP-Zugang zum Palast
- Vollständige Hilfe zu allen Funktionen

### 🎭 Reaktionen auf KI-Antworten

Reaktion auf Bot-Nachricht:
- 👍 → `my_notes/`
- ❤️ → `insights/`
- 🤷 → `research/`

(Cache speichert die letzten 50 KI-Antworten)

### 🔍 Suche

- `/search anfrage` — Globale Suche in MemPalace
- `/search --wing dreams anfrage` — Suche in bestimmtem Flügel
- `📖 Einträge lesen` — Volltext der gefundenen Ergebnisse anzeigen

### 💻 CLI-Schnittstelle

```bash
python3 cli_ask.py
```

Vollwertiger Terminal-Client mit Syntax-Highlighting, Verlauf und allen Palast-/KI-Befehlen.

**Palast-Befehle (CLI):**
| Befehl | Aktion |
|--------|--------|
| `/palace` | Palast-Befehle anzeigen |
| `/status` | MemPalace-Statistik |
| `/mcp` | MCP-Einrichtungsanleitung |
| `/wakeup` | Palast in aktiven Kontext laden |
| `/repair` | Vektorindex neu aufbauen |
| `/compress` | Speicher komprimieren |

---

## 📂 `_scripts` — Fertige Skripte

Alle Skripte funktionieren per Doppelklick (`.command`).

### 🚀 Start & Verwaltung

| Skript | Wann ausführen | Funktion |
|--------|----------------|----------|
| **Ollama_Start** | Vor erstem Bot-Start | Ollama-Server starten |
| **start_bot** | Bei jedem Bot-Start | Telegram-Bot starten |
| **PalaceManager_TelegrammBot** | Für volle Kontrolle | Menü: Start (interaktiv/im Hintergrund), Stopp, Logs, Bereinigung |
| **KillPalaceBot** | Wenn Bot hängt | Alle Bot-Prozesse beenden |
| **Switch_AI** | KI-Modell wechseln | Aktives Modell aus Ollama/OpenAI/Gemini wählen |
| **setup_env** | Bei Ersteinrichtung | `.env`-Menü (Token, Schlüssel, ID) |
| **RestoreConfig** | Bei fehlenden Aliassen | `mempalace`-Befehl wiederherstellen |

### 🧠 MemPalace-Verwaltung

| Skript | Wann ausführen | Funktion |
|--------|----------------|----------|
| **update_memory** | Nach Notiz-Hinzufügung | MemPalace-DB aus `my_notes` aktualisieren |
| **update_memory_insights_research** | Nach Einsichten/Recherchen | DB aus `insights` und `research` aktualisieren |
| **update_memory_wingMode** | Für Themenzuordnung | Notizen mit Auto-Flügelzuordnung indizieren |
| **check_memory** | Zum DB-Status | MemPalace-Status + Dateiliste |
| **clear_memory** | Zum DB-Reset | MemPalace-Speicher leeren (Dateien bleiben) |
| **Ask_Memory** | Für schnellen KI-Dialog | CLI-Modus (ohne Telegram) |
| **Run_Extraction** | Für Gedankenextraktion | Extraktion wichtiger Fakten |

### 🔍 Suche & Werkzeuge

| Skript | Wann ausführen | Funktion |
|--------|----------------|----------|
| **find_memory** | Notizen durchsuchen | Endlose Suche mit Mengen-/Schwellenwert-Einstellung |
| **go_to_memory** | Terminal im DB-Ordner | Zum MemPalace-Ordner mit aktivierter Umgebung |
| **Archive_Chat** | Dialog speichern | Ausgewählten Chat in `my_notes` verschieben |
| **Daily_Note** | Tägliche Notiz | Tägliche Notiz öffnen (falls konfiguriert) |

### ⚙️ Modelle & Wartung

| Skript | Wann ausführen | Funktion |
|--------|----------------|----------|
| **Manage_Wechsel_Models** | Modell hinzufügen/entfernen | `models.json`-Verwaltung |
| **Ollama_Cleaner** | Bei wenig Speicher | Installierte Ollama-Modelle anzeigen/löschen |
| **import_notes** | Beim Import aus Apple Notes | Notizen aus Apple Notes importieren |

---

## 🖥️ MemPalace Bot.app

Native macOS-Anwendung, die alle 22 Skripte in einem Fenster mit Dark Mode bündelt.

**Nutzung:**
1. `MemPalace Bot.app` an gewünschten Ort verschieben
2. Doppelklicken → Fenster mit 4 Spalten:
   - **🚀 Start** — Bot, Ollama, Verwaltung
   - **🧠 Speicher** — MemPalace aktualisieren/prüfen
   - **🔍 Werkzeuge** — Suche, Archivierung, Daily Note
   - **⚙️ Wartung** — Modelle, Bereinigung, Konfiguration
3. Skript klicken – automatische Erkennung:
   - 🪟 **Terminal** — für interaktive Skripte
   - ⚡ **Hintergrund** — Ausgabe im App-Fenster
4. ⏹ **Stopp** — Hintergrundaufgaben beenden
5. 📎 **.command** — Eigenes Skript hinzufügen
6. 📝 **Code einfügen** — Skript direkt in der App erstellen

**Datenpfad:** `~/Library/Application Support/MemPalaceBot/`

---

## 🧹 Fehlerbehebung

**Bot antwortet nicht:**
- Läuft der Bot? (Im Terminal sollte `Bot polling started` stehen)
- Stimmt der Token in `.env`?
- Läuft der Bot nur einmal? (Zwei Instanzen konfligieren)
- `KillPalaceBot.command` zur erzwungenen Beendigung, dann neu starten

**Fehler „Module not found":**
- `pip install -r requirements.txt` erneut ausführen
- Virtuelle Umgebung aktivieren: `source venv/bin/activate`

**Fehler „venv/bin/activate: No such file or directory":**
- `python3.12 -m venv venv` im Projektordner ausführen

**Fehler „TELEGRAM_BOT_TOKEN not found":**
- `.env` im Projektordner prüfen
- Zeile `TELEGRAM_BOT_TOKEN=ihr_token` vorhanden?

**Bot läuft, aber reagiert nicht auf Befehle:**
- Schreiben Sie dem Bot direkt in Telegram
- `/start` zur Initialisierung senden

**PDF wird nicht verarbeitet:**
- Tesseract installiert? `brew install tesseract tesseract-lang`
- Große PDFs (>50 Seiten) brauchen länger

**YouTube-Download fehlschlägt:**
- FFmpeg installiert? `brew install ffmpeg`
- Link muss auf ein Video verweisen (keine Playlist)

**Fehler „No module named 'yt_dlp'":**
- `pip install -r requirements.txt` erneut ausführen

**Bot aktualisieren:**
```bash
cd ~/Documents/mempalace_bot && git pull && source venv/bin/activate && pip install -r requirements.txt
```

**Logs:**
- Bot-Logs: `bot_debug.log` im Projektordner
- Start-Logs: `nohup.out` im Projektordner (automatisch gelöscht)

---

## 📄 Lizenz

MIT License — frei verwendbar, veränderbar und teilbar mit Namensnennung.
