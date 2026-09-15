# Handoff Notes — Spotify ⇄ YT Music Sync

Context for picking this project back up (written for any fresh developer or reviewer).

## What this is

A high-precision, bidirectional playlist synchronization and migration tool between Spotify and YouTube Music.
Built for a portfolio/resume project, balancing architectural elegance with real-world API cost and gating constraints.

## Architecture & Flows

### 1. Forward Sync: Spotify CSV → YouTube Music
* **100% Free Tier, Zero Spotify Developer Keys Required.**
* In February 2026, Spotify gated the Web API developer app creation behind Spotify Premium. Rather than forcing users into paid subscriptions or dealing with a 5-test-user allowlist, forward sync consumes client-side CSV exports from [Exportify](https://exportify.net).
* High-precision matching engine with 11-factor candidate scoring: Levenshtein distance, duration difference penalties, live/acoustic/remix bias matching, album verification, karaoke/tribute disqualification, and channel normalization.
* Idempotent synchronization with multi-layer deduplication (intra-CSV, in-memory, and cross-run remote YouTube playlist diffing).

### 2. Reverse Sync: YouTube Music → Spotify URI CSV
* Inverted Preprocessor extracts canonical song titles, strips YouTube noise (`[Official Video]`, `HD`, etc.), resolves multi-artist delimiters (` - `, ` -- `, ` : `, ` | `), and handles Topic/VEVO channels.
* BYOK (Bring Your Own Key) Spotify Catalog Search using the **Client Credentials Flow** (machine-to-machine, no user OAuth redirects or private account access). Bypasses Spotify's 5-user allowlist cap.
* Outputs standardized CSVs populated with verified `spotify:track:...` URIs and confidence scores for 1-click round-trip import via tools like SpotMyBackup, Spotlistr, or Playlist-Backup.
* **Graceful Fallback:** Users without Spotify developer credentials can also export a clean Raw YouTube tracklist CSV.

## Stack

- **Backend:** FastAPI + SQLite (`backend/app.db`), Python 3.10+
- **Frontend:** Vanilla JS/HTML5/CSS3, responsive UI with mobile viewport support, dark theme, zero framework dependencies
- **Security:** Localhost-only guard (`127.0.0.1`, `::1`) on credential-saving endpoints to prevent unauthorized network writes
- **Test Suite:** 64 automated tests covering API endpoints, CSV parsing, SQLite schema migrations, matching heuristics, reverse sync preprocessors, and synchronization idempotency

## File Map

```
backend/
  main.py             FastAPI application routes, security guards, reverse sync API
  db.py               SQLite schema + atomic operations (tokens, playlist_links, tracks, sync_runs)
  matching.py         11-factor fuzzy scoring and candidate ranking engine
  sync.py             Forward sync orchestrator with batching and cross-run deduplication
  ytmusic_auth.py     Google OAuth 2.0 Device Flow helper + YouTubeSyncClient
  csv_import.py       Robust Exportify CSV parser (handles alias headers, quoted commas)
  spotify_client.py   Spotify Client Credentials token manager + catalog search client
  yt_to_spotify.py    Inverted preprocessor & YouTube -> Spotify URI resolver
  setup_wizard.py     Interactive CLI setup wizard with non-clobbering .env merge
  verify_setup.py     Environment verification utility

frontend/
  index.html          Responsive single-page UI (viewport meta, accessibility)
  app.js              Client controller (auth polling timeout, error handling, clipboard fallback)
  style.css           Dark theme design system with animations and progress bars

tests/
  conftest.py         Pytest fixtures (isolated SQLite, FastAPI TestClient, mocked env)
  test_api.py         HTTP API endpoint tests & security guard validation
  test_csv_import.py  CSV parser unit tests with malformed/alternate headers
  test_db.py          Database schema and CRUD operations tests
  test_matching.py    Fuzzy matching scoring and edge-case unit tests
  test_reverse_sync.py Reverse sync preprocessor and candidate scoring tests
  test_sync.py        End-to-end forward sync orchestration tests
```

## Running the Project

```bash
# Automated launcher (Linux/macOS):
chmod +x run.sh && ./run.sh

# Windows:
run.bat

# Docker:
docker compose up -d

# Run Tests:
./venv/bin/pytest tests/ -v
```
