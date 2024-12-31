####################################################################################################
# Import required libraries and modules
####################################################################################################

import sys
import json
import os
import re
import requests
import discogs_client
import time
import logging
import base64
import random
import jwt
import wikipedia
from difflib import SequenceMatcher
from pathlib import Path
from urllib.request import urlretrieve
from tqdm import tqdm
from datetime import datetime, timedelta
from tenacity import retry, wait_fixed
from jinja2 import Environment, FileSystemLoader
from db_handler import DatabaseHandler
import argparse

####################################################################################################
# Variables
####################################################################################################

DB_PATH = 'collection_cache.db' # Database path for caching
OUTPUT_DIRECTORY = 'website/content/albums' # Directory to store the output files
ARTIST_DIRECTORY = "website/content/artist" # Directory to store artist information
APPLE_KEY_FILE_PATH = 'backups/apple_private_key.p8' # Path to the apple private key file
DEFAULT_DELAY = 2 # Set delay between requests
APPLE_MUSIC_STOREFRONT = "gb" # Storefront for Apple Music
SKIP_RELEASE_FILE = 'skip_releases.txt' # File to store skipped releases
LAST_PROCESSED_INDEX_FILE = "last_processed_index.txt" # File to store the last processed index

####################################################################################################
# Functions
####################################################################################################

def get_wikipedia_data(target, keyword):
    """
    Retrieves the Wikipedia summary and URL of a given target.

    This function queries the Wikipedia API for the summary and URL of the page corresponding to the provided target.
    If the target leads to a disambiguation page, if the page does not exist, or if the URL does not contain the 
    specified keyword, the function returns None for both the summary and the URL.

    Args:
        target (str): The title of the Wikipedia page to be searched for.
        keyword (str): The keyword that the URL must contain.

    Returns:
        tuple: The summary and URL of the Wikipedia page if it exists, is not a disambiguation page, and its URL 
               contains the specified keyword. Both elements of the tuple are None otherwise.
    """
    def normalize_text(text):
        """Helper function to normalize text for comparison"""
        # Remove common suffixes and prefixes
        text = text.lower()
        text = text.replace("(album)", "").strip()
        # Handle special characters
        text = text.replace("'s", "s")  # Handle possessives
        text = text.replace("'", "")    # Remove other apostrophes
        text = text.replace("%27", "")  # Handle URL-encoded apostrophes
        text = text.replace("_", "")    # Remove underscores
        text = text.replace(" ", "")    # Remove spaces
        text = text.replace("-", "")    # Remove hyphens
        text = text.replace(".", "")    # Remove periods
        return text

    def check_url_match(url, search_keyword):
        """Helper function to check if URL matches the keyword"""
        normalized_url = normalize_text(url)
        normalized_keyword = normalize_text(search_keyword)
        return normalized_keyword in normalized_url

    try:
        # First try: direct search with (album)
        try:
            page = wikipedia.page(target)
            if check_url_match(page.url, keyword):
                return page.summary, page.url
        except wikipedia.exceptions.DisambiguationError as e:
            # If we get a disambiguation error, try the first few options
            for option in e.options[:3]:
                try:
                    option_page = wikipedia.page(option)
                    if check_url_match(option_page.url, keyword):
                        return option_page.summary, option_page.url
                except:
                    continue
        except:
            pass

        # Second try: search without (album)
        clean_target = target.replace(" (album)", "")
        try:
            page = wikipedia.page(clean_target)
            if check_url_match(page.url, keyword):
                return page.summary, page.url
        except wikipedia.exceptions.DisambiguationError as e:
            # Try the first few disambiguation options
            for option in e.options[:3]:
                try:
                    option_page = wikipedia.page(option)
                    if check_url_match(option_page.url, keyword):
                        return option_page.summary, option_page.url
                except:
                    continue
        except:
            pass

        # Third try: just the album name
        try:
            page = wikipedia.page(keyword)
            if check_url_match(page.url, keyword):
                return page.summary, page.url
        except:
            pass

        # If we get here, log the failure with details at debug level
        logging.debug(f"Wikipedia match failed for '{target}':")
        logging.debug(f"  - Tried searches:")
        logging.debug(f"    1. '{target}'")
        logging.debug(f"    2. '{clean_target}'")
        logging.debug(f"    3. '{keyword}'")
        if 'page' in locals():
            logging.debug(f"  - Last found URL: {page.url}")
            logging.debug(f"  - Looking for keyword: '{keyword}'")
            logging.debug(f"  - Normalized URL: {normalize_text(page.url)}")
            logging.debug(f"  - Normalized keyword: {normalize_text(keyword)}")
        return None, None

    except wikipedia.exceptions.PageError as e:
        logging.debug(f"PageError: No page found for any of these searches:")
        logging.debug(f"  1. '{target}'")
        logging.debug(f"  2. '{clean_target}'")
        logging.debug(f"  3. '{keyword}'")
        return None, None

