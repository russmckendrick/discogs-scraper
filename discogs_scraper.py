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
from pathlib import Path
from urllib.request import urlretrieve
from jinja2 import Environment, FileSystemLoader
from tqdm import tqdm
from datetime import datetime

DELAY = 2
CACHE_FILE = 'collection_cache.json'
OUTPUT_DIRECTORY = 'website/content/posts'
ARTIST_IMAGES_DIRECTORY = "website/content/artist"

# Create logs folder if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Get the current date and time to append to the log file's name
current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

# Configure logging
logging.basicConfig(
    filename=f'logs/app_{current_time}.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Load access token and username from secrets.json
with open('secrets.json', 'r') as f:
    secrets = json.load(f)

discogs_access_token = secrets['discogs_access_token']
discogs_username = secrets['discogs_username']
spotify_client_id = secrets['spotify_client_id']
spotify_client_secret = secrets['spotify_client_secret']

# Initialize Discogs client
discogs = discogs_client.Client('DiscogsCollectionScript/1.0', user_token=discogs_access_token)

# Get user information and collection
user = discogs.identity()
collection = discogs.user(discogs_username).collection_folders[0].releases

# Check if the --all flag is passed
process_all = '--all' in sys.argv

# Check if the --num-items flag is passed and set the number of items to process
num_items_override = next((arg for arg in sys.argv if arg.startswith('--num-items=')), None)
if num_items_override:
    try:
        num_items = int(num_items_override.split('=')[1])
    except ValueError:
        logging.error("Invalid value for --num-items flag. Using default value (10).")
        num_items = 10
else:
    num_items = 10

# Determine the number of items to process
num_items = len(collection) if process_all else num_items

# Function to escape quotes
def escape_quotes(text):
    text = text.replace('"', '\\"')
    text = re.sub(r'\s\(\d+\)', '', text)  # Remove brackets and numbers inside them
    return text

# Function to sanitize a slug
def sanitize_slug(slug):
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r'\s\(\d+\)', '', slug)  # Remove brackets and numbers inside them
    slug = re.sub(r'\W+', ' ', slug)
    slug = slug.strip().lower().replace(' ', '-').replace('"', '')
    return slug

# Function to download an image
def download_image(url, filename, retries=3, delay=1):
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


# Function to extract the YouTube video ID from a URL
def extract_youtube_id(url):
    youtube_id_match = re.search(r'(?<=v=)[^&#]+', url)
    if youtube_id_match:
        return youtube_id_match.group(0)
    return None

# Spotify functions
def get_spotify_id(artist, album_name):
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

# Function to process artists only once
def process_artist(artist_info, processed_artists):
    if artist_info is not None:
        artist_id = artist_info["id"]
        if artist_id not in processed_artists:
            create_artist_markdown_file(artist_info)
            processed_artists.add(artist_id)

# Function to format notes
def format_notes(notes):
    if notes is None:
        return ""
    return notes.replace('\n', ' ').replace('\r', ' ')

# Function to format the tracklist
def format_tracklist(tracklist):
    formatted_tracklist = []
    for index, track in enumerate(tracklist, start=1):
        title = track["title"]
        duration = track["duration"]
        if duration:
            formatted_tracklist.append(f'{index}. {title} ({duration})')
        else:
            formatted_tracklist.append(f'{index}. {title}')
    return "\n".join(formatted_tracklist)

# Function to format the release formats
def format_release_formats(release_formats):
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

# Function to create an artist markdown file
def create_artist_markdown_file(artist_data, output_dir=ARTIST_IMAGES_DIRECTORY):
    
    if artist_data is not None:
        artist_name = escape_quotes(artist_data["name"])
        slug = sanitize_slug(artist_data["slug"])
        folder_path = Path(output_dir) / slug
        image_filename = f"{slug}.jpg"
        image_path = folder_path / image_filename
        artist_image_url = artist_data["images"][0]
        if artist_image_url:
            download_image(artist_image_url, image_path)
        else:
            missing_cover_url = "https://github.com/russmckendrick/records/raw/b00f1d9fc0a67b391bde0b0fa93284c8e64d3dfe/assets/images/missing.jpg"
            download_image(missing_cover_url, image_path)

        # Check if the artist file already exists
        artist_file_path = folder_path / "_index.md"

        # Create the output directory if it doesn't exist
        folder_path.mkdir(parents=True, exist_ok=True)

        # Render markdown file using Jinja2 template
        env = Environment(loader=FileSystemLoader('.'))
        template = env.get_template('artist_template.md')

        rendered_content = template.render(
            name=escape_quotes(artist_name),
            slug=sanitize_slug(artist_data["slug"]),
            profile=escape_quotes(artist_data["profile"]),
            aliases=artist_data["aliases"],
            members=artist_data["members"],
            image=image_filename,
        )

        # Save the rendered content to the markdown file
        with open(artist_file_path, "w") as f:
            f.write(rendered_content)
        logging.info(f"Saved artist file {artist_file_path}")

    else:
        logging.error('No artist information, skipping')
        return None

