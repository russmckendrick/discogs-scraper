import csv
import os
import re
import json
import requests
import base64
import time
import discogs_client
from datetime import datetime
from urllib.request import urlretrieve
from tqdm import tqdm

discogs_csv_file = "discogs.csv"
output_folder = "website/content/albums"

# Function to sanitize a slug
def sanitize_slug(slug):
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r'\W+', ' ', slug)
    slug = slug.strip().lower().replace(' ', '-').replace('"', '')
    return slug

# Function to escape quotes
def escape_quotes(text):
    text = text.replace('"', '\\"')
    text = re.sub(r'\s\(\d+\)', '', text)  # Remove brackets and numbers inside them
    return text

# Function to download an image
def download_image(url, filename):
    try:
        urlretrieve(url, filename)
    except Exception as e:
        print(f'Unable to download image {url}, error {e}')

# Function to format the tracklist
def format_tracklist(tracklist):
    formatted_tracklist = []
    for index, track in enumerate(tracklist, start=1):
        title = track.title
        duration = track.duration
        if duration:
            formatted_tracklist.append(f"{index}. {title} ({duration})")
        else:
            formatted_tracklist.append(f"{index}. {title}")
    return "\n".join(formatted_tracklist)

# Function to extract the YouTube video ID from a URL
def extract_youtube_id(url):
    youtube_id_match = re.search(r'(?<=v=)[^&#]+', url)
    if youtube_id_match:
        return youtube_id_match.group(0)
    return None

# Function to format the video list
def format_videos(videos):
    formatted_videos = []
    for idx, video in enumerate(videos):
        title = video.title
        url = video.url
        if url is not None:
            youtube_id = extract_youtube_id(url)
            if youtube_id:
                if idx == 0:
                    formatted_videos.append(f"{{{{< youtube id=\"{youtube_id}\" title=\"{title}\" >}}}}")
                else:
                    formatted_videos.append(f"- [{title}]({url})")
    return "\n".join(formatted_videos)


# Function to format the album notes
def format_notes(album_notes):
    if not album_notes:
        return ""
    formatted_notes = album_notes.replace("\n", " ")
    formatted_notes = re.sub(
        r'\[url=(https?://[^\]]+)\]([^\[]+)\[/url\]',
        r'[\2](\1)',
        formatted_notes
    )
    return formatted_notes

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

def get_spotify_embed_code(spotify_id):
    if spotify_id:
        return f'{{{{< spotify type="album" id="{spotify_id}" width="100%" height="500" >}}}}'
    return ""

class MissingSecretError(Exception):
    pass

def load_secrets(file_path, required_secrets):
    with open(file_path, "r") as secret_file:
        secrets = json.load(secret_file)

    # Check for missing secrets
    missing_secrets = [key for key in required_secrets if key not in secrets]
    if missing_secrets:
        raise MissingSecretError(f"Missing secrets in {file_path}: {', '.join(missing_secrets)}")

    return secrets

# Define required secrets
required_secrets = ["discogs_access_token", "spotify_client_id", "spotify_client_secret"]

# Load secrets from the file
secrets_file = "secrets.json"
try:
    secrets = load_secrets(secrets_file, required_secrets)
except MissingSecretError as e:
    print(e)
    exit(1)

# Access the secrets
discogs_access_token = secrets['discogs_access_token']
spotify_client_id = secrets['spotify_client_id']
spotify_client_secret = secrets['spotify_client_secret']

# Create a Discogs client
discogs_client = discogs_client.Client("AlbumScraper/0.1", user_token=discogs_access_token)