def generate_apple_music_token(private_key_path, key_id, team_id):
    """
    Generates a developer token for Apple Music API.

    This function generates a JWT (JSON Web Token) using the ES256 algorithm. 
    The token is required to access the Apple Music API as a developer.

    Args:
        private_key_path (str): The path to the private key (in .p8 format) 
            obtained from the Apple Developer account.
        key_id (str): The ID for the private key obtained from the Apple Developer account.
        team_id (str): The ID for the developer's team obtained from the Apple Developer account.

    Returns:
        str: A JWT token that can be used to authorize requests to the Apple Music API.
    
    Raises:
        IOError: If the file at `private_key_path` cannot be read.
        jwt.PyJWTError: If there is an error encoding the token.
    """
    with open(private_key_path, 'r') as f:
        private_key = f.read()

    headers = {
        'alg': 'ES256',
        'kid': key_id
    }

    now = datetime.now()
    exp = now + timedelta(hours=12)

    payload = {
        'iss': team_id,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp())
    }

    token = jwt.encode(payload, private_key, algorithm='ES256', headers=headers)
    return token


def get_apple_music_data(search_type, query, token):
    """
    Queries the Apple Music API for a specific data based on the search type and query.

    This function sends a GET request to the Apple Music API and retrieves the data 
    based on the search type (e.g., artists, albums) and the search query.

    Args:
        search_type (str): The type of data to be searched for. It can be 'artists' or 'albums'.
        query (str): The search term or query.
        token (str): The JWT token for authorizing the request to the Apple Music API.

    Returns:
        dict: A dictionary containing the first search result data if any data is found.
        None: If no data is found, or if the request was unsuccessful.
    
    Raises:
        requests.exceptions.RequestException: If there is a network problem like a DNS resolution failure, 
            connection timeout, or similar.
        requests.exceptions.HTTPError: If an invalid HTTP response was received.
    """
    base_url = "https://api.music.apple.com/v1/catalog/"
    store_front = APPLE_MUSIC_STOREFRONT

    headers = {
        'Authorization': f'Bearer {token}'
    }

    search_params = {
        'term': query,
        'limit': 10,
        'types': search_type
    }

    search_url = f"{base_url}{store_front}/search"
    search_response = requests.get(search_url, headers=headers, params=search_params)

    if search_response.status_code == 200:
        search_data = search_response.json()

        if search_type == 'artists' and 'artists' in search_data['results'] and search_data['results']['artists']['data']:
            artists_data = search_data['results']['artists']['data']
            logging.info(f"Search results for artists with query '{query}':")
            for artist in artists_data:
                logging.info(f"- {artist['attributes']['name']}")
            
            # Find the artist with the closest name match
            best_match = max(artists_data, key=lambda x: SequenceMatcher(None, query.lower(), x['attributes']['name'].lower()).ratio())
            return best_match

        elif search_type == 'albums' and 'albums' in search_data['results'] and search_data['results']['albums']['data']:
            albums_data = search_data['results']['albums']['data']
            logging.info(f"Search results for albums with query '{query}':")
            for album in albums_data:
                logging.info(f"- {album['attributes']['name']} by {album['attributes']['artistName']}")
            
            # Find the album with the closest name match
            best_match = max(albums_data, key=lambda x: SequenceMatcher(None, query.lower(), x['attributes']['name'].lower()).ratio())
            return best_match

        else:
            logging.error(f"No {search_type} found for query '{query}'")
            return None

    else:
        logging.error(f"Error {search_response.status_code}: Could not fetch data from Apple Music API")
        return None

