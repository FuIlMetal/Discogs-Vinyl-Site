import requests
import sqlite3
import time
import json

API_BASE = "https://api.discogs.com"
DB_PATH = "vinyl_collection.db"  # Adjust path as needed

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
    
    conn.commit()
    conn.close()


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