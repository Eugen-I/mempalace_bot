# MemPalace Bot 🤖

Ein Telegram-Bot, der mit KI kommuniziert (lokal oder über API), in deinen persönlichen Notizen (MemPalace) sucht, YouTube-Videos herunterlädt, Transkriptionen erstellt und vieles mehr. Läuft nur auf deinem Computer. Solange der Computer läuft, läuft auch der Bot.

## 🔧 Voraussetzungen

- **Mac-Computer** (Intel — 4x langsamer, oder Apple Silicon M1/M2/M3)
- **Internetverbindung**
- **Telegram-Konto**
- **Grundkenntnisse im Kopieren/Einfügen** — der Rest wird Schritt für Schritt erklärt

---

## 📦 Installation

### Schritt 1. Homebrew installieren (falls nicht vorhanden)

Öffne das **Terminal** (`⌘ + Leertaste`, `Terminal` eingeben, Enter drücken).

Füge diesen Befehl ein und drücke Enter:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Schritt 2. Python und FFmpeg installieren

```bash
brew install python@3.12 ffmpeg
```

### Schritt 3. MemPalace installieren

```bash
brew install anomalyco/tap/mempalace
```

### Schritt 4. Bot herunterladen

```bash
cd ~/Documents
git clone https://github.com/Eugen-I/mempalace_bot.git
cd mempalace_bot
```

### Schritt 5. Virtuelle Umgebung erstellen

```bash
python3.12 -m venv venv
source venv/bin/activate
```

