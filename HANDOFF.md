# Handoff notes — Spotify → YT Music Sync

Context for picking this project back up (written for a fresh Claude Code
session with no prior conversation history).

## What this is

A personal tool that one-way syncs a Spotify playlist into YouTube Music.
Built for a resume project (targeting PM/APM applications), so the
decision-making behind choices matters as much as the code — see
"Why CSV, not the Spotify API" below, that's the one worth understanding
before touching auth.

## Stack

- Backend: FastAPI + plain sqlite3 (no ORM), Python 3.11+
- Frontend: vanilla JS/HTML/CSS, no build step, served as static files by FastAPI
- No test suite yet — verification so far has been manual, via FastAPI's
  `TestClient` in one-off scripts, not committed test files

## Why CSV, not the Spotify API

Originally built against Spotify's Web API with standard OAuth. In
February 2026 Spotify started requiring a Premium subscription to use the
Web API in Developer Mode (confirmed via Spotify's own Feb 2026 migration
guide and contemporaneous TechCrunch coverage) — apps also got capped at 5
test users. Rather than depend on a subscription that could lapse, the
Spotify half was ripped out and replaced with CSV import: the user exports
their playlist via exportify.net (runs client-side against their own
Spotify login, not the gated API) and uploads the CSV here.

**Practical implication:** there is no live "is the source playlist still
in sync" signal. Re-syncing means the user re-exports and re-uploads
manually. Don't try to "fix" this by re-adding Spotify OAuth without
re-litigating that tradeoff first.

## File map

```
backend/
  main.py         FastAPI routes — status, YT Music auth, CSV import, sync trigger
  db.py           sqlite3 schema + queries (tokens, playlist_links, tracks, sync_runs)
  csv_import.py   Exportify CSV parser (handles a few header-name variants)
  ytmusic_auth.py YT Music OAuth (device-code flow via ytmusicapi) + client helper
  sync.py         orchestrates: create/reuse YT playlist, search+add tracks
frontend/
  index.html, app.js, style.css   no framework, talks to the FastAPI JSON routes
README.md         setup instructions (env vars, install, run)
```

## Data flow

1. User uploads CSV via `POST /api/import-csv` (multipart: `name`, `file`)
2. `csv_import.parse_csv` extracts `{title, artist, album}` per row
3. `db.upsert_link` + `db.replace_tracks` store them, keyed by playlist name
   (re-uploading the same name wipes and replaces its tracks)
4. `POST /api/links/{id}/sync` runs as a FastAPI `BackgroundTask` →
   `sync.run_sync`: creates a YT Music playlist if this link doesn't have
   one yet, searches each track by `"{title} {artist}"`, adds the first hit
5. Frontend polls `GET /api/links/{id}/runs` every 2s while syncing

## Known gaps — the actual next-work list

Ranked roughly by value for a resume bullet vs. effort:

1. **Track matching is naive.** First search result only, no scoring
   against duration/album/explicit-version. Worth adding a scored match
   (e.g. compare duration_ms if Exportify's CSV includes it, penalize
   "live"/"remix" mismatches) — this is the single highest-leverage fix for
   sync quality.
2. **No cross-run dedup.** Re-syncing a playlist re-adds everything.
   `ytmusicapi`'s `duplicates=False` only dedups within one call. Fix:
   before adding, fetch the YT playlist's existing video IDs and diff.
3. **No scheduling/automation** for re-import — by design, see above, but
   a "watch a folder for a new CSV" mode would be a reasonable v2.
4. One-way only, single-user (`DEFAULT_USER_ID = "me"` hardcoded) — fine
   for personal use, flag if this ever needs to serve more than one person.

## Testing so far

Verified via `fastapi.testclient.TestClient` in throwaway scripts (not
committed): CSV import round-trip with a real sample Exportify-format CSV
(correct track count, correct parsed fields), and rejection of a
malformed CSV (missing title/artist columns → clean 400, not a crash).
The YT Music device-code auth flow and the actual sync-to-YT-Music path
have **not** been run against real credentials — that's untested end-to-end.
