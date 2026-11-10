import requests
import sqlite3
import time
import json

API_BASE = "https://api.discogs.com"
DB_PATH = "vinyl_collection.db"  # Adjust path as needed
PLAYS_FIELD_NAME = "Plays"  # Custom collection field in Discogs that stores play counts

LED_SETTING_COLUMNS = {
    "album_glow": "INTEGER NOT NULL DEFAULT 0",
    "first_led": "INTEGER NOT NULL DEFAULT 0",
    "last_led": "INTEGER",
    "spot_seconds": "INTEGER NOT NULL DEFAULT 60",
    "find_color": "TEXT NOT NULL DEFAULT '#ffffff'",
    "wave_speed": "INTEGER NOT NULL DEFAULT 5",
    "range_count": "INTEGER",  # Records on the shelf when start/end were last saved, to ask again after adds/removes
}


def init_db():
    """Create tables if they don't exist"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if collection_cache table exists and has correct structure
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='collection_cache'")
        table_exists = cursor.fetchone() is not None
        
        if table_exists:
            # Verify table structure by checking columns
            cursor.execute("PRAGMA table_info(collection_cache)")
            columns = [row[1] for row in cursor.fetchall()]
            expected_columns = ['id', 'last_updated', 'collection_count', 'release_ids_hash']
            
            if not all(col in columns for col in expected_columns):
                # Table exists but structure is wrong, drop and recreate
                print("collection_cache table structure mismatch, recreating...")
                cursor.execute("DROP TABLE IF EXISTS collection_cache")
                table_exists = False
    except sqlite3.OperationalError:
        # Table doesn't exist or database error
        table_exists = False
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS releases (
            release_id INTEGER PRIMARY KEY,
            data TEXT NOT NULL,
            tracks TEXT NOT NULL,
            fetched_at INTEGER NOT NULL
        )
    """)
    
    if not table_exists:
        cursor.execute("""
            CREATE TABLE collection_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_updated INTEGER NOT NULL,
                collection_count INTEGER,
                release_ids_hash TEXT
            )
        """)
    else:
        # Table exists with correct structure, just ensure it exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collection_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_updated INTEGER NOT NULL,
                collection_count INTEGER,
                release_ids_hash TEXT
            )
        """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS play_counts (
            release_id INTEGER PRIMARY KEY,
            play_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    # Track the most recently spun record (logical "last played")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS current_record (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            release_id INTEGER,
            updated_at INTEGER NOT NULL
        )
    """)

    # Track what is currently spinning (separate from last played)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS now_playing (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            release_id INTEGER,
            updated_at INTEGER NOT NULL
        )
    """)

    # Track the most recently spun record (single-row table)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS current_record (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            release_id INTEGER,
            updated_at INTEGER NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lyrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            artist TEXT NOT NULL,
            track_name TEXT NOT NULL,
            lyrics TEXT NOT NULL,
            fetched_at INTEGER NOT NULL,
            UNIQUE(artist, track_name)
        )
    """)

    # LED spots confirmed by hand on the admin page; records between them are estimated
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shelf_anchors (
            release_id INTEGER PRIMARY KEY,
            led INTEGER NOT NULL
        )
    """)

    # LEDs from the record before to this one. Saving a spot sets these, so an add or remove only nudges neighbors.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shelf_steps (
            release_id INTEGER PRIMARY KEY,
            step REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS led_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            brightness INTEGER NOT NULL,
            album_glow INTEGER NOT NULL DEFAULT 0
        )
    """)
    # Older databases are missing the later settings. last_led NULL means the strip's last LED.
    have = [row[1] for row in cursor.execute("PRAGMA table_info(led_settings)")]
    for column, definition in LED_SETTING_COLUMNS.items():
        if column not in have:
            cursor.execute(f"ALTER TABLE led_settings ADD COLUMN {column} {definition}")

    conn.commit()
    conn.close()


