import logging
import re
import wikipedia
import requests
import base64
from difflib import SequenceMatcher
import os
import html2text
from jinja2 import Environment, FileSystemLoader, Template
import time  # needed for delays

# Initialize html2text
h = html2text.HTML2Text()
h.ignore_links = True
h.ignore_images = True
h.ignore_emphasis = True
h.body_width = 0  # Don't wrap text

def sanitize_slug(text):
    """
    Convert text to a URL-friendly slug.
    Remove any trailing numbers in parentheses first.
    """
    # Remove numbers in parentheses at end of name
    text = re.sub(r'\s*\(\d+\)\s*$', '', text)
    
    # Convert to lowercase and replace special characters
    slug = text.lower()
    
    # Handle special character replacements
    replacements = {
        'ö': 'o',
        'ä': 'a',
        'ü': 'u',
        'ß': 'ss',
        'æ': 'ae',
        'ø': 'o',
        'å': 'a',
        'é': 'e',
        'è': 'e',
        'ê': 'e',
        'ë': 'e',
        'á': 'a',
        'à': 'a',
        'â': 'a',
        'ã': 'a',
        'ñ': 'n',
        'ó': 'o',
        'ò': 'o',
        'ô': 'o',
        'õ': 'o',
        'í': 'i',
        'ì': 'i',
        'î': 'i',
        'ï': 'i',
        'ú': 'u',
        'ù': 'u',
        'û': 'u',
        'ý': 'y',
        'ÿ': 'y',
        'ç': 'c'
    }
    
    for char, replacement in replacements.items():
        slug = slug.replace(char, replacement)
    
    # Replace spaces and special characters with hyphens
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    
    return slug

def get_wikipedia_data(target, keyword):
    """
    Retrieves the Wikipedia summary and URL of a given target.
    """
    logging.info(f"Searching Wikipedia for '{target}' with keyword '{keyword}'")
    
    def normalize_text(text):
        normalized = text.lower().replace("(album)", "").strip()
        logging.debug(f"Normalized text: '{text}' -> '{normalized}'")
        return normalized

    def check_url_match(url, search_keyword):
        normalized_url = normalize_text(url)
        normalized_keyword = normalize_text(search_keyword)
        return normalized_keyword in normalized_url

    try:
        # First try: direct search
        try:
            page = wikipedia.page(target)
            if check_url_match(page.url, keyword):
                return page.summary, page.url
        except wikipedia.exceptions.DisambiguationError as e:
            for option in e.options[:3]:
                try:
                    option_page = wikipedia.page(option)
                    if check_url_match(option_page.url, keyword):
                        return option_page.summary, option_page.url
                except:
                    continue
        except Exception as e:
            logging.debug(f"Direct search failed: {str(e)}")

        return None, None

    except Exception as e:
        logging.error(f"Wikipedia error: {str(e)}")
        return None, None

def search_apple_music(query, search_type, token):
    """
    Search Apple Music API for artist or album.
    """
    logging.info(f"Searching Apple Music for {search_type}: {query}")
    
    base_url = "https://api.music.apple.com/v1/catalog/GB/search"
    headers = {'Authorization': f'Bearer {token}'}
    params = {
        'term': query,
        'types': search_type,
        'limit': 10  # Increased limit to get more results
    }

    try:
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if search_type in data['results'] and data['results'][search_type]['data']:
                results = data['results'][search_type]['data']
                
                # Log all results for debugging
                for result in results:
                    logging.debug(f"Found result: {result['attributes'].get('name')} by {result['attributes'].get('artistName', 'Unknown')}")
                
                # Filter out tribute/cover versions
                filtered_results = [
                    r for r in results 
                    if not any(x in r['attributes'].get('name', '').lower() for x in 
                             ['tribute', 'cover', 'karaoke', 'performed by', 'in the style of'])
                ]
                
                if filtered_results:
                    # Use exact match first
                    exact_matches = [
                        r for r in filtered_results
                        if r['attributes'].get('name', '').lower() == query.lower()
                    ]
                    
                    if exact_matches:
                        best_match = exact_matches[0]
                    else:
                        # Use string similarity as fallback
                        best_match = max(
                            filtered_results,
                            key=lambda x: SequenceMatcher(
                                None,
                                query.lower(),
                                x['attributes'].get('name', '').lower()
                            ).ratio()
                        )
                    
                    logging.info(f"Selected best match: {best_match['attributes'].get('name')} by {best_match['attributes'].get('artistName', 'Unknown')}")
                    return best_match
                else:
                    logging.warning(f"No valid matches found after filtering tributes/covers")
                    return None
                    
        return None
    except Exception as e:
        logging.error(f"Apple Music API error: {str(e)}")
        return None

