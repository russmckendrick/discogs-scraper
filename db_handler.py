import sqlite3
from pathlib import Path
import json
import logging
import time
from utils import sanitize_slug, get_wikipedia_data, search_apple_music, download_artist_image, get_best_artist_profile, sanitize_artist_name
import os
from jinja2 import Template

class DatabaseHandler:
    def __init__(self, db_path='collection_cache.db', skip_file='skip_releases.txt'):
        self.db_path = db_path
        self.skip_file = skip_file
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create releases table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS releases (
                    id INTEGER PRIMARY KEY,
                    release_id INTEGER UNIQUE,
                    data TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create artists table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS artists (
                    id INTEGER PRIMARY KEY,
                    artist_id INTEGER UNIQUE,
                    name TEXT,
                    data TEXT,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create skip_releases table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS skip_releases (
                    release_id INTEGER PRIMARY KEY
                )
            ''')
            
            # Create processed_index table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_index (
                    id INTEGER PRIMARY KEY,
                    last_index INTEGER
                )
            ''')
            conn.commit()

    def save_release(self, release_id, data):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT OR REPLACE INTO releases (release_id, data) VALUES (?, ?)',
                (release_id, json.dumps(data))
            )
            conn.commit()

    def get_release(self, release_id):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT data FROM releases WHERE release_id = ?', (release_id,))
            result = cursor.fetchone()
            if result:
                logging.info(f"Found release {release_id} in database")
                return json.loads(result[0])
            else:
                logging.warning(f"No release found with ID {release_id}")
                return None

    def get_all_releases(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT release_id, data FROM releases')
            return {row[0]: json.loads(row[1]) for row in cursor.fetchall()}

    def get_skip_releases(self):
        """Load skip releases from the text file."""
        skip_releases = set()
        try:
            with open(self.skip_file, 'r') as f:
                for line in f:
                    skip_releases.add(int(line.strip()))
            logging.info(f"Loaded {len(skip_releases)} release IDs to skip from {self.skip_file}")
        except FileNotFoundError:
            logging.warning(f"{self.skip_file} not found. No releases will be skipped.")
        return skip_releases

    def add_skip_release(self, release_id):
        """Add a release ID to skip_releases.txt file."""
        try:
            with open(self.skip_file, 'a') as f:
                f.write(f"{release_id}\n")
            logging.info(f"Added release ID {release_id} to skip list")
        except Exception as e:
            logging.error(f"Error adding release ID {release_id} to skip list: {str(e)}")

    def save_last_processed_index(self, index):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT OR REPLACE INTO processed_index (id, last_index) VALUES (1, ?)', (index,))
            conn.commit()

    def get_last_processed_index(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT last_index FROM processed_index WHERE id = 1')
            result = cursor.fetchone()
            return result[0] if result else 0

    def save_artist(self, artist_id, name, data):
        """
        Save or update artist information in the database.
        
        Args:
            artist_id (int): The Discogs artist ID
            name (str): The artist name
            data (dict): The artist data dictionary
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                '''
                INSERT OR REPLACE INTO artists (artist_id, name, data) 
                VALUES (?, ?, ?)
                ''',
                (artist_id, name, json.dumps(data))
            )
            conn.commit()
            logging.info(f"Saved/updated artist {name} (ID: {artist_id}) in database")

    def get_artist(self, artist_id):
        """
        Get artist information from the database.
        
        Args:
            artist_id (int): The Discogs artist ID
            
        Returns:
            dict: Artist data if found, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT data FROM artists WHERE artist_id = ?', (artist_id,))
            result = cursor.fetchone()
            if result:
                logging.info(f"Found artist {artist_id} in database")
                return json.loads(result[0])
            else:
                logging.debug(f"No artist found with ID {artist_id}")
                return None

    def get_all_artists(self):
        """
        Get all artists from the artists table.
        
        Returns:
            list: List of tuples (artist_id, name, data)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT artist_id, name, data FROM artists ORDER BY name')
            results = cursor.fetchall()
            return [(row[0], row[1], json.loads(row[2])) for row in results]

    def migrate_artists_from_releases(self, discogs_client=None, jwt_apple_music_token=None):
        """
        Migrate artist data from releases table to artists table.
        This will extract unique artists from releases and fetch fresh data for each.
        
        Args:
            discogs_client: Authenticated Discogs client instance
            jwt_apple_music_token: Apple Music JWT token
        """
        if not discogs_client:
            raise ValueError("Discogs client is required for artist migration")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # First, clear the artists table
            cursor.execute('DELETE FROM artists')
            conn.commit()
            logging.info("Cleared existing artists table")
            
            # Get all unique artists from releases
            cursor.execute('''
                SELECT DISTINCT json_extract(data, '$.Artist Name') as artist_name,
                              json_extract(data, '$.Artist Info.id') as artist_id
                FROM releases 
                WHERE json_extract(data, '$.Artist Name') IS NOT NULL 
                AND json_extract(data, '$.Artist Name') != 'Various'
                ORDER BY artist_name
            ''')
            artists = cursor.fetchall()
            
            artists_processed = set()
            artists_count = 0
            
            logging.info(f"Found {len(artists)} unique artists in releases")
            
            for artist_name, artist_id in artists:
                try:
                    if artist_id in artists_processed:
                        continue
                    
                    logging.info(f"Processing artist: {artist_name}")
                    
                    # Get full artist data from Discogs
                    artist = discogs_client.artist(artist_id)
                    
                    # Initialize data structure
                    artist_info = {
                        'id': artist_id,
                        'name': artist_name,
                        'profile': artist.profile if hasattr(artist, 'profile') else '',
                        'url': artist.url if hasattr(artist, 'url') else '',
                        'aliases': [alias.name for alias in artist.aliases] if hasattr(artist, 'aliases') else [],
                        'members': [member.name for member in artist.members] if hasattr(artist, 'members') else [],
                        'images': [img.get('resource_url') for img in artist.images] if hasattr(artist, 'images') else [],
                        'slug': sanitize_slug(artist_name),
                        'artist_wikipedia_summary': None,
                        'artist_wikipedia_url': None,
                        'apple_music_url': None,
                        'apple_music_image': None,
                        'apple_music_bio': None
                    }

                    # Try to get Wikipedia data if function is available
                    try:
                        if 'get_wikipedia_data' in globals():
                            wiki_summary, wiki_url = get_wikipedia_data(artist_name, artist_name)
                            artist_info['artist_wikipedia_summary'] = wiki_summary
                            artist_info['artist_wikipedia_url'] = wiki_url
                    except Exception as e:
                        logging.error(f"Error getting Wikipedia data for {artist_name}: {str(e)}")

                    # Try to get Apple Music data if token is provided
                    if jwt_apple_music_token:
                        try:
                            if 'search_apple_music' in globals():
                                apple_music_data = search_apple_music(artist_name, 'artists', jwt_apple_music_token)
                                if apple_music_data:
                                    artist_info.update({
                                        'apple_music_url': apple_music_data.get('attributes', {}).get('url'),
                                        'apple_music_image': apple_music_data.get('attributes', {}).get('artwork', {}).get('url'),
                                        'apple_music_bio': apple_music_data.get('attributes', {}).get('artistBio')
                                    })
                        except Exception as e:
                            logging.error(f"Error getting Apple Music data for {artist_name}: {str(e)}")
                    
                    # Save to database
                    self.save_artist(artist_id, artist_name, artist_info)
                    artists_processed.add(artist_id)
                    artists_count += 1
                    
                    if artists_count % 10 == 0:
                        logging.info(f"Processed {artists_count} artists...")
                    
                    # Add delay to respect rate limits
                    time.sleep(1)
                    
                except Exception as e:
                    logging.error(f"Error processing artist {artist_name}: {str(e)}")
                    continue
            
            logging.info(f"Artist migration complete. Migrated {artists_count} unique artists")

    def verify_artist(self, artist_name, artist_id, discogs_client):
        """
        Verifies artist exists in cache, adds if missing.
        Returns artist info dict.
        """
        artist_info = self.get_artist(artist_id)
        if not artist_info:
            logging.info(f"Artist {artist_name} not in cache, fetching data")
            try:
                # Get full artist data from Discogs
                artist = discogs_client.artist(artist_id)
                
                # Initialize data structure
                artist_info = {
                    'id': artist_id,
                    'name': artist_name,
                    'profile': artist.profile if hasattr(artist, 'profile') else '',
                    'url': artist.url if hasattr(artist, 'url') else '',
                    'aliases': [alias.name for alias in artist.aliases] if hasattr(artist, 'aliases') else [],
                    'members': [member.name for member in artist.members] if hasattr(artist, 'members') else [],
                    'images': [img.get('resource_url') for img in artist.images] if hasattr(artist, 'images') else [],
                    'slug': sanitize_slug(artist_name)
                }
                
                # Save to database
                self.save_artist(artist_id, artist_name, artist_info)
                
            except Exception as e:
                logging.error(f"Error verifying artist {artist_name}: {str(e)}")
                return None
                
        return artist_info

    def generate_artist_page(self, artist_info, output_dir):
        """
        Generates artist page if it doesn't exist.
        Returns True if successful or page exists, False on error.
        """
        artist_name = sanitize_artist_name(artist_info['name'])
        artist_slug = artist_info['slug']
        artist_dir = os.path.join(output_dir, artist_slug)
        index_file = os.path.join(artist_dir, '_index.md')
        
        # Skip if page already exists
        if os.path.exists(index_file):
            logging.info(f"Artist page already exists for {artist_name}")
            return True
        
        try:
            # Create artist directory
            os.makedirs(artist_dir, exist_ok=True)
            
            # Get best profile text
            profile = get_best_artist_profile(artist_info)
            
            # Try to get image
            image_filename = None
            if artist_info.get('apple_music_image'):
                image_path = os.path.join(artist_dir, f"{artist_slug}.jpg")
                if download_artist_image(artist_info['apple_music_image'], image_path):
                    image_filename = f"{artist_slug}.jpg"
            if not image_filename and artist_info.get('images'):
                # Fall back to first Discogs image
                image_path = os.path.join(artist_dir, f"{artist_slug}.jpg")
                if download_artist_image(artist_info['images'][0], image_path):
                    image_filename = f"{artist_slug}.jpg"
                
            # Generate page content using template
            with open('artist_template.md', 'r') as f:
                template = Template(f.read())
                
            content = template.render(
                name=artist_name,
                profile=profile,
                image=image_filename,
                url=artist_info.get('url', ''),
                apple_music_url=artist_info.get('apple_music_url', '')
            )
            
            # Write page
            with open(index_file, 'w') as f:
                f.write(content)
                
            return True
            
        except Exception as e:
            logging.error(f"Error generating artist page for {artist_name}: {str(e)}")
            return False
