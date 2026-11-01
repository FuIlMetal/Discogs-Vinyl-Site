"""One-time upload of local play counts to the "Plays" custom field in Discogs.

Run this on the machine with the real play counts (the Pi):
    python migrate_plays_to_discogs.py --dry-run   # show what would change
    python migrate_plays_to_discogs.py

Releases that already have a value in Discogs are left alone, so it is safe to re-run.
"""
import os
import sys
import time
from dotenv import load_dotenv
from discogs_api import (
    DB_PATH, PLAYS_FIELD_NAME, fetch_collection_from_api, get_all_play_counts,
    get_plays_field_id, parse_plays, set_discogs_plays,
)

load_dotenv()

def main():
    dry_run = "--dry-run" in sys.argv
    username = os.getenv("DISCOGS_USERNAME")
    token = os.getenv("DISCOGS_TOKEN")

    field_id = get_plays_field_id(username, token)
    if not field_id:
        print(f'No "{PLAYS_FIELD_NAME}" custom field found in Discogs. Create it under '
              "Collection > Settings > Custom fields (type: text) first.")
        sys.exit(1)

    print(f"Using database {DB_PATH}")
    local_counts = get_all_play_counts()
    collection = fetch_collection_from_api(username, token)

    uploaded = 0
    for item in collection:
        release_id = item.get("id")
        local = local_counts.get(release_id, 0)
        if local == 0 or parse_plays(item.get("notes"), field_id) is not None:
            continue

        title = item.get("basic_information", {}).get("title", release_id)
        print(f"{'Would set' if dry_run else 'Setting'} {title}: {local} plays")
        if not dry_run:
            set_discogs_plays(username, token, item, field_id, local)
            time.sleep(1.1)  # Discogs allows 60 authenticated requests per minute
        uploaded += 1

    print(f"{'Would upload' if dry_run else 'Uploaded'} {uploaded} play count(s).")

if __name__ == "__main__":
    main()
