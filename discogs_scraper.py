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

####################################################################################################
# Variables
####################################################################################################

CACHE_FILE = 'collection_cache.json' # File to store the collection cache
OVERRIDE_CACHE_FILE = 'collection_cache_override.json' # File to store the override collection cache
LAST_PROCESSED_INDEX_FILE = "last_processed_index.txt" # File to store the last processed index
OUTPUT_DIRECTORY = 'website/content/albums' # Directory to store the output files
ARTIST_DIRECTORY = "website/content/artist" # Directory to store artist information
APPLE_KEY_FILE_PATH = 'backups/apple_private_key.p8' # Path to the apple private key file
DEFAULT_DELAY = 2 # Set delay between requests
APPLE_MUSIC_STOREFRONT = "gb" # Storefront for Apple Music
SKIP_RELEASE_FILE = 'skip_releases.txt'

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
    
    Raises:
        wikipedia.exceptions.DisambiguationError: If the target leads to a disambiguation page.
        wikipedia.exceptions.PageError: If the Wikipedia page does not exist.
    """
    try:
        page = wikipedia.page(target)
        # Check if the URL contains the keyword
        # Make comparison case-insensitive and replace spaces with underscores
        if keyword.lower().replace(' ', '_') in page.url.lower():
            return page.summary, page.url
        else:
            # Log an error message
            logging.error(f"URL of the page for '{target}' does not contain the keyword '{keyword}'.")
            return None, None
    except wikipedia.exceptions.DisambiguationError as e:
        # Handle disambiguation error
        logging.error(f"DisambiguationError: Multiple potential matches found for '{target}' on Wikipedia.")
        return None, None
    except wikipedia.exceptions.PageError as e:
        # Handle page not found error
        logging.error(f"PageError: No page found for '{target}' on Wikipedia.")
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

@retry(wait=wait_fixed(60))  # Adjust this value as needed
def download_image(url, filename, retries=5, delay=15):
    """
    Downloads an image from a given URL and saves it to a specified file.

    Args:
        url (str): The URL of the image to download.
        filename (str): The path and name of the file to save the image to.
        retries (int, optional): The number of times to retry the download if it fails. Defaults to 3.
        delay (int, optional): The time to wait (in seconds) between retries. Defaults to 1.
    """
    folder_path = Path(filename).parent
    folder_path.mkdir(parents=True, exist_ok=True)

    if os.path.exists(filename):
        logging.info(f"Image file {filename} already exists. Skipping download.")
        return

    for attempt in range(retries):
        try:
            logging.info(f"Image file {filename} doesn't exist. Downloading. (Attempt {attempt + 1})")
            urlretrieve(url, filename)
            break
        except Exception as e:
            logging.error(f'Unable to download image {url}, error {e}')
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                logging.error(f'Failed to download image {url} after {retries} attempts')

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

def get_spotify_id(artist, album_name):
    """
    Gets the Spotify ID of an album given the artist and album name.
    
    Args:
        artist (str): The name of the artist.
        album_name (str): The name of the album.
        
    Returns:
        str: The Spotify ID of the album, or None if not found.
    """
    token = get_spotify_token()
    url = 'https://api.spotify.com/v1/search'
    params = {
        'q': f'artist:{artist} album:{album_name}',
        'type': 'album',
        'limit': 1
    }
    headers = {
        'Authorization': f'Bearer {token}'
    }

    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        json_response = response.json()
        if json_response.get('albums', {}).get('items'):
            spotify_id = json_response['albums']['items'][0]['id']
            return spotify_id
    return None

def get_spotify_token():
    """
    Gets an access token for the Spotify API using client credentials authentication.
    
    Returns:
        str: The access token, or None if not obtained.
    """
    url = 'https://accounts.spotify.com/api/token'
    headers = {
        'Authorization': f'Basic {base64.b64encode(f"{spotify_client_id}:{spotify_client_secret}".encode()).decode()}'
    }
    data = {
        'grant_type': 'client_credentials'
    }

    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        json_response = response.json()
        access_token = json_response.get('access_token')
        return access_token
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
        first_video_title=first_video["title"] if first_video else None,
        additional_videos=additional_videos,
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

def get_artist_info(artist_id):
    """
    Retrieves information about an artist with the specified ID from Discogs.

    Args:
        artist_id (int): The ID of the artist to fetch information for.

    Returns:
        dict or None: A dictionary containing information about the artist, including their ID, name, profile, URL, aliases,
        members, images, and slug. If the artist cannot be found or an error occurs, it returns None.
    """

    try:
        # Retrieve the artist from Discogs using the specified ID
        artist = discogs.artist(artist_id)

        # Fetch the Wikipedia summary and URL for the artist
        artist_wikipedia_summary, artist_wikipedia_url = get_wikipedia_data(f"{escape_quotes(artist.name)} (band)", escape_quotes(artist.name))



        # Create a dictionary containing information about the artist
        artist_info = {
            'id': artist.id,
            'name': artist.name,
            'profile': artist.profile,
            'url': artist.url,
            'aliases': [{'id': alias.id, 'name': alias.name} for alias in artist.aliases] if artist.aliases else [],
            'members': [{'id': member.id, 'name': member.name} for member in artist.members] if artist.members else [],
            'images': [image['resource_url'] for image in artist.images] if artist.images else [],
            'slug': sanitize_slug(artist.name),  # Create a sanitized string representation of the artist name
            'artist_wikipedia_summary': artist_wikipedia_summary,  # Add the Wikipedia summary
            'artist_wikipedia_url': artist_wikipedia_url,  # Add the Wikipedia URL
        }

        # Return the artist information dictionary
        return artist_info

    except Exception as e:
        # Log an error message if the artist cannot be found or an error occurs
        logging.error(f'Error fetching artist information for ID {artist_id}: {e}')
        return None


def process_item(item, cache):
    """
    Process a single Discogs item and create a dictionary of the item's information.

    Args:
        item (discogs_client.models.Item): The Discogs item to be processed.
        cache (dict): A dictionary to store processed items in.

    Returns:
        dict: A dictionary of the item's information.

    """
    release = item.release
    release_id = release.id
    artist_info = None  # Initialize artist_info as None
    apple_music_data = None  # Initialize apple_music_data as None

    if str(release_id) not in cache:
        artist_name = release.artists[0].name
        album_title = release.title
        artist_id = release.artists[0].id
        date_added = item.date_added.isoformat() if item.date_added else None
        genre = release.genres
        style = release.styles
        label = release.labels[0].name if release.labels else None
        catalog_number = release.labels[0].catno if release.labels else None

        # Get release formats
        release_formats = [
            {
                key: fmt[key] for key in ["name", "qty", "text", "descriptions"] if key in fmt
            }
            for fmt in release.formats
        ] if release.formats else None

        release_date = release.year
        country = release.country
        rating = release.community.rating.average

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
        spotify_id = get_spotify_id(artist_name, album_title)

        # Get Wikipedia data
        wikipedia_summary, wikipedia_url = get_wikipedia_data(f"{escape_quotes(artist_name)} {album_title} (album)", album_title)

        # Create dictionary of item information
        cache[str(release_id)] = {
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
                    cache[str(release_id)][f"Apple Music {key}"] = value

        # Get artist information
        if apple_music_data:
            discogs_artist_info = get_artist_info(artist_id)
            apple_music_artist_info = get_apple_music_data('artists', escape_quotes(artist_name), jwt_apple_music_token)
            if discogs_artist_info is not None and apple_music_artist_info is not None:
                artist_info = {**discogs_artist_info, **apple_music_artist_info}  # Merge Discogs and Apple Music artist info
            elif discogs_artist_info is not None:
                artist_info = discogs_artist_info
            elif apple_music_artist_info is not None:
                artist_info = apple_music_artist_info
            else:
                artist_info = None
        else:
            artist_info = get_artist_info(artist_id)


        cache[str(release_id)]["Artist Info"] = artist_info

        return cache[str(release_id)]

# Function to load the last processed index
def load_last_processed_index():
    """
    Load the last processed index from a file.

    This function attempts to open a file containing the last processed index and return it.
    If the file is not found, it will return 0. If any other exceptions occur, they are logged and 0 is returned.

    Returns:
        int: The last processed index, or 0 if an error occurred.
    """
    try:
        with open(LAST_PROCESSED_INDEX_FILE, 'r') as f:
            return int(f.read())
    except FileNotFoundError:
        return 0
    except Exception as e:
        logging.error(f"Error occurred while loading last processed index: {str(e)}")
        return 0

def load_skip_releases():
    """
    Load release IDs to skip from a file.

    Returns:
        set: A set of release IDs to skip.
    """
    skip_releases = set()
    try:
        with open(SKIP_RELEASE_FILE, 'r') as f:
            for line in f:
                skip_releases.add(line.strip())
        logging.info(f"Loaded {len(skip_releases)} release IDs to skip.")
    except FileNotFoundError:
        logging.warning(f"{SKIP_RELEASE_FILE} not found. No releases will be skipped.")
    return skip_releases

####################################################################################################
# Main script
####################################################################################################

# Create logs folder if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

skip_releases = load_skip_releases()

# Get the current date and time to append to the log file's name
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Configure logging with the log file's name, format, and log level
logging.basicConfig(
    filename=f'logs/app_{current_time}.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Load access token and username from secrets.json
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

# Store Discogs and Spotify API credentials from secrets.json
discogs_access_token = secrets['discogs_access_token']
discogs_username = secrets['discogs_username']
spotify_client_id = secrets['spotify_client_id']
spotify_client_secret = secrets['spotify_client_secret']
apple_music_client_id = secrets['apple_music_client_id']
apple_developer_team_id = secrets['apple_developer_team_id']

# Initialize Discogs client with the user token
discogs = discogs_client.Client('DiscogsCollectionScript/1.0', user_token=discogs_access_token)

# Retrieve user information and collection from Discogs
user = discogs.identity()
collection = discogs.user(discogs_username).collection_folders[0].releases

# Check if the --all flag is passed to process all items in the collection
process_all = '--all' in sys.argv

# Check if the --delay flag is passed and set the delay between requests accordingly
delay_override = next((arg for arg in sys.argv if arg.startswith('--delay=')), None)
if delay_override:
    try:
        delay_value = float(delay_override.split('=')[1])
        if delay_value < 0:
            raise ValueError("Delay value must be non-negative")
        DELAY = delay_value
    except ValueError as e:
        logging.error(f"Invalid value for --delay flag. Using default value ({DEFAULT_DELAY}). Error: {e}")
        DELAY = DEFAULT_DELAY
else:
    DELAY = DEFAULT_DELAY

# Check if the --num-items flag is passed and set the number of items to process accordingly
num_items_override = next((arg for arg in sys.argv if arg.startswith('--num-items=')), None)
if num_items_override:
    try:
        num_items = int(num_items_override.split('=')[1])
    except ValueError:
        logging.error("Invalid value for --num-items flag. Using default value (10).")
        num_items = 10
else:
    num_items = 10

# Determine the number of items to process based on the flags
num_items = len(collection) if process_all else num_items

collection_cache = {}
override_cache = {}

# Check if both cache files exist
if not os.path.exists(CACHE_FILE):
    raise FileNotFoundError(f"{CACHE_FILE} not found.")
if not os.path.exists(OVERRIDE_CACHE_FILE):
    raise FileNotFoundError(f"{OVERRIDE_CACHE_FILE} not found.")

# Load the cache files
with open(CACHE_FILE, 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            if isinstance(data, dict) and len(data) == 1:
                collection_cache.update(data)
            else:
                logging.warning(f"Skipping invalid data in {CACHE_FILE}: {line.strip()}")
        except json.decoder.JSONDecodeError as e:
            logging.error(f"Error parsing JSON in {CACHE_FILE}: {e}")
            # Skip the problematic line and continue with the next line

with open(OVERRIDE_CACHE_FILE, 'r') as f:
    for line in f:
        try:
            data = json.loads(line)
            if isinstance(data, dict) and len(data) == 1:
                override_cache.update(data)
            else:
                logging.warning(f"Skipping invalid data in {OVERRIDE_CACHE_FILE}: {line.strip()}")
        except json.decoder.JSONDecodeError as e:
            logging.error(f"Error parsing JSON in {OVERRIDE_CACHE_FILE}: {e}")
            # Skip the problematic line and continue with the next line

# Initialize a set for processed artists
processed_artists = set()
last_processed_index = load_last_processed_index()  # Load from file or initialize to 0

# Generate the Apple Music token
jwt_apple_music_token = generate_apple_music_token(APPLE_KEY_FILE_PATH, apple_music_client_id, apple_developer_team_id)

# Iterate through the collection, update the cache, and create the markdown file
with tqdm(total=num_items, unit="item", bar_format="{desc} |{bar}| {n_fmt}/{total_fmt} {unit} [{elapsed}<{remaining}]") as progress_bar:
    # Update the progress bar to reflect already processed items
    progress_bar.update(last_processed_index)
    with open(CACHE_FILE, 'a') as cache_file:
        for i, item in enumerate(collection):
            if i < last_processed_index:
                # Skip the already processed items
                continue

            if i >= num_items:
                break

            # Process the current item
            release_id = str(item.release.id)
            
            # Check if the release should be skipped
            if release_id in skip_releases:
                logging.info(f"Skipping release ID {release_id} as it's in the skip list.")
                progress_bar.update(1)
                continue

            if release_id in override_cache:
                # Retrieve the release data from the override cache
                release_data = override_cache[release_id]
                artist_info = release_data["Artist Info"]
                logging.info(f'Using override cache for: {release_data["Album Title"]} by {release_data["Artist Name"]} ({release_id})')
            elif release_id in collection_cache:
                # If not in override cache, check the normal cache
                release_data = collection_cache[release_id]
                artist_info = release_data["Artist Info"]
                logging.info(f'Using cached information for: {release_data["Album Title"]} by {release_data["Artist Name"]} ({release_id})')
            else:
                # Fetch the release data and update the cache
                process_item(item, collection_cache)
                release_data = collection_cache[release_id]
                artist_info = release_data["Artist Info"]
                logging.info(f'Fetching information for: {release_data["Album Title"]} by {release_data["Artist Name"]} ({release_id})')

                # Write the current item to the cache file
                cache_file.write(json.dumps({release_id: release_data}) + '\n')

                # Log the action of writing to the cache
                logging.info(f'Writing information to cache for: {release_data["Album Title"]} by {release_data["Artist Name"]} ({release_id})')


            # Update the progress bar with current item information
            progress_bar.set_description(f'Currently Processing: {release_data["Album Title"]} by {release_data["Artist Name"]} ({release_id})')
            progress_bar.update(1)

            # Create the release markdown file
            create_markdown_file(release_data)

            # Process the artist and create the artist markdown file if not processed before
            process_artist(artist_info, processed_artists)

            # Update the last processed index
            last_processed_index = i + 1

            # Add a delay between requests to avoid hitting the rate limit
            if DELAY > 0:
                time.sleep(DELAY)

            # Save the last processed index to the file
            with open(LAST_PROCESSED_INDEX_FILE, 'w') as f:
                f.write(str(last_processed_index))

# Delete the last processed index file after successful completion
if os.path.exists(LAST_PROCESSED_INDEX_FILE):
    os.remove(LAST_PROCESSED_INDEX_FILE)
    logging.info("Deleted the last processed index file.")