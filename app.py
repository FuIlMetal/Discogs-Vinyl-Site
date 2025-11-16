import os
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
)  # Import from your new file
from lyrics_api import get_lyrics  # Import lyrics function

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

DISCOGS_USERNAME = os.getenv("DISCOGS_USERNAME")
DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN")

# Validate that credentials are set
if not DISCOGS_USERNAME or not DISCOGS_TOKEN:
    raise ValueError("DISCOGS_USERNAME and DISCOGS_TOKEN must be set in .env file")

@app.route("/", methods=["GET"])
def index():
    sort_by = request.args.get("sort", "artist")
    search_query = request.args.get("search", "").lower()

    # Use the new cached version
    releases = get_collection(DISCOGS_USERNAME, DISCOGS_TOKEN)
    
    # Get all play counts
    play_counts = get_all_play_counts()

    # Get the record that is currently spinning
    current_record_id = get_current_record()
    
    # Transform to your existing format
    collection = []
    all_genres = set()  # Collect all unique genres
    
    for r in releases:
        basic = r.get("basic_information", {})
        release_id = basic.get("id")
        genres = basic.get("genres", []) or []
        styles = basic.get("styles", []) or []
        # Combine genres and styles
        all_genre_tags = genres + styles
        all_genres.update(all_genre_tags)
        
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
        
        collection.append({
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
        })
    
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
    
    new_count = update_play_count(release_id, delta)

    # If this was a positive spin, mark as current record (both last played + now playing)
    if delta and delta > 0:
        set_current_record(release_id)

    current_id = get_current_record()

    return jsonify({"play_count": new_count, "current_record_id": current_id})


@app.route("/api/now_playing/clear", methods=["POST"])
def clear_now_playing_api():
    """
    Explicitly clear the 'now playing' state (e.g., record finished and put away).
    We keep track of the last played record separately for LEDs/shelving.
    """
    clear_now_playing()
    last_played_id = get_last_played()
    return jsonify({"current_record_id": None, "last_played_id": last_played_id})


@app.route("/api/last_played", methods=["GET"])
def last_played_api():
    """Small helper endpoint for LED controller to know where the last record belongs."""
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
    app.run(host="0.0.0.0", port=80, debug=True)