import csv
import os
import re
import json
from datetime import datetime
import discogs_client
import time
from urllib.request import urlretrieve
from tqdm import tqdm

discogs_csv_file = "discogs.csv"

# Function to sanitize a slug
def sanitize_slug(slug):
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r'\W+', ' ', slug)
    slug = slug.strip().lower().replace(' ', '-').replace('"', '')
    return slug

# Function to escape quotes
def escape_quotes(text):
    return text.replace('"', '\\"')

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
        duration = video.duration
        url = video.url
        if url:  # Add this check
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

# Function to load the Discogs API access token from a file
def load_discogs_token(file_path):
    with open(file_path, "r") as token_file:
        token = token_file.read().strip()
    return token

# Load the Discogs API access token from a file
discogs_token_file = "discogs_token.txt"
discogs_access_token = load_discogs_token(discogs_token_file)
if not discogs_access_token:
    raise ValueError("Discogs API access token not found in the file '{}'".format(discogs_token_file))

# Create a Discogs client
discogs_client = discogs_client.Client("AlbumScraper/0.1", user_token=discogs_access_token)

# Create folders to store the markdown files and images
output_folder = "website/content/albums"
if not os.path.exists(output_folder):
    os.makedirs(output_folder)

# Parse the CSV file
with open(discogs_csv_file, 'r') as csv_file:
    csv_reader = csv.DictReader(csv_file)
    total_rows = sum(1 for _ in csv_reader)
    csv_file.seek(0)
    csv_reader = csv.DictReader(csv_file)
    for row in tqdm(csv_reader, desc="Processing CSV Rows", total=total_rows):
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

            # Download images
            image_filename = os.path.join(post_folder, f"{slug}-{release_id}.jpg")
            image_filename_150 = os.path.join(post_folder, f"{slug}-{release_id}-150.jpg")
            download_image(image_url, image_filename)
            download_image(image_url_150, image_filename_150)

            # Get tracklisting
            tracklist = release.tracklist
            # print(tracklist)
            formatted_tracklist = format_tracklist(tracklist)

            # Get videos
            videos = release.videos
            # print(videos)
            formatted_videos = format_videos(videos)

            # Get genres
            genres = release.genres
            # print(genres)
            formatted_genres = json.dumps(genres)

            # Get styles
            styles = release.styles
            # print(genres)
            formatted_styles = json.dumps(styles)

            # Get album notes
            album_notes = release.notes
            # print(album_notes)
            formatted_notes = format_notes(album_notes)

            release_url = release.url
            # print(release_url)

            # Add a 2-second delay between requests to avoid hitting the rate limit
            time.sleep(2)

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