### Schritt 6. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
```

### Schritt 7. Konfigurationsdatei erstellen

```bash
cp .env.example .env
```

Öffne `.env` und fülle aus:

```
TELEGRAM_BOT_TOKEN= — dein Token von @BotFather
ADMIN_ID= — deine Telegram-ID
ALLOWED_USERS= — IDs weiterer Benutzer (kommasepariert)
GEMINI_API_KEY= — API-Schlüssel von Google Gemini
OPENAI_API_KEY= — API-Schlüssel von OpenAI (optional)
```

### Schritt 8. Bot starten

```bash
python3 main.py
```

Bei Erfolg erscheint: `🦾 MemPalace запущен.`

---

## 🎮 Benutzung

Nach dem Start zeigt der Bot Buttons:

| Button | Funktion |
|--------|----------|
| 🆕 Neuer Dialog | Neues KI-Gespräch starten |
| 📂 Chat-Liste | Alle Dialoge anzeigen |
| ⚙️ Einstellungen | KI-Modell wählen, Sprachmodus |
| 🔍 Flügel-Suche | In Notizen nach Thema suchen |
| 🔄 Synchronisation | Dialog in MemPalace speichern |
| 📹 Video herunterladen | YouTube-Video (480/720p) |
| 🎵 MP3 herunterladen | YouTube-Audio + Transkription |

### 🤖 KI-Kommunikation

Einfach Nachricht schreiben — der Bot antwortet per KI (Gemini / Ollama / OpenAI).

**Spezialbefehle:**

| Symbol | Aktion |
|--------|--------|
| `!` text | Schnellnotiz in `my_notes` speichern |
| `!!` | Erkenntnis aus letzter KI-Antwort extrahieren |
| `???` | Letzte Antwort als Recherche speichern |
| `/search text` | In MemPalace suchen |
| `/search --wing träume text` | In einem bestimmten Flügel suchen |

### 📄 PDF-Verarbeitung

Einfach PDF senden — der Bot:
1. Extrahiert Text (mit OCR auf Deutsch, Russisch, Englisch)
2. Erkennt Dokumenttyp (Medizin / Finanzen / Persönlich)
3. Erstellt eine genaue Analyse mit allen Zahlen, Daten, Begriffen
4. Speichert das Original im Archiv

**Befehle:** `/pdfs`, `/compare`

### 🎤 Sprachnachrichten

Sprachnachricht senden — der Bot:
1. Erkennt Sprache via Whisper (lokal auf deinem Mac)
2. Antwortet per Text oder Sprache (einstellbar in ⚙️)

### 📸 Fotoanalyse

Foto senden — der Bot analysiert es mit multimodaler KI.

---

## 📋 Vollständiger Funktionsumfang

### 🏰 Wissenspalast (Palace)

**Navigation:**
- `🕸️ Flügel` — Hauptbereiche anzeigen (Projekte, Personen, Themen)
- `🪪 Räume` — Unterbereiche eines Flügels → **klickbare Räume** → Eintragsliste
- `🏛️ Taxonomie` — vollständiger Baum: Flügel → Raum → Anzahl Einträge
- `📊 Graph` — Verflechtungsstatistik, Tunnel-Anzahl

**Einträge in Räumen:**
- `📄 Eintrag öffnen` — Volltext mit Paginierung (>3500 Zeichen)
- `🔗 Verbindungen` — zeigt per Tunnel verbundene Räume
- `📡 Mit Tunneln lesen` — Einträge aus aktuellem + allen verbundenen Räumen
- `🤖 Artikel` — KI erstellt einen zusammenhängenden Artikel aus allen Einträgen

**Tunnel (Verbindungen zwischen Räumen verschiedener Flügel):**
- `📋 Liste` — alle Tunnel, **klickbar** für Detailansicht
- `🔍 Zwischen Flügeln` — gemeinsame Räume zwischen zwei Flügeln finden
- `➡️ Folgen` — von einem Raum ausgehend verbundene Einträge anzeigen
- `➕ Erstellen` — 4-Schritte-Assistent zur Tunnel-Erstellung
- `🗑️ Löschen` — Tunnel aus der Detailansicht entfernen
- `🤖 Tunnel-Analyse` — KI analysiert alle Tunnel: starke/unerwartete Verbindungen
- `🔀 Traversieren` — Graph von einem Raum aus (N Schritte) erkunden

**Tunnel-Detailansicht:**
- `📖 Flügel/Raum` — Einträge einer Tunnel-Seite öffnen
- `📡 Beide lesen` — Einträge aus beiden Räumen gleichzeitig anzeigen
- `🗑️ Löschen` — Tunnel mit Bestätigung entfernen

**AI Context Enrichment (automatisch):**
Bei der Antwort durchläuft die KI automatisch die Tunnel von gefundenen Quellen und fügt Einträge aus benachbarten Räumen hinzu. Ergebnis wird markiert als `[Verbindung: Flügel/Raum → verbundener_Flügel/verbundener_Raum]`.

**Wissensgraph (KG):**
- `📊 Statistiken` — Entitäten, Fakten, Verbindungstypen
- `🔍 Entität suchen` — alle Fakten mit Paginierung
- `➕ Fakt hinzufügen` — 3-Schritte-Assistent (Subjekt → Prädikat → Objekt)

**Wartung:**
- `🔁 Index neu aufbauen`
- `🗜️ DB komprimieren`
- `📦 Text komprimieren`
- `🌙 In Kontext laden`

---

### 📝 Persönliche Notizen

**«📝 Persönliche Notiz»** — schnelle Gedankennotiz:
1. Text oder Sprachnachricht senden
2. KI formatiert (Zeichensetzung, Absätze, ohne Interpretation)
3. KI klassifiziert — schlägt Flügel und Raum vor
4. Bestätigen oder manuell auswählen
5. Speichern + Kopie in `persönliche_Gedanken/inbox`

**«📖 Persönliche Gedanken»** — verwalten:
- Liste der Einträge aus `persönliche_Gedanken/inbox`
- Vorschau → Volltext (>4000 Zeichen aufgeteilt)
- `💾 In Palast` — in anderen Flügel/Raum kopieren
- `💬 Zitat` — Ausschnitt in beliebigen Raum speichern
- `🗑️ Löschen` — mit Bestätigung, endgültig

---

### 📸 Fotos
- Automatisch in `photos/` speichern
- Fotoanalyse per KI
- `/photos` — alle Fotos verwalten

### 🎙️ Sprache
- Spracherkennung via `faster-whisper` (lokal, CPU)
- Sprachausgabe via macOS `say` + ffmpeg (OGG, 64k, Stimme Milena)
- Drei Modi: nur Text / nur Sprache / beides
- Geschwindigkeit: 100–300 wpm

### 🎬 YouTube
- `📹 Video` — 480p oder 720p via yt-dlp
- `🎵 MP3` — Audio extrahieren + Transkription + speichern

### 📄 PDF
- Textextraktion (PyMuPDF + Tesseract OCR)
- 9 Analysetypen (Medizin, Psychologie, Literatur, Programmierung, Sport u.a.)
- `/pdfs` — Archiv mit Neuanalyse
- `/compare` — zwei PDFs vergleichen
- Auto-Chunking (>25K Zeichen)

### 💬 Chats
- `🆕 Neuer Dialog`
- `📂 Chat-Liste`
- `/history` — letzte 10 Nachrichten
- `/export` — Chat als `.md` exportieren
- `~` oder `#ctx` — Zusammenfassung anzeigen/generieren
- Auto-Sync alle 5 Nachrichten

