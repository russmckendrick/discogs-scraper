# Discogs Scraper Overview

## Purpose
The `discogs_scraper.py` is the core data collection engine of the vinyl collection management system. It orchestrates the extraction, enrichment, and storage of music release data from multiple APIs (Discogs, Apple Music, Spotify, Wikipedia) while managing artist information and generating static website content.

## Architecture Overview

### Core Components
1. **API Integration Layer** - Handles authentication and data retrieval from external services
2. **Data Processing Engine** - Transforms and enriches raw API data
3. **Database Management** - Caches data and tracks processing progress
4. **Content Generation** - Creates markdown files for static website
5. **Progress Tracking** - Database-based resume capability for large collections

### Key Dependencies
- `discogs_client` - Official Discogs API client
- `jwt` - Apple Music API authentication
- `requests` - HTTP client for API calls
- `wikipedia` - Wikipedia API integration
- `tqdm` - Progress bar visualization
- `jinja2` - Template rendering for markdown generation
- `tenacity` - Retry logic for failed operations

## Main Functions & Workflow

### 1. Authentication & Token Management
```python
generate_apple_music_token(private_key_path, key_id, team_id)
verify_apple_music_token(token)
```
- Generates JWT tokens for Apple Music API using ES256 algorithm
- Validates tokens before processing begins
- Uses private key file from Apple Developer account

### 2. Data Retrieval Functions
```python
get_apple_music_data(search_type, query, token)
get_artist_info(artist_name, discogs_client)
```
- **Apple Music**: Searches for albums/artists with fuzzy matching
- **Discogs**: Retrieves detailed release and artist information
- **Spotify**: Gets album IDs for streaming links (via utils)
- **Wikipedia**: Fetches artist biographies and summaries (via utils)

### 3. Core Processing Pipeline
```python
process_item(item, db_handler, tokens...) -> item_data
```

**Workflow per release:**
1. Extract basic release data from Discogs
2. Check database cache to avoid re-processing
3. Enrich with Apple Music data (album artwork, editorial notes)
4. Add Spotify integration for streaming links
5. Download high-resolution album artwork
6. Generate markdown file using Jinja2 templates
7. Cache processed data in SQLite database

### 4. Artist Management
```python
create_artist_markdown_file(artist_data, output_dir)
```
- Processes artist information separately from releases
- Downloads artist images and creates dedicated pages
- Integrates Wikipedia biographies when available
- Handles artist aliases and band member information

### 5. Progress Management
- **Database-driven tracking**: Uses `processed_index` table instead of file-based system
- **Resume capability**: Can restart from last processed item
- **Error resilience**: Continues processing even when individual items fail

## Data Flow Architecture

```
Discogs Collection → Rate-Limited API Calls → Data Enrichment → Database Cache → Markdown Generation
                                ↓
                    Apple Music + Spotify + Wikipedia APIs
                                ↓
                          Image Downloads
                                ↓
                        Static Website Content
```

## Command Line Interface

### Available Modes
- `--all`: Process entire collection from scratch
- `--artists-only`: Regenerate only artist pages
- `--migrate-artists`: Move artist data from releases to dedicated table
- `--regenerate-artist <name>`: Rebuild specific artist page
- `--overwrite-album`: Force update existing album pages
- `--delay <seconds>`: Configure API request throttling

### Rate Limiting Strategy
- **Discogs**: 2-second delays between requests with 429 handling
- **Collection pagination**: 2-second delays between page requests
- **Configurable delays**: Default 10 seconds, adjustable via CLI
- **Retry logic**: Automatic retry on rate limit hits

## Database Integration

### Core Tables Used
- `releases`: Cached release data with enriched metadata
- `artists`: Dedicated artist information storage
- `skip_releases`: User-defined exclusion list
- `processed_index`: Progress tracking for resumable processing

### Caching Strategy
- **First-level cache**: Database lookup before API calls
- **Incremental processing**: Only new/missing data fetched
- **Data persistence**: Survives application restarts
- **Conflict resolution**: Database data takes precedence

## Output Generation

### Markdown Templates
- **Album pages**: `album_template.md` via Jinja2
- **Artist pages**: `artist_template.md` via Jinja2
- **Hugo-compatible**: Static site generator ready
- **Rich metadata**: YAML frontmatter with structured data

### Image Management
- **High-resolution preference**: Apple Music 2000x2000px artwork
- **Fallback strategy**: Discogs → Missing image placeholder
- **Local storage**: Downloaded to album/artist directories
- **Consistent naming**: Slug-based filenames

## Error Handling & Logging

### Comprehensive Logging
- **Timestamped log files**: `logs/log_YYYYMMDD_HHMMSS.log`
- **Detailed API interactions**: Request/response logging
- **Progress tracking**: Item-by-item processing status
- **Error context**: Full stack traces for debugging

### Resilience Features
- **Skip problematic releases**: Maintains processing momentum
- **API failure handling**: Graceful degradation when services unavailable
- **Missing data tolerance**: Continues with partial information
- **Resume capability**: No work lost on interruption

## Integration Points

### External Dependencies
- **Discogs API**: Core music database (rate limited)
- **Apple Music API**: High-quality artwork and editorial content
- **Spotify Web API**: Streaming service integration
- **Wikipedia API**: Artist biographical information

### Internal Dependencies
- **DatabaseHandler**: SQLite operations and schema management
- **Utils module**: Shared helper functions and utilities
- **Template system**: Jinja2 templates for content generation

## Performance Characteristics

### Processing Speed
- **Rate limited by APIs**: ~2-10 seconds per release
- **Batch processing**: Handles collections of 1000+ releases
- **Progress persistence**: No restart penalty
- **Parallel opportunities**: Limited by API rate limits

### Resource Usage
- **Memory efficient**: Processes items individually
- **Disk space**: Grows with collection size (images + metadata)
- **Network intensive**: Multiple API calls per release
- **CPU light**: Mostly I/O bound operations

## Refactoring Considerations

### Current Pain Points
1. **Monolithic structure**: Single large file handles multiple concerns
2. **Mixed responsibilities**: API, processing, and generation in one place
3. **Duplicate functions**: Some utilities replicated across modules
4. **Configuration scattered**: Settings mixed with constants
5. **Limited error recovery**: Basic retry logic

### Improvement Opportunities
1. **Service separation**: Split API clients into dedicated modules
2. **Configuration management**: Centralized settings system
3. **Enhanced error handling**: More sophisticated retry strategies
4. **Async processing**: Parallel API calls where possible
5. **Plugin architecture**: Extensible API integrations
6. **Metrics collection**: Processing statistics and performance monitoring

### Architecture Recommendations
- **Service layer**: Separate API clients (DiscogsService, AppleMusicService, etc.)
- **Orchestration layer**: Coordinate services and manage workflow
- **Repository pattern**: Abstract database operations
- **Command pattern**: Better CLI command handling
- **Observer pattern**: Progress reporting and logging 