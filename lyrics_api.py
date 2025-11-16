import sqlite3
import time
import json
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse

DB_PATH = "vinyl_collection.db"

def init_lyrics_db():
    """Ensure lyrics table exists"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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

def clean_artist_name(artist: str):
    """Clean artist name by removing Discogs disambiguation like (2), (3), etc."""
    # Remove patterns like "(2)", "(3)", etc. at the end
    artist = re.sub(r'\s*\(\d+\)\s*$', '', artist).strip()
    # Also handle cases where it might be in the middle or start
    artist = re.sub(r'^\s*\(\d+\)\s*', '', artist).strip()
    return artist

def get_cached_lyrics(artist: str, track_name: str):
    """Get lyrics from cache if available"""
    init_lyrics_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clean artist name for cache lookup too
    clean_artist = clean_artist_name(artist)
    clean_track = track_name.split("(")[0].split("-")[0].strip()
    
    cursor.execute(
        "SELECT lyrics FROM lyrics WHERE artist = ? AND track_name = ?",
        (clean_artist, clean_track)
    )
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else None

def cache_lyrics(artist: str, track_name: str, lyrics: str):
    """Cache lyrics in database"""
    init_lyrics_db()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Clean artist name and track name for consistent caching
    clean_artist = clean_artist_name(artist)
    clean_track = track_name.split("(")[0].split("-")[0].strip()
    
    cursor.execute("""
        INSERT OR REPLACE INTO lyrics (artist, track_name, lyrics, fetched_at)
        VALUES (?, ?, ?, ?)
    """, (clean_artist, clean_track, lyrics, int(time.time())))
    
    conn.commit()
    conn.close()

def search_genius_song(artist: str, track_name: str):
    """Search for a song on Genius using their public API and return the song URL"""
    try:
        # Clean up artist name (remove Discogs disambiguation)
        clean_artist = clean_artist_name(artist)
        # Clean up track name (remove common suffixes like "Remastered", etc.)
        clean_track = track_name.split("(")[0].split("-")[0].strip()
        
        # Build search query - try with artist first for better matching
        query = f"{clean_artist} {clean_track}"
        print(f"Searching Genius API with query: {query}")
        
        # Use Genius public API endpoint (no authentication required)
        search_url = f"https://genius.com/api/search/multi?q={urllib.parse.quote(query)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json"
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        print(f"Genius API response status: {response.status_code}")
        
        # Debug: Print response structure to understand what we're getting
        if "response" not in data:
            print(f"Warning: No 'response' key in API data. Keys: {list(data.keys())}")
            return None
        
        if "sections" not in data["response"]:
            print(f"Warning: No 'sections' key in response. Keys: {list(data['response'].keys())}")
            return None
        
        # Parse API response - look for song results
        sections = data["response"]["sections"]
        print(f"Found {len(sections)} sections in response")
        
        for section in sections:
            section_type = section.get("type")
            print(f"Section type: {section_type}")
            
            if section_type == "song":
                hits = section.get("hits", [])
                print(f"Found {len(hits)} song hits")
                
                # Return the first matching song result
                # Since we're already in a "song" section, all hits should be songs
                for hit in hits:
                    result = hit.get("result", {})
                    result_type = result.get("type")
                    title = result.get("title", "N/A")
                    print(f"Hit result type: {result_type}, title: {title}")
                    
                    # Check if it's a song (either type is "song" or we're in song section)
                    # Also check for URL directly since we're in song section
                    song_url = result.get("url")
                    if song_url:
                        print(f"Found song URL: {song_url}")
                        return song_url
                    else:
                        # Debug: show what keys we have
                        print(f"No URL found. Result keys: {list(result.keys())}")
                        # Try alternative URL fields
                        if "path" in result:
                            path = result.get("path")
                            if path:
                                song_url = f"https://genius.com{path}"
                                print(f"Found song URL via path: {song_url}")
                                return song_url
        
        # If no song found, try searching with just track name
        if clean_artist and clean_track:
            print(f"Trying track-only search: {clean_track}")
            query_track_only = clean_track
            search_url = f"https://genius.com/api/search/multi?q={urllib.parse.quote(query_track_only)}"
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "response" in data and "sections" in data["response"]:
                    for section in data["response"]["sections"]:
                        if section.get("type") == "song":
                            hits = section.get("hits", [])
                            print(f"Found {len(hits)} song hits in track-only search")
                            for hit in hits:
                                result = hit.get("result", {})
                                # Check if artist name matches (case-insensitive)
                                primary_artist = result.get("primary_artist", {})
                                artist_name = primary_artist.get("name", "").lower() if primary_artist else ""
                                print(f"Comparing: '{clean_artist.lower()}' with '{artist_name}'")
                                
                                # Check artist match or if no artist specified, take first result
                                if not clean_artist or clean_artist.lower() in artist_name or artist_name in clean_artist.lower() or not artist_name:
                                    song_url = result.get("url")
                                    if not song_url and "path" in result:
                                        path = result.get("path")
                                        if path:
                                            song_url = f"https://genius.com{path}"
                                    
                                    if song_url:
                                        print(f"Found song via track-only search: {song_url}")
                                        return song_url
        
        print(f"No song URL found after all search attempts")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Network error searching Genius for {artist} - {track_name}: {e}")
        return None
    except Exception as e:
        print(f"Error searching Genius for {artist} - {track_name}: {e}")
        return None

def scrape_lyrics_from_genius(song_url: str):
    """Scrape lyrics from a Genius song page"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        response = requests.get(song_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Method 1: Try to find lyrics in JSON-LD structured data
        scripts = soup.find_all('script', type='application/ld+json')
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and 'lyrics' in data:
                    lyrics = data['lyrics']
                    if isinstance(lyrics, dict) and 'text' in lyrics:
                        return lyrics['text'].strip()
            except:
                pass
        
        # Method 2: Find the lyrics container by data attribute
        lyrics_div = soup.find('div', {'data-lyrics-container': 'true'})
        
        # Method 3: Try finding by class name patterns
        if not lyrics_div:
            for div in soup.find_all('div', class_=True):
                classes = ' '.join(div.get('class', []))
                if 'lyrics' in classes.lower() and 'container' in classes.lower():
                    lyrics_div = div
                    break
        
        # Method 4: Look for div with lyrics-related classes
        if not lyrics_div:
            lyrics_div = soup.find('div', class_=re.compile(r'lyrics|Lyrics', re.I))
        
        # Method 5: Find div with data attribute (case-insensitive search)
        if not lyrics_div:
            for div in soup.find_all('div'):
                attrs = div.attrs
                if 'data-lyrics-container' in attrs or 'data-lyrics' in attrs:
                    lyrics_div = div
                    break
        
        if not lyrics_div:
            return None
        
        # Remove unwanted navigation and metadata elements BEFORE extracting text
        # Remove translation/language links
        for unwanted in lyrics_div.find_all(['a'], href=True):
            href = unwanted.get('href', '').lower()
            text = unwanted.get_text(strip=True).lower()
            # Remove links to translations, contributors, languages
            if any(x in href for x in ['translation', 'contributor', '/artists/', '/albums/', 'language']) or \
               any(x in text for x in ['translation', 'contributor', 'read more', 'show', 'hide']):
                unwanted.decompose()
        
        # Remove divs that contain only navigation/metadata
        for div in lyrics_div.find_all('div'):
            div_text = div.get_text(strip=True).lower()
            # Check if this div is mostly navigation/metadata
            if any(x in div_text for x in ['translation', 'contributor', 'language', 'read more', 'show', 'hide']):
                # Check if it contains language names (common pattern)
                language_names = ['فارسی', 'bahasa', 'español', 'português', '繁體中文', 'česky', 'magyar', 
                                'français', 'türkçe', 'deutsch', 'русский', 'traditional chinese', 'russian']
                if any(lang in div_text for lang in language_names):
                    div.decompose()
                    continue
                # If it's a short div with navigation words, remove it
                if len(div_text) < 100 and any(x in div_text for x in ['translation', 'contributor']):
                    div.decompose()
        
        # Remove header-like elements that contain "Lyrics" but are navigation
        for header in lyrics_div.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            header_text = header.get_text(strip=True).lower()
            # If header contains "lyrics" but also has navigation, it might be a navigation header
            if 'lyrics' in header_text and any(x in header_text for x in ['translation', 'contributor', 'read more']):
                # Check if it's followed by mostly navigation content
                next_sibling = header.find_next_sibling()
                if next_sibling:
                    sibling_text = next_sibling.get_text(strip=True).lower()
                    if any(x in sibling_text for x in ['translation', 'contributor', 'language']):
                        header.decompose()
        
        # Extract lyrics text - focus on actual lyrics content
        lyrics_lines = []
        
        # Find all div elements that are likely lyrics lines
        for element in lyrics_div.find_all(['div', 'p', 'span']):
            element_text = element.get_text(strip=True)
            
            # Skip empty or very short elements
            if not element_text or len(element_text) < 3:
                continue
            
            # Skip elements that are clearly navigation/metadata
            element_lower = element_text.lower()
            if any(x in element_lower for x in ['translation', 'contributor', 'read more', 'show', 'hide']):
                continue
            
            # Skip if it's just language names
            language_names = ['فارسی', 'bahasa indonesia', 'español', 'português', '繁體中文', 'traditional chinese',
                            'česky', 'magyar', 'français', 'türkçe', 'deutsch', 'русский', 'russian']
            if element_lower in [lang.lower() for lang in language_names] or \
               (len(element_text) < 30 and any(lang.lower() in element_lower for lang in language_names)):
                continue
            
            # Skip if it's mostly links (navigation)
            links = element.find_all('a')
            if links and len(links) > len(element_text.split()) * 0.3:
                continue
            
            # This looks like actual lyrics content
            lyrics_lines.append(element_text)
        
        # If we didn't get much from structured elements, try getting all text but filter lines
        if len(lyrics_lines) < 10:
            # Replace <br> tags with newlines
            for br in lyrics_div.find_all('br'):
                br.replace_with('\n')
            
            all_text = lyrics_div.get_text(separator='\n', strip=True)
            
            # Filter out lines that are navigation/metadata
            filtered_lines = []
            for line in all_text.split('\n'):
                line = line.strip()
                if not line or len(line) < 2:
                    continue
                
                line_lower = line.lower()
                
                # Skip navigation/metadata lines
                if any(x in line_lower for x in ['translation', 'contributor', 'read more', 'show', 'hide']):
                    continue
                
                # Skip language names
                if line_lower in [lang.lower() for lang in language_names] or \
                   (len(line) < 30 and any(lang.lower() in line_lower for lang in language_names)):
                    continue
                
                # Skip lines that are just numbers (likely page numbers or metadata)
                if line.isdigit() and len(line) < 5:
                    continue
                
                # Skip very short lines that are likely navigation
                if len(line) < 10 and (line.isupper() or line in ['Translations', 'Contributors']):
                    continue
                
                filtered_lines.append(line)
            
            lyrics_text = '\n'.join(filtered_lines)
        else:
            lyrics_text = '\n'.join(lyrics_lines)
        
        # Clean up the lyrics
        # Remove multiple consecutive newlines
        lyrics_text = re.sub(r'\n{3,}', '\n\n', lyrics_text)
        # Remove leading/trailing whitespace
        lyrics_text = lyrics_text.strip()
        
        # Final validation - make sure we have actual lyrics content
        # Lyrics should be substantial (at least 50 characters)
        if not lyrics_text or len(lyrics_text) < 50:
            print(f"Lyrics too short after filtering: {len(lyrics_text) if lyrics_text else 0} characters")
            return None
        
        # Check if content is mostly navigation (too many unique short words suggests navigation)
        words = lyrics_text.split()
        if len(words) < 20:  # Too few words for real lyrics
            print(f"Too few words for lyrics: {len(words)}")
            return None
        
        return lyrics_text
        
    except Exception as e:
        print(f"Error scraping lyrics from {song_url}: {e}")
        return None