### 🧠 Langzeitgedächtnis
- Fakten aus jedem Dialog extrahieren
- Speichern in `memory_store/mem_{user_id}.json`
- Relevante Fakten in den KI-Kontext einfügen

### ⚙️ Einstellungen
- KI-Modell: Gemini Flash / Ollama / OpenAI
- Antwortmodus: Text / Sprache / beides
- Sprachgeschwindigkeit
- MCP-Zugang zum Palast

### ⏰ Erinnerungen

Schreibe «erinnere mich morgen um 15:00 an den Anruf» — der Bot解析t Zeit und Text per KI, zeigt eine Bestätigung und sendet die Erinnerung zur gewünschten Zeit.

**Beispiele:**
- «erinnere mich in 2 Stunden an das Meeting»
- «remind me tomorrow at 10:30 to buy milk»
- «erinnere übermorgen um 18:00 an Geburtstag»

**Bei unvollständigen Angaben:**
- Der Bot fragt selbst nach der fehlenden Zeit oder dem fehlenden Text
- Funktioniert auf Deutsch, Russisch und Englisch
- Erinnerungen überleben Bot-Neustarts (SQLite)
- Prüfung alle 30 Sekunden durch Hintergrundplaner

### 🎭 Reaktionen
Auf KI-Antworten reagieren:
- 👍 → `my_notes/`
- ❤️ → `insights/`
- 🤷 → `research/`

---

## ⚡ Architektur (v1.1+)

- **Event Bus** — asynchrone Ereignisverarbeitung
- **Streaming AI** — Antwort erscheint Token für Token
- **Semantic Cache** — ähnliche Fragen (≥0.82) werden gecacht
- **Circuit Breaker** — Schutz vor Kaskadenausfällen
- **Warm-start Whisper** — Modell wird einmalig geladen
- **SQLite KV Store** — persistente Sitzungen über Neustarts hinweg
- **Graceful Degradation** — 4 Betriebsstufen (FULL → EMERGENCY)
- **Quellenangabe** — KI zitiert Fundstellen mit `[1]`, `[2]`...
- **Strukturiertes Logging** — JSON-Log mit Rotation

---

## 📂 `_scripts` — Fertige Skripte

Alle Skripte starten per Doppelklick (`.command`). Keine Terminal-Eingabe nötig.

| Skript | Aktion |
|--------|--------|
| **Ollama_Start** | Ollama-Server starten |
| **start_bot** | Bot starten |
| **PalaceManager_TelegrammBot** | Vollkontrolle (Start/Stopp/Logs) |
| **KillPalaceBot** | Bot-Prozesse beenden |
| **Switch_AI** | KI-Modell wechseln |
| **setup_env** | `.env` einrichten |
| **update_memory** | MemPalace aus `my_notes` aktualisieren |
| **check_memory** | MemPalace-Status prüfen |
| **clear_memory** | MemPalace-Datenbank leeren |
| **Ask_Memory** | CLI-Dialog mit KI |
| **find_memory** | Suche in Notizen |
| **Backup_Restore** | Backup/Wiederherstellung |

---

## 🖥️ MemPalace Bot.app

Native macOS-App im Projektverzeichnis. Alle 22 Skripte in einem Fenster mit Dark Mode. Doppelklick zum Öffnen.

---

## 🧹 Fehlerbehebung

**Bot antwortet nicht:** → Prüfe Token, starte neu, nutze KillPalaceBot.

**Module not found:** → `pip install -r requirements.txt` im venv.

**PDF wird nicht verarbeitet:** → `brew install tesseract tesseract-lang`.

**YouTube lädt nicht:** → `brew install ffmpeg`.

**Palace/MCP nicht erreichbar:** → Bot startet automatisch in 🟡/🟠 Modus, erholt sich nach 30–60 Sekunden.

**Wie aktualisieren:** → `git pull && pip install -r requirements.txt`.

## 📄 Lizenz

MIT License — frei verwendbar, veränderbar, teilbar mit Namensnennung.
