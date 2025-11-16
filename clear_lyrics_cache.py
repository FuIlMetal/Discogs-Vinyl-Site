"""
Script to clear all cached lyrics from the database.
This will remove all existing lyrics so they can be re-fetched with the improved scraping.
"""
import sqlite3

DB_PATH = "vinyl_collection.db"

def clear_lyrics_cache():
    """Clear all lyrics from the database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Count how many entries we're deleting
    cursor.execute("SELECT COUNT(*) FROM lyrics")
    count = cursor.fetchone()[0]
    
    print(f"Found {count} cached lyrics entries")
    
    if count > 0:
        # Delete all lyrics
        cursor.execute("DELETE FROM lyrics")
        conn.commit()
        print(f"Successfully cleared {count} lyrics entries from cache")
    else:
        print("No lyrics entries found in cache")
    
    conn.close()

if __name__ == "__main__":
    import sys
    # Allow non-interactive mode with --yes flag
    if len(sys.argv) > 1 and sys.argv[1] == "--yes":
        clear_lyrics_cache()
        print("Done! All lyrics will be re-fetched with the improved scraping.")
    else:
        confirm = input("Are you sure you want to clear all cached lyrics? (yes/no): ")
        if confirm.lower() == "yes":
            clear_lyrics_cache()
            print("Done! All lyrics will be re-fetched with the improved scraping.")
        else:
            print("Cancelled. No changes made.")

