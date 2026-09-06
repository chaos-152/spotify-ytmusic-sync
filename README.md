# 🎵 Spotify → YouTube Music Playlist Sync

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/Tests-39%20Passing-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()

A lightweight, reliable, one-way playlist synchronization tool that mirrors your Spotify playlists directly into YouTube Music. Built with **FastAPI**, **SQLite**, and vanilla JS.

---

## 💡 Why This Exists (Product Context)

As of **February 2026**, Spotify gated its Web API developer mode behind an active Spotify Premium subscription. To keep this tool 100% accessible to free users without API paywalls or complex developer verification, playlist metadata is imported via client-side CSV exports (using open tools like [Exportify](https://exportify.net)), and synced seamlessly into YouTube Music via the **Google Cloud YouTube Data API v3** using a device-code OAuth flow.

---

## ✨ Features

- **🚀 Zero-Friction Setup:** Device-code OAuth login — click connect, enter the code on Google, and you're authenticated. No redirect URIs or complex local callback servers.
- **🧠 Smart Track Matching Engine:**
  - Normalized string similarity matching (via SequenceMatcher).
  - Version penalty heuristics (avoids accidental live, acoustic, remix, or instrumental matches).
  - Duration tolerance validation ($\le 15$s buffer) and album bonus scoring.
  - Strict confidence thresholding to prevent false-positive adds.
- **🔄 Cross-Run Deduplication:**
  - Queries existing playlist contents before inserting.
  - Automatically skips tracks already synced in previous runs or duplicated in the CSV.
  - Handles batching in chunks of 50 to avoid oversized payloads.
- **🎨 Intuitive Drag-and-Drop Web UI:**
  - Drag-and-drop or browse CSV file picker.
  - Auto-infers playlist title from the filename.
  - Live progress polling and real-time error reporting.
- **🧪 Comprehensive Test Suite:** 39 unit and integration tests covering CSV parsing, database schema migrations, matching heuristics, sync execution, and API endpoints.

---

## 🛠️ Architecture & Tech Stack

```
┌────────────────────────────────────────────────────────┐
│                   Web Browser UI                       │
│    (Vanilla JS, Drag-and-Drop CSV, Polling Status)     │
└───────────────────────────┬────────────────────────────┘
                            │ REST API
┌───────────────────────────▼────────────────────────────┐
│                    FastAPI Backend                     │
├────────────────────────────────────────────────────────┤
│  • CSV Parser (Alias Normalization, Duration Parsing)  │
│  • Smart Matching Engine (Fuzzy + Version Penalty)     │
│  • YouTube Sync Client (YouTube Data API v3)           │
│  • SQLite Storage (Tracks, Tokens, Playlist Links)     │
└────────────────────────────────────────────────────────┘
```

- **Backend:** FastAPI, Uvicorn, Requests, ytmusicapi (for music search).
- **Database:** SQLite (lightweight, zero-config local persistence).
- **Frontend:** Semantic HTML5, CSS3, Vanilla ES6 JavaScript (zero build step).
- **Testing:** Pytest, pytest-mock.

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+
- A Google Cloud Project with the **YouTube Data API v3** enabled.

### 2. Export a Spotify Playlist
1. Visit **[Exportify](https://exportify.net)** and log in with your Spotify account.
2. Export your desired playlist as a `.csv` file.

### 3. Setup Google Cloud OAuth Credentials
1. Open the **[Google Cloud Console](https://console.cloud.google.com/)**.
2. Create or select a project and navigate to **APIs & Services $\rightarrow$ Library**.
3. Search for and enable **YouTube Data API v3**.
4. Go to **APIs & Services $\rightarrow$ OAuth consent screen**:
   - Set User Type to **External**.
   - Add your email under **Test users**.
5. Go to **Credentials $\rightarrow$ Create Credentials $\rightarrow$ OAuth client ID**:
   - Select Application type: **TVs and Limited Input devices**.
   - Note down the generated `Client ID` and `Client Secret`.

### 4. Installation & Configuration

```bash
# Clone the repository
git clone https://github.com/your-username/spotify-ytmusic-sync.git
cd spotify-ytmusic-sync

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example backend/.env
```

Edit `backend/.env` with your Google Cloud credentials:
```ini
YTMUSIC_CLIENT_ID=your_client_id.apps.googleusercontent.com
YTMUSIC_CLIENT_SECRET=your_client_secret
```

### 5. Run the Application

```bash
uvicorn backend.main:app --reload --port 8000
```

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser:
1. Click **Connect YT Music**, click the Google link, enter the code, and approve.
2. Drag & drop your Spotify CSV file.
3. Click **Sync now**!

---

## 🧪 Running Tests

```bash
pytest -v
```

All 39 automated tests will execute against an isolated temporary SQLite database and mock API fixtures:
```
tests/test_api.py ........                                [ 20%]
tests/test_csv_import.py ........                         [ 41%]
tests/test_db.py ....                                     [ 51%]
tests/test_matching.py ............                       [ 82%]
tests/test_sync.py .......                                [100%]
====================== 39 passed in 0.20s ======================
```

---

## 📊 API & Quota Considerations (PM Notes)

- **Daily Quotas:** Google provides 10,000 free quota units per day for the YouTube Data API v3. Creating a playlist costs 50 units, and adding an item costs 50 units (~200 tracks per daily quota).
- **Resumable Sync:** Thanks to cross-run deduplication, large playlists exceeding the daily limit can be resumed the following day without adding duplicate songs.
- **Non-blocking Search:** Track searches use YouTube Music's search engine directly (0 YouTube Data API quota cost), preserving 100% of API quota for playlist mutations.

---

## 📄 License

MIT License. Free to use, modify, and distribute.
