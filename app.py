import os
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from discogs_api import get_collection, get_all_play_counts, update_play_count  # Import from your new file

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
        
        collection.append({
            "title": basic.get("title", ""),
            "artist": ", ".join([artist["name"] for artist in basic.get("artists", [])]),
            "year": basic.get("year", "Unknown"),
            "thumb": basic.get("thumb", ""),
            "id": release_id,
            "tracks": r.get("tracks", []),  # Now includes tracks!
            "genres": all_genre_tags,  # Add genres to the collection
            "play_count": play_counts.get(release_id, 0)  # Add play count
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
    return jsonify({"play_count": new_count})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)