def get_spotify_token(client_id, client_secret):
    """
    Gets an access token for the Spotify API using client credentials authentication.
    
    Args:
        client_id (str): Spotify API client ID
        client_secret (str): Spotify API client secret
        
    Returns:
        str: The access token, or None if not obtained.
    """
    logging.info("Requesting Spotify access token")
    
    url = 'https://accounts.spotify.com/api/token'
    headers = {
        'Authorization': f'Basic {base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()}'
    }
    data = {
        'grant_type': 'client_credentials'
    }

    try:
        logging.debug(f"Making Spotify auth request to: {url}")
        response = requests.post(url, headers=headers, data=data)
        
        if response.status_code == 200:
            token = response.json()['access_token']
            logging.info("Successfully obtained Spotify access token")
            return token
        else:
            logging.error(f"Failed to get Spotify token. Status code: {response.status_code}")
            return None
            
    except Exception as e:
        logging.error(f"Error getting Spotify token: {str(e)}")
        return None

def get_spotify_id(artist, album_name, spotify_token):
    """
    Gets the Spotify ID of an album given the artist and album name.
    
    Args:
        artist (str): The name of the artist.
        album_name (str): The name of the album.
        spotify_token (str): The Spotify API token.
        
    Returns:
        str: The Spotify ID of the album, or None if not found.
    """
    if not spotify_token:
        logging.debug("No Spotify token provided, skipping Spotify lookup")
        return None

    logging.info(f"Searching Spotify for album: {artist} - {album_name}")
    
    url = 'https://api.spotify.com/v1/search'
    params = {
        'q': f'artist:{artist} album:{album_name}',
        'type': 'album',
        'limit': 1
    }
    headers = {
        'Authorization': f'Bearer {spotify_token}'
    }

    try:
        logging.debug(f"Making Spotify API request to: {url}")
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            json_response = response.json()
            if json_response.get('albums', {}).get('items'):
                spotify_id = json_response['albums']['items'][0]['id']
                logging.info(f"Found Spotify ID: {spotify_id}")
                return spotify_id
            else:
                logging.warning(f"No Spotify results found for: {artist} - {album_name}")
                return None
        else:
            logging.error(f"Spotify API error {response.status_code}: {response.text}")
            return None

    except Exception as e:
        logging.error(f"Error querying Spotify API: {str(e)}")
        return None 