def get_shelf_anchors():
    """Hand-confirmed LED spots as {release_id: led}"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT release_id, led FROM shelf_anchors").fetchall()
    conn.close()
    return dict(rows)


def set_shelf_anchor(release_id: int, led: int):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO shelf_anchors (release_id, led) VALUES (?, ?)", (release_id, led))
    conn.commit()
    conn.close()


def get_shelf_steps():
    """{release_id: LEDs from the record on its left}"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT release_id, step FROM shelf_steps").fetchall()
    conn.close()
    return dict(rows)


def save_shelf_steps(steps: dict):
    """Replace every step at once (the whole shelf is recalculated each time)."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    with conn:
        conn.execute("DELETE FROM shelf_steps")
        conn.executemany("INSERT INTO shelf_steps (release_id, step) VALUES (?, ?)", steps.items())
    conn.close()


def get_led_settings():
    """Find light and strip range settings from admin, with defaults until they're saved."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT first_led, last_led, spot_seconds, find_color, wave_speed, range_count "
                       "FROM led_settings WHERE id = 1").fetchone()
    conn.close()
    first_led, last_led, spot_seconds, find_color, wave_speed, range_count = row or (0, None, 60, "#ffffff", 5, None)
    return {"first_led": first_led, "last_led": last_led, "spot_seconds": spot_seconds, "find_color": find_color,
            "wave_speed": wave_speed, "range_count": range_count}


def save_led_settings(**values):
    for column, value in values.items():
        _save_led_setting(column, value)


def get_led_brightness():
    """Saved glow brightness as a percentage"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT brightness FROM led_settings WHERE id = 1").fetchone()
    conn.close()
    return row[0] if row else 30


def _save_led_setting(column: str, value):
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO led_settings (id, brightness) VALUES (1, 30)")
    conn.execute(f"UPDATE led_settings SET {column} = ? WHERE id = 1", (value,))
    conn.commit()
    conn.close()


def set_led_brightness(percent: int):
    _save_led_setting("brightness", percent)


def get_album_glow():
    """Whether the shelf glows in the cover color while a record plays. Off unless turned on in admin."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT album_glow FROM led_settings WHERE id = 1").fetchone()
    conn.close()
    return bool(row and row[0])


def set_album_glow(enabled: bool):
    _save_led_setting("album_glow", int(enabled))


def set_current_record(release_id: int):
    """
    Set the most recently spun record AND mark it as currently spinning.

    - current_record.release_id = last played (persists even after stopped)
    - now_playing.release_id   = currently spinning (cleared when user stops)
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT OR REPLACE INTO current_record (id, release_id, updated_at)
        VALUES (1, ?, ?)
        """,
        (release_id, int(time.time())),
    )

    cursor.execute(
        """
        INSERT OR REPLACE INTO now_playing (id, release_id, updated_at)
        VALUES (1, ?, ?)
        """,
        (release_id, int(time.time())),
    )

    conn.commit()
    conn.close()


def get_current_record():
    """
    Get the record that is currently spinning, or None.

    This reads from the now_playing table.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT release_id FROM now_playing WHERE id = 1"
    )
    row = cursor.fetchone()

    conn.close()
    return row[0] if row else None


def clear_now_playing():
    """Clear the 'currently spinning' record but keep last played."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE now_playing SET release_id = NULL, updated_at = ? WHERE id = 1",
        (int(time.time()),),
    )

    conn.commit()
    conn.close()


def get_last_played():
    """Return the last played record id (current_record), or None."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT release_id FROM current_record WHERE id = 1"
    )
    row = cursor.fetchone()

    conn.close()
    return row[0] if row else None

def get_cached_release(release_id: int):
    """Get release data from cache"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT data, tracks FROM releases WHERE release_id = ?",
        (release_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return json.loads(row[0]), json.loads(row[1])
    return None, None

def get_play_count(release_id: int):
    """Get play count for a release"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT play_count FROM play_counts WHERE release_id = ?",
        (release_id,)
    )
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else 0

def update_play_count(release_id: int, delta: int):
    """Update play count for a release (delta can be +1 or -1)"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get current count
    cursor.execute(
        "SELECT play_count FROM play_counts WHERE release_id = ?",
        (release_id,)
    )
    row = cursor.fetchone()
    current_count = row[0] if row else 0
    
    # Calculate new count (ensure it doesn't go below 0)
    new_count = max(0, current_count + delta)
    
    # Update or insert
    cursor.execute("""
        INSERT OR REPLACE INTO play_counts (release_id, play_count)
        VALUES (?, ?)
    """, (release_id, new_count))
    
    conn.commit()
    conn.close()
    return new_count

def set_play_count(release_id: int, count: int):
    """Overwrite the local play count for a release"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO play_counts (release_id, play_count)
        VALUES (?, ?)
    """, (release_id, count))
    
    conn.commit()
    conn.close()