# Function to create the album markdown file
def create_markdown_file(item_data, output_dir=OUTPUT_DIRECTORY):
    artist = item_data["Artist Name"]
    album_name = item_data["Album Title"]
    release_id = str(item_data["Release ID"])
    cover_url = item_data["Album Cover URL"]
    slug = item_data["Slug"]
    folder_path = Path(output_dir) / slug

    # Create the output directory if it doesn't exist
    folder_path.mkdir(parents=True, exist_ok=True)

    # Download album cover
    cover_filename = f"{slug}.jpg"
    cover_path = folder_path / cover_filename
    if cover_url:
        download_image(cover_url, cover_path)
    else:
        missing_cover_url = "https://github.com/russmckendrick/records/raw/b00f1d9fc0a67b391bde0b0fa93284c8e64d3dfe/assets/images/missing.jpg"
        download_image(missing_cover_url, cover_path)

    # Render markdown file using Jinja2 template
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('album_template.md')
    genres = item_data.get("Genre", [])
    styles = item_data.get("Style", [])
    videos = item_data["Videos"]
    first_video = random.choice(videos) if videos else None
    additional_videos = [video for video in videos if video != first_video] if videos and len(videos) > 1 else None

    rendered_content = template.render(
        title="{artist} - {album_name}".format(artist=escape_quotes(artist), album_name=album_name),
        artist=escape_quotes(artist),
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
    )

    # Save the rendered content to the markdown file
    with open(folder_path / "index.md", "w") as f:
        f.write(rendered_content)
    logging.info(f"Saved/Updated file {folder_path}.index.md")

# Load collection cache or create an empty cache
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, 'r') as f:
        collection_cache = json.load(f)
else:
    collection_cache = {}

def get_artist_info(artist_id):
    try:
        artist = discogs.artist(artist_id)
        artist_info = {
            'id': artist.id,
            'name': artist.name,
            'profile': artist.profile,
            'url': artist.url,
            'aliases': [{'id': alias.id, 'name': alias.name} for alias in artist.aliases] if artist.aliases else [],
            'members': [{'id': member.id, 'name': member.name} for member in artist.members] if artist.members else [],
            'images': [image['resource_url'] for image in artist.images] if artist.images else [],
            "slug": sanitize_slug(artist.name), 
        }
        return artist_info
    except Exception as e:
        logging.error(f'Error fetching artist information for ID {artist_id}: {e}')
        return None

# Define a function to process an item and add it to the cache
def process_item(item, cache):
    release = item.release
    release_id = release.id
    artist_info = None  # Initialize artist_info as None

    if str(release_id) not in cache:
        artist_name = release.artists[0].name
        album_title = release.title
        artist_id = release.artists[0].id
        artist_info = get_artist_info(artist_id)
        date_added = item.date_added.isoformat() if item.date_added else None
        genre = release.genres
        style = release.styles
        label = release.labels[0].name if release.labels else None
        catalog_number = release.labels[0].catno if release.labels else None
        release_formats = [
            {
                key: fmt[key] for key in ["name", "qty", "text", "descriptions"] if key in fmt
            }
            for fmt in release.formats
        ] if release.formats else None
        release_date = release.year
        country = release.country
        rating = release.community.rating.average
        track_list = [{'number': track.position, 'title': track.title, 'duration': track.duration} for track in release.tracklist]
        cover_url = release.images[0]['resource_url'] if release.images else None
        videos = [{'title': video.title, 'url': video.url} for video in release.videos] if release.videos else None
        release_url = release.url
        notes = release.notes
        credits = [str(credit) for credit in release.extraartists] if hasattr(release, 'extraartists') else None
        slug = sanitize_slug(f"{album_title}-{release_id}")
        spotify_id = get_spotify_id(artist_name, album_title)

        cache[str(release_id)] = {
            "Release ID": release_id,
            "Artist Name": artist_name,
            "Album Title": album_title,
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
            "Videos": videos,
            "Release URL": release_url,
            "Notes": notes,
            "Credits": credits,
            "Spotify ID": spotify_id,
            "Artist Info": artist_info,
        }

# Initialize a set for processed artists
processed_artists = set()

# Iterate through the collection, update the cache, and create the markdown file
with tqdm(total=num_items, unit="item", bar_format="{desc} |{bar}| {n_fmt}/{total_fmt} {unit} [{elapsed}<{remaining}]") as progress_bar:
    for i, item in enumerate(collection):
        if i >= num_items:
            break

        # Process the current item and update the cache
        process_item(item, collection_cache)
        release_id = item.release.id
        release_data = collection_cache[str(release_id)]
        artist_info = release_data["Artist Info"]

        # Update the progress bar with current item information
        progress_bar.set_description(f'Currently Processing: {release_data["Album Title"]} by {release_data["Artist Name"]} ({release_id})')
        progress_bar.update(1)

        # Create the release markdown file
        create_markdown_file(release_data)

        # Process the artist and create the artist markdown file if not processed before
        process_artist(artist_info, processed_artists)

        # Add a delay between requests to avoid hitting the rate limit
        time.sleep(DELAY)

# Save the updated cache to the file
with open(CACHE_FILE, 'w') as f:
    json.dump(collection_cache, f, indent=4)

# Check if the --num-items flag is passed and set the number of items to process
num_items_override = next((arg for arg in sys.argv if arg.startswith('--num-items=')), None)
if num_items_override:
    try:
        num_items = int(num_items_override.split('=')[1])
    except ValueError:
        logging.error("Invalid value for --num-items flag. Using default value (10).")