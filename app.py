import os
import threading
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from discogs_api import (
    get_collection,
    get_all_play_counts,
    update_play_count,
    set_current_record,
    get_current_record,
    clear_now_playing,
    get_last_played,
    search_releases,
    add_to_collection,
    get_plays_field_id,
    sync_play_counts_from_discogs,
    update_discogs_play_count,
    get_release_instance,
    get_release_tracks,
    cache_release,
    get_album_glow,
)  # Import from your new file
from lyrics_api import get_lyrics  # Import lyrics function
from led_controller import set_ambient, show_spots
from shelf import glow_for_record, placement, spot_for
from admin import admin

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.register_blueprint(admin)
# Changes on every deploy so browsers fetch the new stylesheet instead of a cached one
app.jinja_env.globals["css_version"] = int(os.path.getmtime(os.path.join(app.static_folder, "style.css")))

DISCOGS_USERNAME = os.getenv("DISCOGS_USERNAME")
DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")

# Validate that credentials are set
if not DISCOGS_USERNAME or not DISCOGS_TOKEN:
    raise ValueError("DISCOGS_USERNAME and DISCOGS_TOKEN must be set in .env file")

def format_record(r, play_counts, current_record_id):
    """Turn a Discogs collection item into the record shape the page uses"""
    basic = r.get("basic_information", {})
    release_id = basic.get("id")
    genres = basic.get("genres", []) or []
    styles = basic.get("styles", []) or []
    # Combine genres and styles
    all_genre_tags = genres + styles
    
    # Get format information
    try:
        formats = basic.get("formats", [])
        format_name = formats[0].get("name", "Unknown") if formats and len(formats) > 0 else "Unknown"
        format_descriptions = formats[0].get("descriptions", []) if formats and len(formats) > 0 and isinstance(formats[0].get("descriptions"), list) else []
        format_desc = ", ".join(format_descriptions) if format_descriptions else ""
    except (IndexError, AttributeError, TypeError):
        format_name = "Unknown"
        format_desc = ""
    
    # Get labels
    try:
        labels = basic.get("labels", [])
        label_names = [label.get("name", "") for label in labels if label and isinstance(label, dict) and label.get("name")]
    except (TypeError, AttributeError):
        label_names = []
    
    # Get master year (if available)
    master_id = basic.get("master_id", None)
    
    return {
        "title": basic.get("title", ""),
        "artist": ", ".join([artist["name"] for artist in basic.get("artists", [])]),
        "year": basic.get("year", "Unknown"),
        "thumb": basic.get("thumb", ""),
        "cover_image": basic.get("cover_image", ""),
        "id": release_id,
        "tracks": r.get("tracks", []),  # Now includes tracks!
        "genres": all_genre_tags,  # Add genres to the collection
        "play_count": play_counts.get(release_id, 0),  # Add play count
        "format": format_name,
        "format_desc": format_desc,
        "labels": label_names,
        "styles": styles,
        "master_id": master_id,
        "is_current": bool(current_record_id and release_id == current_record_id),
    }

@app.route("/", methods=["GET"])
def index():
    sort_by = request.args.get("sort", "artist")
    search_query = request.args.get("search", "").lower()

    # Use the new cached version
    releases = get_collection(DISCOGS_USERNAME, DISCOGS_TOKEN)
    
    # Pull play counts stored in Discogs into the local cache
    plays_field_id = get_plays_field_id(DISCOGS_USERNAME, DISCOGS_TOKEN)
    if plays_field_id:
        sync_play_counts_from_discogs(releases, plays_field_id)
    
    # Get all play counts
    play_counts = get_all_play_counts()

    # Get the record that is currently spinning
    current_record_id = get_current_record()
    
    # Transform to your existing format
    collection = []
    all_genres = set()  # Collect all unique genres
    
    for r in releases:
        record = format_record(r, play_counts, current_record_id)
        all_genres.update(record["genres"])
        collection.append(record)
    
    # Sort genres alphabetically for the filter dropdown
    sorted_genres = sorted([g for g in all_genres if g])  # Filter out empty strings

    # Filter by search
    if search_query:
        collection = [item for item in collection if search_query in item["title"].lower() or search_query in item["artist"].lower()]

    # Sort
    if sort_by == "artist":
        collection.sort(key=lambda x: x["artist"])
    elif sort_by == "year":
        collection.sort(key=lambda x: x["year"] if isinstance(x["year"], int) else 0)
    elif sort_by == "play_count":
        collection.sort(key=lambda x: x.get("play_count", 0), reverse=True)  # Highest play count first

    return render_template("index.html", collection=collection, genres=sorted_genres)

@app.route("/api/play_count", methods=["POST"])
def update_play_count_api():
    """API endpoint to update play count"""
    data = request.get_json()
    release_id = data.get("release_id")
    delta = data.get("delta", 1)  # +1 to increment, -1 to decrement
    
    if not release_id:
        return jsonify({"error": "release_id is required"}), 400
    
    plays_field_id = get_plays_field_id(DISCOGS_USERNAME, DISCOGS_TOKEN)
    if not plays_field_id:
        new_count = update_play_count(release_id, delta)
    else:
        try:
            new_count = update_discogs_play_count(DISCOGS_USERNAME, DISCOGS_TOKEN, release_id, delta, plays_field_id)
        except (requests.RequestException, ValueError) as e:
            return jsonify({"error": f"Could not update play count in Discogs: {e}"}), 502

    # If this was a positive spin, mark as current record (both last played + now playing)
    if delta and delta > 0:
        set_current_record(release_id)
        if get_album_glow():
            threading.Thread(target=glow_for_record, args=(release_id,), daemon=True).start()

    current_id = get_current_record()

    return jsonify({"play_count": new_count, "current_record_id": current_id})