def get_all_play_counts():
    """Get all play counts as a dictionary"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT release_id, play_count FROM play_counts")
    rows = cursor.fetchall()
    conn.close()
    
    return {release_id: play_count for release_id, play_count in rows}

def cache_release(release_id: int, data: dict, tracks: list):
    """Save release data to cache"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR REPLACE INTO releases (release_id, data, tracks, fetched_at)
        VALUES (?, ?, ?, ?)
    """, (release_id, json.dumps(data), json.dumps(tracks), int(time.time())))
    
    conn.commit()
    conn.close()

def get_collection(username: str, token: str, force_refresh: bool = False):
    """Fetch collection with smart caching - only fetches details if collection changed"""
    init_db()
    
    # Get cached collection metadata
    row = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT last_updated, collection_count, release_ids_hash FROM collection_cache WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        # Table might not exist or database is corrupted, recreate it
        print(f"Database error: {e}. Reinitializing database...")
        try:
            conn.close()
        except:
            pass
        # Force recreate the table
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS collection_cache")
        cursor.execute("""
            CREATE TABLE collection_cache (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_updated INTEGER NOT NULL,
                collection_count INTEGER,
                release_ids_hash TEXT
            )
        """)
        conn.commit()
        conn.close()
        # Retry the query
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT last_updated, collection_count, release_ids_hash FROM collection_cache WHERE id = 1")
        row = cursor.fetchone()
        conn.close()
    
    now = int(time.time())
    cached_count = row[1] if row and row[1] else None
    cached_hash = row[2] if row and row[2] else None
    
    # Always fetch collection list (lightweight, just IDs and basic info)
    print("Fetching collection list from Discogs...")
    collection = fetch_collection_from_api(username, token)
    
    # Calculate current collection hash (sorted release IDs)
    current_release_ids = sorted([
        item.get("basic_information", {}).get("id") 
        for item in collection 
        if item.get("basic_information", {}).get("id")
    ])
    current_count = len(current_release_ids)
    current_hash = str(hash(tuple(current_release_ids)))  # Hash of sorted IDs
    
    # Check if collection has changed
    collection_changed = (
        force_refresh or 
        cached_count is None or 
        cached_count != current_count or 
        cached_hash != current_hash
    )
    
    if collection_changed:
        print(f"Collection changed detected (count: {cached_count} -> {current_count})")
        print("Fetching track details for all releases...")
    else:
        print(f"Collection unchanged (count: {current_count}), using cached track data")
    
    # Get cached release IDs to identify new ones
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT release_id FROM releases")
    cached_release_ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    # Enrich with track data from cache or API
    new_releases_count = 0
    for item in collection:
        release_id = item.get("basic_information", {}).get("id")
        if not release_id:
            continue
        
        is_new_release = release_id not in cached_release_ids
        
        # Try to get from cache first
        cached_data, cached_tracks = get_cached_release(release_id)
        
        if cached_tracks:
            # Use cached tracks
            item["tracks"] = cached_tracks
        elif collection_changed and is_new_release:
            # New release and collection changed - fetch tracks
            print(f"Fetching tracks for new release: {item.get('basic_information', {}).get('title')}")
            tracks = get_release_tracks(release_id, token)
            item["tracks"] = tracks
            cache_release(release_id, item.get("basic_information", {}), tracks)
            new_releases_count += 1
            time.sleep(0.6)  # Rate limiting
        elif not collection_changed:
            # Collection unchanged - should have cache, but if not, skip API call
            # (This shouldn't happen, but handle gracefully)
            if not cached_tracks:
                print(f"Warning: No cache for {item.get('basic_information', {}).get('title')} but collection unchanged. Skipping API call.")
                item["tracks"] = []  # Empty tracks rather than fetching
        else:
            # Collection changed but release exists - should have cache, fetch if missing
            print(f"Warning: No cache for existing release {item.get('basic_information', {}).get('title')}, fetching...")
            tracks = get_release_tracks(release_id, token)
            item["tracks"] = tracks
            cache_release(release_id, item.get("basic_information", {}), tracks)
            time.sleep(0.6)
    
    # Update cache metadata
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO collection_cache (id, last_updated, collection_count, release_ids_hash)
        VALUES (1, ?, ?, ?)
    """, (now, current_count, current_hash))
    conn.commit()
    conn.close()
    
    if collection_changed:
        print(f"Collection cache updated. Fetched {new_releases_count} new release(s) from API.")
    
    return collection