def get_lyrics(artist: str, track_name: str):
    """
    Get lyrics from cache or fetch from Genius.
    Uses Genius public API for search, then scrapes lyrics page.
    """
    # Clean up artist name (remove Discogs disambiguation)
    clean_artist = clean_artist_name(artist)
    # Clean up track name (remove common suffixes like "Remastered", etc.)
    clean_track = track_name.split("(")[0].split("-")[0].strip()
    
    print(f"Searching for lyrics: {clean_artist} - {clean_track}")
    
    # Check cache first to avoid unnecessary API calls
    cached = get_cached_lyrics(clean_artist, clean_track)
    if cached is not None:
        # Return cached lyrics (even if empty string, which means not found)
        if cached:
            print(f"Found cached lyrics for {clean_artist} - {clean_track}")
            return cached
        else:
            print(f"Found cached 'not found' for {clean_artist} - {clean_track}")
            return None
    
    try:
        # Step 1: Use Genius public API to search for the song
        # (No authentication required for search)
        song_url = search_genius_song(clean_artist, clean_track)
        
        if not song_url:
            print(f"No song URL found for {clean_artist} - {clean_track}")
            # Cache empty result to avoid repeated failed lookups
            cache_lyrics(clean_artist, clean_track, "")
            return None
        
        print(f"Found song URL: {song_url}")
        
        # Step 2: Scrape lyrics from the song page
        # (Genius API doesn't provide lyrics, only metadata, so we need to scrape)
        lyrics_text = scrape_lyrics_from_genius(song_url)
        
        if lyrics_text:
            print(f"Successfully scraped lyrics for {clean_artist} - {clean_track}")
            # Cache the lyrics for future use
            cache_lyrics(clean_artist, clean_track, lyrics_text)
            return lyrics_text
        else:
            print(f"Failed to scrape lyrics from {song_url}")
            # Cache empty result to avoid repeated failed lookups
            cache_lyrics(clean_artist, clean_track, "")
            return None
            
    except Exception as e:
        print(f"Error fetching lyrics for {clean_artist} - {clean_track}: {e}")
        import traceback
        traceback.print_exc()
        return None