def download_artist_image(url, filename):
    """
    Downloads an artist image from a URL.
    
    Args:
        url (str): The URL of the image to download
        filename (str): The path where to save the image
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Set proper headers for Discogs
        headers = {
            'User-Agent': 'DiscogsScraperApp/1.0 +https://github.com/russmckendrick/discogs-scraper',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.discogs.com/'
        }
        
        # Download the image
        logging.info(f"Downloading artist image to {filename}")
        response = requests.get(url, headers=headers, stream=True)
        response.raise_for_status()
        
        # Save the image
        with open(filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    
        logging.info(f"Successfully downloaded artist image to {filename}")
        return True
        
    except Exception as e:
        logging.error(f"Error downloading artist image from {url}: {str(e)}")
        return False

def get_best_artist_profile(artist_info):
    """
    Gets the best available artist profile text using priority:
    Apple Music -> Discogs -> Wikipedia
    """
    profile = None
    
    # Try Apple Music bio first
    if artist_info.get('apple_music_bio'):
        profile = artist_info['apple_music_bio']
    # Then try Discogs profile
    elif artist_info.get('profile'):
        profile = artist_info['profile']
    # Finally try Wikipedia
    elif artist_info.get('artist_wikipedia_summary'):
        profile = artist_info['artist_wikipedia_summary']
        
    if profile:
        # Convert BBCode to markdown
        profile = re.sub(r'\[b\](.*?)\[/b\]', r'**\1**', profile)  # Bold
        profile = re.sub(r'\[u\](.*?)\[/u\]', r'*\1*', profile)    # Italic
        profile = re.sub(r'\[i\](.*?)\[/i\]', r'*\1*', profile)    # Italic
        
        # Convert to markdown and clean up
        profile = h.handle(profile)  # Use the initialized instance
        
        # Remove multiple newlines
        profile = re.sub(r'\n\s*\n', '\n\n', profile)
        
        # Remove any remaining HTML or BBCode
        profile = re.sub(r'<[^>]+>', '', profile)
        profile = re.sub(r'\[[^\]]+\]', '', profile)
        
        # Clean up any markdown artifacts
        profile = re.sub(r'\*\s*\*', '', profile)  # Remove empty bold/italic
        profile = re.sub(r'_{2,}', '', profile)    # Remove multiple underscores
        profile = profile.strip()
        
    return profile

def sanitize_artist_name(name):
    """
    Sanitizes artist name by removing numbers in brackets etc.
    Preserves special characters in the name.
    """
    if not name:
        return ''
        
    # Remove numbers in brackets/parentheses at end of name
    name = re.sub(r'\s*[\(\[]\d+[\)\]]\s*$', '', name)
    
    # Remove Discogs ID format (name-number)
    name = re.sub(r'-\d+$', '', name)
    
    # Remove any other trailing numbers
    name = re.sub(r'\s+\d+$', '', name)
    
    return name.strip()

def extract_youtube_id(url):
    """
    Extracts YouTube video ID from various YouTube URL formats.
    
    Args:
        url (str): YouTube URL
        
    Returns:
        str: YouTube video ID or None if not found
    """
    if not url:
        return None
        
    # Common YouTube URL patterns
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/watch\?.*v=([^&\n?#]+)',
        r'youtube\.com\/shorts\/([^&\n?#]+)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
            
    return None

def format_youtube_embed(video_id):
    """
    Formats YouTube video ID into Hugo shortcode.
    
    Args:
        video_id (str): YouTube video ID
        
    Returns:
        str: Hugo shortcode for YouTube embed
    """
    if not video_id:
        return ''
    return f'{{{{< youtube {video_id} >}}}}'

def format_track_duration(duration):
    """
    Formats track duration into MM:SS format.
    
    Args:
        duration (str): Duration string
        
    Returns:
        str: Formatted duration or empty string if invalid
    """
    if not duration:
        return ''
        
    try:
        # Try to parse duration string (could be in various formats)
        if ':' in duration:
            # Already in MM:SS format
            return duration
        else:
            # Convert seconds to MM:SS
            seconds = int(duration)
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}:{remaining_seconds:02d}"
    except:
        return duration

def format_track_list(tracklist):
    """Formats track list into markdown table.
    
    Args:
        tracklist (list): List of track dictionaries
        
    Returns:
        str: Markdown formatted track list table
    """
    if not tracklist:
        return ''
        
    # Start table with headers
    table = "| Position | Title |\n"
    table += "|----------|--------|\n"
    
    # Add each track
    for track in tracklist:
        # Try position first, fall back to number
        position = track.get('position', '') or track.get('number', '')
        title = track.get('title', '')
        table += f"| {position} | {title} |\n"
        
    return table

def format_release_formats(formats):
    """
    Formats release format information into readable text.
    
    Args:
        formats (list): List of format dictionaries
        
    Returns:
        str: Formatted text describing formats
    """
    if not formats:
        return ''
        
    format_strings = []
    for fmt in formats:
        parts = []
        
        # Add quantity if present
        if fmt.get('qty'):
            parts.append(f"{fmt['qty']}×")
            
        # Add format name
        if fmt.get('name'):
            parts.append(fmt['name'])
            
        # Add text description
        if fmt.get('text'):
            parts.append(f"({fmt['text']})")
            
        # Add descriptions
        if fmt.get('descriptions'):
            parts.append(', '.join(fmt['descriptions']))
            
        format_strings.append(' '.join(parts))
        
    return ' | '.join(format_strings) 

# -----------------------------------------------------------------------------
# Artist Page Generation functions (moved from discogs_scraper.py and db_handler.py)
# -----------------------------------------------------------------------------

def tidy_text(text):
    """Simple helper to tidy text (placeholder)."""
    return text.strip() if text else ""

def escape_quotes(text):
    """
    Escapes double quotes in a given text.
    (Moved from discogs_scraper.py)
    """
    text = text.replace('"', '\\"')
    text = re.sub(r'\s\(\d+\)', '', text)  # Remove brackets and numbers inside them
    return text

def download_image(url, filename, retries=3, delay=5):
    """
    Downloads an image from the given URL.
    (Moved from discogs_scraper.py)
    """
    folder_path = Path(filename).parent
    folder_path.mkdir(parents=True, exist_ok=True)

    if os.path.exists(filename):
        logging.info(f"Image file {filename} already exists. Skipping download.")
        return

    for attempt in range(retries):
        try:
            logging.info(f"Downloading image from {url} to {filename} (Attempt {attempt + 1})")
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logging.info(f"Successfully downloaded image to {filename}")
            return
        except Exception as e:
            logging.error(f"Failed to download image from {url}, attempt {attempt + 1}: {str(e)}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                logging.error(f"Failed to download image after {retries} attempts")
                raise

def create_artist_markdown_file(artist_data, output_dir):
    """
    Creates a markdown file for an artist.
    (Moved from discogs_scraper.py)
    """
    if artist_data is None or 'name' not in artist_data:
        logging.error('Artist data is missing or does not contain the key "name". Skipping artist.')
        return

    artist_name = artist_data["name"]
    slug = sanitize_slug(artist_name)
    folder_path = Path(output_dir) / slug
    folder_path.mkdir(parents=True, exist_ok=True)

    image_filename = f"{slug}.jpg"
    image_path = folder_path / image_filename
    missing_cover_url = "https://github.com/russmckendrick/records/raw/b00f1d9fc0a67b391bde0b0fa93284c8e64d3dfe/assets/images/missing.jpg"

    # Handle artist images
    if "images" in artist_data and artist_data["images"]:
        artist_image_url = (
            artist_data["images"][0]['resource_url']
            if isinstance(artist_data["images"][0], dict)
            else artist_data["images"][0]
        )
        download_image(artist_image_url, image_path)
    else:
        download_image(missing_cover_url, image_path)

    # Check if the artist file already exists
    artist_file_path = folder_path / "_index.md"

    # Render markdown file using Jinja2 template
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('artist_template.md')

    # Get profile text using tidy_text helper
    profile = tidy_text(artist_data.get("profile", ""))
    wikipedia_summary = tidy_text(artist_data.get("artist_wikipedia_summary", ""))

    # Choose the longer text as the summary
    summary = wikipedia_summary if len(wikipedia_summary or "") > len(profile or "") else profile

    rendered_content = template.render(
        name=escape_quotes(artist_name),
        slug=slug,
        profile=summary,
        aliases=artist_data.get("aliases", []),
        members=artist_data.get("members", []),
        image=image_filename,
        artist_wikipedia_url=artist_data.get('artist_wikipedia_url', '')
    )

    with open(artist_file_path, "w") as f:
        f.write(rendered_content)
    logging.info(f"Saved artist file {artist_file_path}")

def sanitize_summary(text):
    """
    Sanitizes text for use in YAML front matter.
    (Moved from db_handler.py)
    """
    if not text:
        return ""
    text = text.replace("[a=", "")
    text = text.replace("[l=", "")
    text = text.replace("]", "")
    lines = text.split("\n")
    lines = [line.strip() for line in lines]
    text = " ".join(lines)
    text = " ".join(text.split())
    return text

def generate_artist_page(artist_info, output_dir):
    """
    Generates artist page if it doesn't exist.
    Returns True if successful or page exists, False on error.
    (Moved and converted from db_handler.py)
    """
    artist_name = sanitize_artist_name(artist_info['name'])
    artist_slug = sanitize_slug(artist_name)
    artist_dir = os.path.join(output_dir, artist_slug)
    index_file = os.path.join(artist_dir, '_index.md')
    image_path = os.path.join(artist_dir, f"{artist_slug}.jpg")
    
    try:
        os.makedirs(artist_dir, exist_ok=True)
        image_filename = None
        if artist_info.get('images'):
            logging.info(f"Attempting to download artist image from {artist_info['images'][0]}")
            if download_artist_image(artist_info['images'][0], image_path):
                image_filename = f"{artist_slug}.jpg"
                logging.info(f"Successfully downloaded artist image to {image_path}")
            else:
                logging.error(f"Failed to download artist image from {artist_info['images'][0]}")
        else:
            logging.warning(f"No images found for artist {artist_name}")
        
        with open('artist_template.md', 'r') as f:
            template = Template(f.read())
                
        profile = sanitize_summary(artist_info.get('profile', ''))
        
        content = template.render(
            title=artist_name,
            summary=profile,
            slug=artist_slug,
            image=image_filename or "",
            apple_music_artist_url=artist_info.get('apple_music_url', ''),
            wikipedia_url=artist_info.get('artist_wikipedia_url', ''),
            url=artist_info.get('url', '')
        )
        
        with open(index_file, 'w') as f:
            f.write(content)
                
        return True
            
    except Exception as e:
        logging.error(f"Error generating artist page for {artist_name}: {str(e)}")
        return False 