# Create folders to store the markdown files and images
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Parse the CSV file
with open(discogs_csv_file, 'r') as csv_file:
    csv_reader = csv.DictReader(csv_file)
    total_rows = sum(1 for _ in csv_reader)
    csv_file.seek(0)
    csv_reader = csv.DictReader(csv_file)
    next(csv_reader)  # Skip the header row

    progress_bar = tqdm(csv_reader, total=total_rows - 1)

    for row in progress_bar:
        try:
            catalog_no = escape_quotes(row['Catalog#'])
            artist = escape_quotes(row['Artist'])
            title = escape_quotes(row['Title'])
            label = escape_quotes(row['Label'])
            release_format = escape_quotes(row['Format'])
            rating = row['Rating']
            released = row['Released']
            release_id = row['release_id']
            date_added = row['Date Added']
            media_condition = escape_quotes(row['Collection Media Condition'])
            sleeve_condition = escape_quotes(row['Collection Sleeve Condition'])
            notes = escape_quotes(row['Collection Notes'])
            date_added = datetime.strptime(date_added, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
            slug = sanitize_slug(title)

            progress_bar.set_description(f"Processing {title} by {artist} ({release_id})")

        except Exception as e:
            print(f"Error processing row: {row}\nError: {e}")

        # Create post folder
        post_folder = os.path.join(output_folder, slug+"-"+release_id)
        if not os.path.exists(post_folder):
            os.makedirs(post_folder)
        release = discogs_client.release(release_id)

        # Get album artwork URLs
        if release.images and len(release.images) > 0:
            image_url = release.images[0].get("uri", "")
            image_url_150 = release.images[0].get("uri150", "")
            image_filename = os.path.join(post_folder, f"{slug}-{release_id}.jpg")
            image_filename_150 = os.path.join(post_folder, f"{slug}-{release_id}-150.jpg")
            download_image(image_url, image_filename)
            download_image(image_url_150, image_filename_150)
        else:
            image_url = "https://github.com/russmckendrick/records/raw/b00f1d9fc0a67b391bde0b0fa93284c8e64d3dfe/assets/images/missing.jpg"
            image_url_150 = "https://github.com/russmckendrick/records/raw/b00f1d9fc0a67b391bde0b0fa93284c8e64d3dfe/assets/images/missing.jpg"
            image_filename = os.path.join(post_folder, f"{slug}-{release_id}.jpg")
            image_filename_150 = os.path.join(post_folder, f"{slug}-{release_id}-150.jpg")
            download_image(image_url, image_filename)
            download_image(image_url_150, image_filename_150)

        # Get tracklisting
        tracklist = release.tracklist
        formatted_tracklist = format_tracklist(tracklist)

        # Get videos
        videos = release.videos
        formatted_videos = format_videos(videos)

        # Get genres
        genres = release.genres
        # print(genres)
        formatted_genres = json.dumps(genres)

        # Get styles
        styles = release.styles
        formatted_styles = json.dumps(styles)

        # Get album notes
        album_notes = release.notes
        formatted_notes = format_notes(album_notes)

        # Get discogs release URL
        release_url = release.url

        spotify_id = get_spotify_id(artist, title)
        spotify_embed_code = get_spotify_embed_code(spotify_id)

        # Add a 2-second delay between requests to avoid hitting the rate limit
        time.sleep(2)

        # Check if spotify_embed_code is not empty
        if spotify_embed_code.strip():
            spotify_section = f"## Spotify\n{spotify_embed_code}\n"
        else:
            spotify_section = ""

        # Check if formatted_videos is not empty
        if formatted_videos.strip():
            videos_section = f"## Videos\n{formatted_videos}\n"
        else:
            videos_section = ""

        content = f"""---
title: "{artist} - {title}"
artist: "{artist}"
album_name: "{title}"
date: {date_added}
release_id: "{release_id}"
slug: "{slug}-{release_id}"
hideSummary: true
cover:
    image: "{slug}-{release_id}.jpg"
    alt: "{title} by {artist}"
    caption: "{title} by {artist}"
genres: {formatted_genres}
styles: {formatted_styles}
---
## Tracklisting
{formatted_tracklist}

{spotify_section}
{videos_section}
## Notes
| Notes          |             |
| ---------------| ----------- |
| Release Year   | {released} |
| Discogs Link   | [{artist} - {title}]({release_url}) |
| Label          | {label} |
| Format         | {release_format} |
| Catalog Number | {catalog_no} |

{formatted_notes}
"""
        with open(f"{post_folder}/index.md", "w") as md_file:
            md_file.write(content)