def fetch_collection_from_api(username: str, token: str):
    """Fetch raw collection list from Discogs"""
    url = f"{API_BASE}/users/{username}/collection/folders/0/releases"
    headers = {"User-Agent": "VinylPi/1.0"}
    params = {"token": token, "per_page": 200, "page": 1}

    all_items = []
    while True:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        all_items.extend(data.get("releases", []))

        if "pagination" in data and data["pagination"]["page"] < data["pagination"]["pages"]:
            params["page"] += 1
        else:
            break
    
    return all_items

def get_release_tracks(release_id: int, token: str):
    """Fetch detailed release info including tracklist"""
    url = f"{API_BASE}/releases/{release_id}"
    headers = {"User-Agent": "VinylPi/1.0"}
    params = {"token": token}
    
    try:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
        data = r.json()
        
        tracklist = data.get("tracklist", [])
        return [track.get("title", "") for track in tracklist]
    except Exception as e:
        print(f"Error fetching tracks for release {release_id}: {e}")
        return []

def search_releases(query: str, token: str, vinyl_only: bool = True):
    """Search the Discogs database for releases matching a query"""
    url = f"{API_BASE}/database/search"
    headers = {"User-Agent": "VinylPi/1.0"}
    params = {"token": token, "q": query, "type": "release", "per_page": 25}
    if vinyl_only:
        params["format"] = "Vinyl"

    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()

    results = []
    for item in r.json().get("results", []):
        results.append({
            "id": item.get("id"),
            "title": item.get("title", ""),  # Discogs formats this as "Artist - Title"
            "year": item.get("year", ""),
            "country": item.get("country", ""),
            "label": (item.get("label") or [""])[0],
            "catno": item.get("catno", ""),
            "formats": ", ".join(item.get("format", []) or []),
            "thumb": item.get("thumb", ""),
        })
    return results

def add_to_collection(username: str, token: str, release_id: int, folder_id: int = 1):
    """Add a release to the user's Discogs collection (folder 1 = Uncategorized)"""
    url = f"{API_BASE}/users/{username}/collection/folders/{folder_id}/releases/{release_id}"
    headers = {
        "User-Agent": "VinylPi/1.0",
        "Authorization": f"Discogs token={token}",
    }

    r = requests.post(url, headers=headers)
    r.raise_for_status()
    return r.json()


# ---- Play counts stored in Discogs ----
#
# When a custom collection field named "Plays" exists in Discogs, it is the
# source of truth for play counts and the local play_counts table is a cache.
# Without that field, play counts are stored locally only.

_plays_field_id = None

def get_plays_field_id(username: str, token: str):
    """Return the id of the "Plays" custom collection field, or None if it doesn't exist"""
    global _plays_field_id
    if _plays_field_id is not None:
        return _plays_field_id

    url = f"{API_BASE}/users/{username}/collection/fields"
    headers = {"User-Agent": "VinylPi/1.0"}
    params = {"token": token}

    try:
        r = requests.get(url, headers=headers, params=params)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching collection fields: {e}")
        return None

    for field in r.json().get("fields", []):
        if field.get("name", "").strip().lower() == PLAYS_FIELD_NAME.lower():
            _plays_field_id = field["id"]
            break
    return _plays_field_id

