# Discogs Scraper 🎵

A Python application for managing a vinyl record collection, generating content for [https://www.russ.fm/](https://www.russ.fm/) 🎸. While initially created for personal use, feel free to use it if you find it helpful! The site is powered by [Hugo](https://gohugo.io/) and you can find the website files and config at [russmckendrick/records](https://github.com/russmckendrick/records/).

## Features ✨

### Data Collection
- Fetches collection data from Discogs API
- Enriches data with information from:
  - Apple Music API
  - Spotify API
  - Wikipedia API
- Downloads and processes album artwork and artist images
- Caches data in SQLite database to avoid rate limiting

### Web Interface
The Flask-based web interface provides:

#### Core Features
- Traditional multi-page layout with Bootstrap styling
- Database backup on application launch (timestamped copies in `backups/` folder)
- Comprehensive logging to dated files in `logs/` directory

#### Release Management
- Full CRUD operations for releases
- Searchable and sortable release listing
- Rich preview with album artwork, track listings, and metadata
- Links to external services (Discogs, Apple Music, Spotify)
- Default sorting by Date Added (newest first)

#### Artist Management
- Full CRUD operations for artists
- Searchable artist listing (by ID, name, or slug)
- Rich preview showing artist images, bio, and related information
- Integration with Apple Music, Discogs, and Wikipedia data

#### Editor Features
- CodeMirror-based JSON editor with:
  - Syntax highlighting
  - Real-time validation
  - Auto-formatting
  - Error highlighting
  - Line numbers and bracket matching
- Preview-first layout with collapsible raw data view

## Getting Started 🚀

1. Clone the repository
2. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `secrets.json.example` to `secrets.json` and fill in your API credentials:
   - Discogs access token
   - Spotify client ID and secret
   - Apple Music client ID and team ID
   - Apple Music private key (place in `backups/apple_private_key.p8`)

## Running the Application 🏃‍♂️

### Web Interface
Start the Flask web application:
```bash
python app.py
```

Add `--debug-data` flag to enable detailed debugging output:
```bash
python app.py --debug-data
```

### Discogs Scraper
The scraper supports various modes:

```bash
# Process just 10 releases (default)
python discogs_scraper.py

# Process all releases
python discogs_scraper.py --all

# Process specific number of releases
python discogs_scraper.py --num-items 100

# Adjust request delay (default: 2 seconds)
python discogs_scraper.py --delay 1

# Regenerate artist pages only
python discogs_scraper.py --artists-only

# Regenerate specific artist
python discogs_scraper.py --regenerate-artist "Artist Name"

# Migrate artist data
python discogs_scraper.py --migrate-artists
```

## Project Structure 📁

- `app.py` - Flask web application
- `discogs_scraper.py` - Main scraper script
- `db_handler.py` - Database operations
- `utils.py` - Shared utility functions
- `templates/` - Flask HTML templates
- `logs/` - Application logs
- `backups/` - Database backups
- `website/` - Generated Hugo content

## Useful Links 🔗

- [JSON Lint](https://jsonlint.com/)
- [JSON Formatter](https://www.text-utils.com/json-formatter/)
- [Apple Media Services Tools](https://tools.applemediaservices.com/?country=gb)

## One More Thing... 🤖

This project was initially developed with assistance from ChatGPT 💬, with subsequent debugging 🐛 and feature additions. 🤓

## Contributing 🤝

Feel free to submit issues and pull requests. The project uses comprehensive logging and maintains a structured approach to data handling.