@retry(wait=wait_fixed(60))  # Adjust this value as needed
def download_image(url, filename, retries=5, delay=15):
    """
    Downloads an image from Apple Music, but only tracks Discogs images for manual download.
    
    Args:
        url (str): The URL of the image to download.
        filename (str): The path and name of the file to save the image to.
        retries (int, optional): Number of retries for Apple Music downloads. Defaults to 5.
        delay (int, optional): Delay between retries in seconds. Defaults to 15.
    """
    folder_path = Path(filename).parent
    folder_path.mkdir(parents=True, exist_ok=True)

    if os.path.exists(filename):
        logging.info(f"Image file {filename} already exists. Skipping download.")
        return

    # Check if this is an Apple Music URL
    if "mzstatic.com" in url:
        for attempt in range(retries):
            try:
                logging.info(f"Downloading Apple Music image to {filename} (Attempt {attempt + 1})")
                urlretrieve(url, filename)
                break
            except Exception as e:
                logging.error(f'Unable to download Apple Music image {url}, error {e}')
                if attempt < retries - 1:
                    time.sleep(delay)
                else:
                    logging.error(f'Failed to download Apple Music image {url} after {retries} attempts')
    else:
        # For Discogs images, just track them for manual download
        if not hasattr(download_image, 'missing_images'):
            download_image.missing_images = set()
        download_image.missing_images.add((filename, url))
        logging.info(f"Added Discogs image {filename} to missing images list")

def escape_quotes(text):
    """
    Escapes double quotes in a given text.
    
    Args:
        text (str): The input text to escape double quotes in.
        
    Returns:
        str: The text with escaped double quotes.
    """
    text = text.replace('"', '\\"')
    text = re.sub(r'\s\(\d+\)', '', text)  # Remove brackets and numbers inside them
    return text

def sanitize_slug(slug):
    """
    Sanitizes a given slug for URL generation.
    
    Args:
        slug (str): The input slug to sanitize.
        
    Returns:
        str: The sanitized slug with non-ASCII characters removed, spaces replaced by hyphens, and special characters removed.
    """
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r'\s\(\d+\)', '', slug)  # Remove brackets and numbers inside them
    slug = re.sub(r'\W+', ' ', slug)
    slug = slug.strip().lower().replace(' ', '-').replace('"', '')
    return slug

def tidy_text(text):
    """
    Tidies up text by converting certain tags to markdown and removing anything that doesn't look like markdown.
    
    Args:
        text (str): The input text to tidy up.
        
    Returns:
        str: The tidied up text.
    """
    
    text = text.replace('"', '\\"') # Escape double quotes
    text = re.sub(r'\[b\](.*?)\[/b\]', r'**\1**', text)  # Convert certain tags to markdown Bold
    text = re.sub(r'\[i\](.*?)\[/i\]', r'*\1*', text)  # Convert certain tags to markdown Italic
    text = re.sub(r'\[(a=[^\]]+)\]', '', text) # Remove artist names that look like '[a...]'
    text = re.sub(r'\[.*?\]', '', text)  # Remove tags
    text = re.sub(r'\(.*?\)', '', text)  # Remove parentheses and anything inside them
    text = re.sub(r'\s{2,}', ' ', text)  # Replace multiple spaces with a single space
    text = text.strip()  # Remove leading and trailing whitespace
    
    return text