@app.route("/api/search", methods=["GET"])
def search_api():
    """Search Discogs for releases to add"""
    query = request.args.get("q", "").strip()
    vinyl_only = request.args.get("vinyl_only", "1") == "1"

    if not query:
        return jsonify({"error": "q is required"}), 400

    try:
        results = search_releases(query, DISCOGS_TOKEN, vinyl_only)
    except requests.RequestException as e:
        return jsonify({"error": f"Discogs search failed: {e}"}), 502

    return jsonify({"results": results})


@app.route("/api/collection", methods=["POST"])
def add_to_collection_api():
    """Add a release to the Discogs collection"""
    data = request.get_json()
    release_id = data.get("release_id")

    if not release_id:
        return jsonify({"error": "release_id is required"}), 400

    try:
        add_to_collection(DISCOGS_USERNAME, DISCOGS_TOKEN, int(release_id))
    except requests.RequestException as e:
        return jsonify({"error": f"Could not add to Discogs: {e}"}), 502

    # Send the new record back so the page can show it without reloading
    try:
        item = get_release_instance(DISCOGS_USERNAME, DISCOGS_TOKEN, int(release_id))
    except requests.RequestException:
        item = None
    if not item:
        return jsonify({"added": release_id, "record": None}), 201

    item["tracks"] = get_release_tracks(int(release_id), DISCOGS_TOKEN)
    cache_release(int(release_id), item.get("basic_information", {}), item["tracks"])
    record = format_record(item, get_all_play_counts(), get_current_record())

    # Show where the new record goes: tell the page, and spin the shelf lights onto the spot
    try:
        shelf = placement(int(release_id))
    except requests.RequestException as e:
        print(f"LED: couldn't work out the shelf spot for new record {release_id}: {e}")
        shelf = None
    if shelf:
        shelf["lit"] = show_spots(find=shelf["led"], spin=True)
    return jsonify({"added": release_id, "record": record, "shelf": shelf}), 201


@app.route("/api/now_playing/clear", methods=["POST"])
def clear_now_playing_api():
    """
    Explicitly clear the 'now playing' state (e.g., record finished and put away).
    Any album glow goes off and the shelf lights up where the record goes back.
    """
    was_playing = get_current_record()
    clear_now_playing()
    if get_album_glow():  # With the glow switched off, any light on is one set by hand in admin, so leave it
        set_ambient(None)
    if was_playing:
        try:
            led = spot_for(was_playing)
            if led is not None:
                show_spots(put_away=led)
        except requests.RequestException as e:
            print(f"LED: couldn't look up shelf spot for {was_playing}: {e}")
    last_played_id = get_last_played()
    return jsonify({"current_record_id": None, "last_played_id": last_played_id})


@app.route("/api/leds/locate", methods=["POST"])
def locate_record():
    """Light a record's spot and the last played record's spot in orange. {"spin": true} sweeps onto it first (Random).
    Public: anyone at the shelf can use Find."""
    data = request.get_json(silent=True) or {}
    try:
        release_id = int(data["release_id"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "release_id must be an integer"}), 400

    last_played_id = get_last_played()
    try:
        led = spot_for(release_id)
        put_away_led = spot_for(last_played_id) if last_played_id and last_played_id != release_id else None
    except requests.RequestException as e:
        return jsonify({"error": f"Couldn't load the collection: {e}"}), 502
    if led is None:
        return jsonify({"error": "That record isn't in the collection"}), 404
    if not show_spots(find=led, put_away=put_away_led, spin=data.get("spin") is True):
        return jsonify({"error": "The shelf lights aren't connected"}), 503
    return jsonify({"led": led, "put_away_id": last_played_id if put_away_led is not None else None})


@app.route("/api/last_played", methods=["GET"])
def last_played_api():
    """The most recently played record, kept after it's cleared."""
    last_played_id = get_last_played()
    if last_played_id is None:
        return jsonify({"last_played_id": None})
    return jsonify({"last_played_id": last_played_id})

@app.route("/api/lyrics", methods=["GET"])
def get_lyrics_api():
    """API endpoint to get lyrics for a track"""
    artist = request.args.get("artist")
    track_name = request.args.get("track")
    
    if not artist or not track_name:
        return jsonify({"error": "artist and track parameters are required"}), 400
    
    lyrics = get_lyrics(artist, track_name)
    
    if lyrics is None:
        return jsonify({"error": "Lyrics not found"}), 404
    
    if lyrics == "":
        return jsonify({"error": "Lyrics not available"}), 404
    
    return jsonify({"lyrics": lyrics})

if __name__ == "__main__":
    # Allow port to be configured via environment variable (default to 8080 for non-root)
    port = int(os.getenv("FLASK_PORT", 8080))
    debug = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    # Localhost only: nginx is the public entry point, so nobody can bypass it on 8080
    app.run(host="127.0.0.1", port=port, debug=debug)