def parse_plays(notes: list, field_id: int):
    """Read the play count from a collection item's notes, or None if it's unset"""
    for note in notes or []:
        if note.get("field_id") == field_id:
            try:
                return int(str(note.get("value", "")).strip())
            except ValueError:
                return None
    return None

def sync_play_counts_from_discogs(collection: list, field_id: int):
    """Update the local play count cache with the values stored in Discogs"""
    for item in collection:
        release_id = item.get("basic_information", {}).get("id")
        plays = parse_plays(item.get("notes"), field_id)
        # Unset in Discogs means not migrated yet, so keep the local value
        if release_id and plays is not None:
            set_play_count(release_id, plays)

def get_release_instance(username: str, token: str, release_id: int):
    """Get the first collection instance of a release (a release can be owned more than once)"""
    url = f"{API_BASE}/users/{username}/collection/releases/{release_id}"
    headers = {"User-Agent": "VinylPi/1.0"}
    params = {"token": token}

    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    releases = r.json().get("releases", [])
    return releases[0] if releases else None

def set_discogs_plays(username: str, token: str, instance: dict, field_id: int, count: int):
    """Write a play count to the "Plays" field of a collection instance"""
    url = (f"{API_BASE}/users/{username}/collection/folders/{instance['folder_id']}"
           f"/releases/{instance['id']}/instances/{instance['instance_id']}/fields/{field_id}")
    headers = {
        "User-Agent": "VinylPi/1.0",
        "Authorization": f"Discogs token={token}",
    }

    r = requests.post(url, headers=headers, json={"value": str(count)})
    r.raise_for_status()

def update_discogs_play_count(username: str, token: str, release_id: int, delta: int, field_id: int):
    """Update a play count in Discogs, reading the current value first so other devices' plays aren't lost"""
    instance = get_release_instance(username, token, release_id)
    if not instance:
        raise ValueError(f"Release {release_id} is not in the collection")

    current = parse_plays(instance.get("notes"), field_id)
    if current is None:
        current = get_play_count(release_id)  # Not migrated yet, start from the local count

    new_count = max(0, current + delta)
    set_discogs_plays(username, token, instance, field_id, new_count)
    set_play_count(release_id, new_count)
    return new_count


# ---- Admin helpers ----

def get_collection_folders(username: str, token: str):
    """Map folder id -> folder name"""
    url = f"{API_BASE}/users/{username}/collection/folders"
    r = requests.get(url, headers={"User-Agent": "VinylPi/1.0"}, params={"token": token})
    r.raise_for_status()
    return {f["id"]: f["name"] for f in r.json().get("folders", [])}


def get_collection_value(username: str, token: str):
    """Discogs' min/median/max estimate for the whole collection (formatted strings like "$1,234.00")"""
    url = f"{API_BASE}/users/{username}/collection/value"
    headers = {"User-Agent": "VinylPi/1.0", "Authorization": f"Discogs token={token}"}
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()


def get_marketplace_stats(release_id: int, token: str, currency: str = "USD"):
    """Lowest current listing price and number for sale (the API has no per-release min/median/max)"""
    url = f"{API_BASE}/marketplace/stats/{release_id}"
    headers = {"User-Agent": "VinylPi/1.0", "Authorization": f"Discogs token={token}"}
    r = requests.get(url, headers=headers, params={"curr_abbr": currency})
    r.raise_for_status()
    return r.json()


def delete_collection_instance(username: str, token: str, folder_id: int, release_id: int, instance_id: int):
    """Remove one copy of a release from the Discogs collection"""
    url = (f"{API_BASE}/users/{username}/collection/folders/{folder_id}"
           f"/releases/{release_id}/instances/{instance_id}")
    headers = {"User-Agent": "VinylPi/1.0", "Authorization": f"Discogs token={token}"}
    r = requests.delete(url, headers=headers)
    r.raise_for_status()


def forget_release(release_id: int):
    """Drop a release's cached details and shelf spot so a re-add starts fresh"""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM releases WHERE release_id = ?", (release_id,))
    conn.execute("DELETE FROM shelf_anchors WHERE release_id = ?", (release_id,))
    conn.execute("DELETE FROM shelf_steps WHERE release_id = ?", (release_id,))
    conn.commit()
    conn.close()