def extract_youtube_id(url):
    """
    Extracts the YouTube video ID from a given URL.

    Args:
        url (str): The URL of the YouTube video.

    Returns:
        str: The extracted YouTube video ID or None if not found.
    """
    youtube_id_match = re.search(r'(?<=v=)[^&#]+', url)
    if youtube_id_match:
        return youtube_id_match.group(0)
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
    url = 'https://api.spotify.com/v1/search'
    params = {
        'q': f'artist:{artist} album:{album_name}',
        'type': 'album',
        'limit': 1
    }
    headers = {
        'Authorization': f'Bearer {spotify_token}'
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        json_response = response.json()
        if json_response.get('albums', {}).get('items'):
            spotify_id = json_response['albums']['items'][0]['id']
            return spotify_id
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
    url = 'https://accounts.spotify.com/api/token'
    headers = {
        'Authorization': f'Basic {base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()}'
    }
    data = {
        'grant_type': 'client_credentials'
    }

    try:
        response = requests.post(url, headers=headers, data=data)
        if response.status_code == 200:
            return response.json()['access_token']
        else:
            logging.error(f"Failed to get Spotify token. Status code: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"Error getting Spotify token: {str(e)}")
        return None

def process_artist(artist_info, processed_artists):
    """
    Processes an artist's information and creates a markdown file if the artist hasn't been processed yet.

    Args:
        artist_info (dict): A dictionary containing the artist's information.
        processed_artists (set): A set of processed artist IDs to avoid processing the same artist multiple times.
    """
    if artist_info is not None:
        artist_id = artist_info["id"]
        if artist_id not in processed_artists:
            create_artist_markdown_file(artist_info)
            processed_artists.add(artist_id)


def format_notes(notes):
    """
    Formats the notes by removing newline and carriage return characters.

    Args:
        notes (str): The notes to be formatted.

    Returns:
        str: The formatted notes as a single line of text.
    """
    if notes is None:
        return ""
    return notes.replace('\n', ' ').replace('\r', ' ')

def format_tracklist(tracklist):
    """
    Formats the tracklist as a string with each track title and duration on a separate line.

    Args:
        tracklist (list): A list of dictionaries containing track information.

    Returns:
        str: The formatted tracklist as a string.
    """
    formatted_tracklist = []
    for index, track in enumerate(tracklist, start=1):
        title = track["title"]
        duration = track["duration"]
        if duration:
            formatted_tracklist.append(f'{index}. {title} ({duration})')
        else:
            formatted_tracklist.append(f'{index}. {title}')
    return "\n".join(formatted_tracklist)


def format_release_formats(release_formats):
    """
    Formats the release formats as a comma-separated string.

    Args:
        release_formats (list): A list of dictionaries containing release format information.

    Returns:
        str: The formatted release formats as a string.
    """
    formatted_formats = []
    
    for fmt in release_formats:
        format_details = [fmt['name']]
        if 'qty' in fmt and fmt['qty'] != '1':
            format_details.append(f"{fmt['qty']}×")
        
        if 'descriptions' in fmt:
            format_details.extend(fmt['descriptions'])
        
        if 'text' in fmt:
            format_details.append(f"({fmt['text']})")
        
        formatted_formats.append(' '.join(format_details))

    return ', '.join(formatted_formats)

def create_artist_markdown_file(artist_data, output_dir=ARTIST_DIRECTORY):
    if artist_data is None or 'name' not in artist_data:
        logging.error('Artist data is missing or does not contain the key "name". Skipping artist.')
        return

    artist_name = artist_data["name"]
    slug = artist_data["slug"]
    folder_path = Path(output_dir) / slug
    image_filename = f"{slug}.jpg"
    image_path = folder_path / image_filename

    missing_cover_url = "https://github.com/russmckendrick/records/raw/b00f1d9fc0a67b391bde0b0fa93284c8e64d3dfe/assets/images/missing.jpg"

    # Check for Apple Music image first
    if "attributes" in artist_data and "artwork" in artist_data["attributes"]:
        apple_music_image = artist_data["attributes"]["artwork"]
        width = min(1024, apple_music_image["width"])
        height = min(1024, apple_music_image["height"])
        apple_music_image_url = apple_music_image["url"].format(w=width, h=height)
        download_image(apple_music_image_url, image_path)
    # If no Apple Music image, check for Discogs image
    elif artist_data["images"]:
        artist_image_url = artist_data["images"][0]
        download_image(artist_image_url, image_path)
    # If no Discogs image, use missing cover URL
    else:
        download_image(missing_cover_url, image_path)

    # Check if the artist file already exists
    artist_file_path = folder_path / "_index.md"

    # Create the output directory if it doesn't exist
    folder_path.mkdir(parents=True, exist_ok=True)

    # Render markdown file using Jinja2 template
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('artist_template.md')

    if "attributes" in artist_data and "url" in artist_data["attributes"]:
        some_apple_music_artist_url = artist_data["attributes"]["url"]
    else:
        some_apple_music_artist_url = None

    # Calculate the lengths of the profile and the wikipedia summary
    profile = tidy_text(artist_data["profile"]) if artist_data["profile"] else None
    artist_wikipedia_summary = tidy_text(artist_data['artist_wikipedia_summary']) if artist_data['artist_wikipedia_summary'] else None

    profile_length = len(profile) if profile else 0
    wikipedia_summary_length = len(artist_wikipedia_summary) if artist_wikipedia_summary else 0

    # Choose the longer one as the summary
    if profile_length > wikipedia_summary_length:
        summary = profile
    else:
        summary = artist_wikipedia_summary

    rendered_content = template.render(
        name=escape_quotes(artist_name),
        slug=sanitize_slug(artist_data["slug"]),
        profile=summary,  # use the longer summary
        aliases=artist_data["aliases"],
        members=artist_data["members"],
        image=image_filename,
        apple_music_artist_url=some_apple_music_artist_url,
        artist_wikipedia_url=artist_data['artist_wikipedia_url'] if artist_data['artist_wikipedia_url'] else 'none'
    )

    # Save the rendered content to the markdown file
    with open(artist_file_path, "w") as f:
        f.write(rendered_content)
    logging.info(f"Saved artist file {artist_file_path}")

def create_markdown_file(item_data, output_dir=Path(OUTPUT_DIRECTORY)):
    """
    Creates a markdown file for the given album data and saves it in the output directory.

    Args:
        item_data (dict): The data for the album.
        output_dir (str or Path): The directory to save the markdown file in.

    Returns:
        None
    """
    artist = item_data["Artist Name"]
    album_name = item_data["Album Title"]
    release_id = str(item_data["Release ID"])
    cover_url = item_data["Album Cover URL"]
    slug = item_data["Slug"]
    folder_path = Path(output_dir) / slug

    # Create the output directory if it doesn't exist
    folder_path.mkdir(parents=True, exist_ok=True)

    # Download album cover and other images
    cover_filename = f"{slug}.jpg"
    cover_path = folder_path / cover_filename

    # Check for Apple Music cover first
    if "Apple Music attributes" in item_data and "artwork" in item_data["Apple Music attributes"]:
        apple_music_cover = item_data["Apple Music attributes"]["artwork"]
        width = min(1024, apple_music_cover["width"])
        height = min(1024, apple_music_cover["height"])
        apple_music_cover_url = apple_music_cover["url"].format(w=width, h=height)
        download_image(apple_music_cover_url, cover_path)
    elif cover_url:
        download_image(cover_url, cover_path)
    else:
        missing_cover_url = "https://github.com/russmckendrick/records/raw/b00f1d9fc0a67b391bde0b0fa93284c8e64d3dfe/assets/images/missing.jpg"
        download_image(missing_cover_url, cover_path)

    # Store all image URLs
    image_urls = []
    if item_data.get("All Images URLs"):  # This will return None if "All Images URLs" does not exist
        for i, url in enumerate(item_data["All Images URLs"]):
            image_urls.append(url)

    # Render markdown file using Jinja2 template
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('album_template.md')
    genres = item_data.get("Genre", [])
    styles = item_data.get("Style", [])
    videos = item_data["Videos"]
    wikipedia_summary = item_data["Wikipedia Summary"]
    wikipedia_url = item_data["Wikipedia URL"]
    first_video = videos[0] if videos else None
    additional_videos = [video for video in videos[1:]] if videos and len(videos) > 1 else None
    if "Apple Music attributes" in item_data and "editorialNotes" in item_data["Apple Music attributes"] and item_data["Apple Music attributes"]["editorialNotes"] and "standard" in item_data["Apple Music attributes"]["editorialNotes"]:
        some_apple_music_editorialNotes = item_data["Apple Music attributes"]["editorialNotes"]["standard"]
    else:
        some_apple_music_editorialNotes = None

    rendered_content = template.render(
        title="{artist} - {album_name}".format(artist=escape_quotes(artist), album_name=album_name),
        artist=escape_quotes(artist),
        artist_slug=sanitize_slug(f"{artist}"),
        album_name=album_name,
        date_added=datetime.strptime(item_data["Date Added"], "%Y-%m-%dT%H:%M:%S%z").strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        release_id=release_id,
        slug=slug,
        cover_filename=cover_filename,
        genres=genres,
        styles=styles,
        track_list=format_tracklist(item_data["Track List"]),
        first_video_id=extract_youtube_id(first_video["url"]) if first_video else None,
        first_video_title=sanitize_youtube_title(first_video["title"]) if first_video else None,
        additional_videos=[{**video, "title": sanitize_youtube_title(video["title"])} for video in additional_videos] if additional_videos else None,
        release_date=item_data["Release Date"],
        release_url=item_data["Release URL"],
        label=item_data["Label"],
        release_formats=format_release_formats(item_data["Release Formats"]),
        catalog_number=item_data["Catalog Number"],
        notes=format_notes(item_data["Notes"]),
        spotify=item_data["Spotify ID"],
        apple_music_album_url = item_data["Apple Music attributes"]["url"] if "Apple Music attributes" in item_data and "url" in item_data["Apple Music attributes"] else None,
        apple_music_editorialNotes = some_apple_music_editorialNotes,
        apple_music_album_release_date = item_data["Apple Music attributes"]["releaseDate"] if "Apple Music attributes" in item_data and "releaseDate" in item_data["Apple Music attributes"] else None,
        wikipedia_summary = wikipedia_summary,
        wikipedia_url = wikipedia_url,
        image_urls=image_urls,
    )

    # Save the rendered content to the markdown file
    with open(folder_path / "index.md", "w") as f:
        f.write(rendered_content)
    logging.info(f"Saved/Updated file {folder_path}.index.md")

def sanitize_youtube_title(title):
    """
    Sanitizes a YouTube video title by removing or escaping special characters.
    
    Args:
        title (str): The YouTube video title to sanitize.
        
    Returns:
        str: The sanitized title safe for use in Hugo shortcodes.
    """
    if not title:
        return title
    # Remove quotes and other potentially problematic characters
    title = title.replace('"', '').replace("'", "").replace("(", "").replace(")", "")
    # Remove any other special characters that might cause issues
    title = re.sub(r'[^\w\s-]', '', title)
    return title

def get_artist_info(artist_name, discogs_client):
    """
    Get artist information from Discogs API.
    
    Args:
        artist_name (str): Name of the artist to search for
        discogs_client: Authenticated Discogs client instance
        
    Returns:
        dict: Artist information if found, None otherwise
    """
    # Skip lookup for Various Artists compilations
    if artist_name.lower() == "various":
        return None
        
    try:
        # Search for the artist
        results = discogs_client.search(artist_name, type='artist')
        if results and len(results) > 0:
            artist = results[0]
            return {
                'name': artist.name,
                'profile': artist.data.get('profile', ''),
                'urls': artist.data.get('urls', [])
            }
    except Exception as e:
        logging.error(f"Error fetching artist information for {artist_name}: {str(e)}")
    return None

def process_item(item, db_handler, spotify_token=None, jwt_apple_music_token=None, discogs_client=None):
    """
    Process a single Discogs item and create a dictionary of the item's information.
    
    Args:
        item (discogs_client.models.Item): The Discogs item to be processed.
        db_handler (DatabaseHandler): Database handler instance for caching.
        spotify_token (str): Optional Spotify API token.
        jwt_apple_music_token (str): Optional Apple Music API token.
        discogs_client: The Discogs client instance.
    
    Returns:
        dict: A dictionary of the item's information.
    """
    release = item.release
    release_id = release.id
    artist_info = None  # Initialize artist_info as None
    apple_music_data = None  # Initialize apple_music_data as None

    # Check if we already have this release in cache
    cached_data = db_handler.get_release(release_id)
    if cached_data:
        return cached_data

    try:
        artist_name = release.artists[0].name
        album_title = release.title
        artist_id = release.artists[0].id
        date_added = item.data['date_added'] if 'date_added' in item.data else None
        genre = release.genres
        style = release.styles
        label = release.labels[0].name if release.labels else None
        catalog_number = item.data['basic_information']['labels'][0]['catno'] if item.data['basic_information']['labels'] else None

        # Get release formats
        release_formats = [
            {
                key: fmt[key] for key in ["name", "qty", "text", "descriptions"] if key in fmt
            }
            for fmt in release.formats
        ] if release.formats else None

        release_date = release.year
        country = release.country
        rating = item.data.get('rating', 0)  # Default to 0 if not present

        # Get track list
        track_list = [{'number': track.position, 'title': track.title, 'duration': track.duration} for track in release.tracklist]

        # Get album cover URL
        cover_url = release.images[0]['resource_url'] if release.images else None
        all_images_urls = [img['resource_url'] for img in release.images] if release.images else None

        # Get videos
        videos = [{'title': video.title, 'url': video.url} for video in release.videos] if release.videos else None

        release_url = release.url
        notes = release.notes

        # Get credits
        credits = [str(credit) for credit in release.extraartists] if hasattr(release, 'extraartists') else None

        slug = sanitize_slug(f"{album_title}-{release_id}")

        # Get Spotify ID
        spotify_id = get_spotify_id(artist_name, album_title, spotify_token)

        # Get Wikipedia data
        wikipedia_summary, wikipedia_url = get_wikipedia_data(f"{escape_quotes(artist_name)} {album_title} (album)", album_title)

        # Create dictionary of item information
        item_data = {
            "Release ID": release_id,
            "Artist Name": artist_name,
            "Album Title": album_title,
            "Slug": slug,
            "Slug": slug,
            "Date Added": date_added,
            "Genre": genre,
            "Style": style,
            "Label": label,
            "Catalog Number": catalog_number,
            "Release Formats": release_formats,
            "Release Date": release_date,
            "Country": country,
            "Rating": rating,
            "Track List": track_list,
            "Album Cover URL": cover_url,
            "All Images URLs": all_images_urls,
            "Videos": videos,
            "Release URL": release_url,
            "Notes": notes,
            "Credits": credits,
            "Spotify ID": spotify_id,
            "Artist Info": artist_info,
            "Wikipedia Summary": wikipedia_summary,
            "Wikipedia URL": wikipedia_url
        }

        # Get Apple Music ID and other data
        if "various" not in artist_name.lower():
            apple_music_data = get_apple_music_data('albums', f'{escape_quotes(artist_name)} {escape_quotes(album_title)}', jwt_apple_music_token)
            if apple_music_data:
                for key, value in apple_music_data.items():
                    item_data[f"Apple Music {key}"] = value

        # Get artist information
        if apple_music_data:
            # If we have Apple Music data, use it to get artist info
            artist_info = {
                'id': artist_id,
                'name': artist_name,
                'profile': apple_music_data.get('artistBio', ''),
                'url': '',
                'aliases': [],
                'members': [],
                'images': [],
                'slug': sanitize_slug(artist_name)
            }
        else:
            # Otherwise get artist info from Discogs
            artist_info = get_artist_info(artist_name, discogs_client)
        item_data["Artist Info"] = artist_info

        # Save to cache before returning
        db_handler.save_release(release_id, item_data)
        return item_data
        
    except Exception as e:
        logging.error(f"Error processing item {release_id}: {str(e)}")
        db_handler.add_skip_release(release_id)
        return None

def load_last_processed_index():
    """
    Load the last processed index from the database.
    
    Returns:
        int: The last processed index, or 0 if not found.
    """
    db = DatabaseHandler(DB_PATH)
    return db.get_last_processed_index()

def load_skip_releases():
    """
    Load release IDs to skip from the database.
    
    Returns:
        set: A set of release IDs to skip.
    """
    db = DatabaseHandler(DB_PATH)
    return db.get_skip_releases()

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Process Discogs collection and create markdown files.')
    parser.add_argument('--all', action='store_true', help='Process all items in the collection')
    parser.add_argument('--delay', type=int, default=DEFAULT_DELAY, help=f'Delay between requests in seconds (default: {DEFAULT_DELAY})')
    args = parser.parse_args()

    # Set up logging
    log_directory = "logs"
    os.makedirs(log_directory, exist_ok=True)
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_filename = os.path.join(log_directory, f"log_{current_time}.log")
    logging.basicConfig(level=logging.INFO, filename=log_filename, filemode='w',
                        format='%(asctime)s - %(levelname)s - %(message)s')

    # Set the delay for requests
    global DELAY
    DELAY = args.delay

    # Initialize the database handler
    db_handler = DatabaseHandler(DB_PATH)

    # Load skip releases
    skip_releases = load_skip_releases()
    logging.info(f"Loaded {len(skip_releases)} releases to skip")

    # Load secrets
    with open('secrets.json', 'r') as f:
        secrets = json.load(f)

    # Get API credentials
    discogs_access_token = secrets['discogs_access_token']
    spotify_client_id = secrets['spotify_client_id']
    spotify_client_secret = secrets['spotify_client_secret']
    apple_music_client_id = secrets['apple_music_client_id']
    apple_developer_team_id = secrets['apple_developer_team_id']

    # Initialize Discogs client and get collection
    while True:
        try:
            discogs = discogs_client.Client('DiscogsScraperApp/1.0', user_token=discogs_access_token)
            me = discogs.identity()
            collection = me.collection_folders[0].releases
            num_items = len(collection)
            logging.info(f"Found {num_items} items in collection")
            break  # Exit loop if successful
        except discogs_client.exceptions.HTTPError as http_err:
            if http_err.status_code == 429:
                logging.warning("Rate limit exceeded while fetching collection. Waiting for 60 seconds before retrying...")
                time.sleep(60)
            else:
                raise  # Re-raise if it's not a 429 error

    # Initialize processed artists set
    processed_artists = set()

    # Get Spotify token
    spotify_token = get_spotify_token(spotify_client_id, spotify_client_secret)

    # Generate the Apple Music token
    jwt_apple_music_token = generate_apple_music_token(APPLE_KEY_FILE_PATH, apple_music_client_id, apple_developer_team_id)

    # Load last processed index
    last_processed_index = 0
    if os.path.exists(LAST_PROCESSED_INDEX_FILE):
        with open(LAST_PROCESSED_INDEX_FILE, 'r') as f:
            last_processed_index = int(f.read().strip() or 0)
    logging.info(f"Starting processing from index: {last_processed_index}")

    # Adjust total items for progress bar to reflect remaining items
    total_items_to_process = num_items - last_processed_index

    # Process all items in the collection
    with tqdm(total=total_items_to_process, unit="item", bar_format="{desc} |{bar}| {n_fmt}/{total_fmt} {unit} [{elapsed}<{remaining}]") as progress_bar:
        for index, item in enumerate(collection):
            if index < last_processed_index:
                logging.debug(f"Skipping index {index}, already processed.")
                progress_bar.update(1)
                continue
            try:
                # Skip if in skip_releases (compare as integers)
                if item.release.id in skip_releases:
                    logging.info(f"Skipping release {item.release.id} (in skip list)")
                    progress_bar.update(1)
                    continue

                # Log cache check
                logging.debug(f"Checking cache for release {item.release.id}")

                # For non-skipped items, check cache first
                cached_data = db_handler.get_release(item.release.id)
                
                if cached_data:
                    # Use cached data if it exists
                    item_data = cached_data
                    logging.debug(f"Using cached data for release {item.release.id}")
                else:
                    # Retry mechanism for handling 429 errors
                    while True:
                        try:
                            # Log API request
                            logging.info(f"Fetching data for release {item.release.id} from Discogs API")
                            item_data = process_item(item, db_handler, spotify_token, jwt_apple_music_token, discogs)
                            break  # Exit loop if successful
                        except discogs_client.exceptions.HTTPError as http_err:
                            if http_err.status_code == 429:
                                logging.warning("Rate limit exceeded. Waiting for 60 seconds before retrying...")
                                time.sleep(60)
                            else:
                                raise  # Re-raise if it's not a 429 error
                
                # Add delay between API requests
                if DELAY > 0:
                    time.sleep(DELAY)

                # Create markdown file if we have data
                if item_data:
                    create_markdown_file(item_data)
                
                # Update last processed index
                with open(LAST_PROCESSED_INDEX_FILE, 'w') as f:
                    f.write(str(index))
                
                progress_bar.update(1)

            except Exception as e:
                logging.error(f"Error processing release {item.release.id}: {str(e)}")
                progress_bar.update(1)
                continue

    # Zero out the last processed index file upon completion
    with open(LAST_PROCESSED_INDEX_FILE, 'w') as f:
        f.write('0')
    logging.info("Reset last processed index to 0 after completion.")

    # Print summary of missing images
    if hasattr(download_image, 'missing_images') and download_image.missing_images:
        print("\nMissing images that need to be downloaded:")
        print("==========================================")
        for filename, url in sorted(download_image.missing_images):
            print(f"Target path: {filename}")
            print(f"Source URL: {url}")
            print("-" * 50)
        print(f"\nTotal missing images: {len(download_image.missing_images)}")

    logging.info("Processing complete")

if __name__ == "__main__":
    main()