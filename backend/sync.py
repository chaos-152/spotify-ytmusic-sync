"""
Core one-way sync: imported Spotify CSV -> YouTube Music playlist.

Strategy for v1 (simple, no dedup against existing YT playlist contents yet):
  1. Ensure a YT Music playlist exists for this link (create on first run).
  2. Read tracks that were parsed out of the last CSV import for this link.
  3. Search + add each one to the YT Music playlist, skipping duplicates
     ytmusicapi already knows about (duplicates=False handles same-run dupes;
     cross-run dedup is a good v2 addition -- see README).
"""
from . import db
from . import ytmusic_auth


def run_sync(link_id: int) -> int:
    link = db.get_link(link_id)
    if not link:
        raise ValueError(f"No playlist link with id {link_id}")

    run_id = db.start_run(link_id)

    try:
        tracks = db.get_tracks(link_id)
        if not tracks:
            raise ValueError("No tracks stored for this playlist -- re-import the CSV")

        ytmusic_playlist_id = link["ytmusic_playlist_id"]
        if not ytmusic_playlist_id:
            ytmusic_playlist_id = ytmusic_auth.create_playlist(
                title=f"{link['source_name']} (from Spotify)",
                description="Synced automatically from an imported Spotify playlist.",
            )
            db.set_ytmusic_playlist_id(link_id, ytmusic_playlist_id)


        result = ytmusic_auth.search_and_add(ytmusic_playlist_id, tracks, link["user_id"])

        db.finish_run(run_id, "done", result["added"], result["skipped"], result["errors"])
    except Exception as e:
        db.finish_run(run_id, "error", 0, 0, [{"track": "*", "reason": str(e)}])
        raise

    return run_id
