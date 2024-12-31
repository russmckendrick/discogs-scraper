import sqlite3
from pathlib import Path
import json
import logging

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
