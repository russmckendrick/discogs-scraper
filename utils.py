import logging
import re
import wikipedia
import requests
import base64
from difflib import SequenceMatcher
import os
import html2text

def sanitize_slug(text):
    """
    Convert text to a URL-friendly slug.
    """
    # Convert to lowercase
    slug = text.lower()
    
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
        'limit': 5
    }

    try:
        response = requests.get(base_url, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            if search_type in data['results'] and data['results'][search_type]['data']:
                results = data['results'][search_type]['data']
                best_match = max(results, key=lambda x: SequenceMatcher(None, query.lower(), x['attributes']['name'].lower()).ratio())
                return best_match
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

def download_artist_image(url, output_path, size='2000x2000'):
    """
    Downloads artist image, converting Apple Music URL to desired size if needed.
    Returns True if successful, False otherwise.
    """
    if os.path.exists(output_path):
        logging.info(f"Artist image already exists at {output_path}")
        return True
        
    try:
        if 'mzstatic.com' in url:
            # Replace {w}x{h} with desired size for Apple Music URLs
            url = url.replace('{w}x{h}', size)
        
        logging.info(f"Downloading artist image from {url}")
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
    except Exception as e:
        logging.error(f"Error downloading artist image: {str(e)}")
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
        # Convert to markdown and clean up
        profile = html2text.handle(profile)
        # Remove multiple newlines
        profile = re.sub(r'\n\s*\n', '\n\n', profile)
        # Remove any remaining HTML
        profile = re.sub(r'<[^>]+>', '', profile)
        
    return profile

def sanitize_artist_name(name):
    """
    Sanitizes artist name by removing numbers in brackets etc.
    """
    # Remove numbers in brackets at end of name
    name = re.sub(r'\s*\(\d+\)\s*$', '', name)
    return name.strip() 