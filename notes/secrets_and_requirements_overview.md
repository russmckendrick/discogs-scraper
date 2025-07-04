# Configuration & Dependencies Overview

## secrets.json.example - API Configuration

### Purpose
The `secrets.json.example` file serves as a template for the required API credentials and configuration needed to access external music services. This file demonstrates the expected structure for authentication tokens and service identifiers.

### Required Credentials

#### Discogs API Access
```json
{
    "discogs_access_token": "put_your_discogs_access_token_here",
    "discogs_username": "username_of_the_collection_owner"
}
```

**Purpose**: 
- **discogs_access_token**: Personal access token for Discogs API authentication
- **discogs_username**: Username of the collection owner (currently defined but not actively used in the codebase)

**How to Obtain**:
1. Create a Discogs account
2. Navigate to Settings → Developers
3. Generate a personal access token
4. Token provides access to user's collection data

**API Capabilities**:
- Access personal record collection
- Retrieve detailed release information
- Get artist data and discographies
- Download album artwork and metadata

#### Spotify Web API
```json
{
    "spotify_client_id": "put_your_spotify_client_id_here",
    "spotify_client_secret": "put_your_spotify_client_secret_here"
}
```

**Purpose**: Client credentials for Spotify Web API integration

**How to Obtain**:
1. Create Spotify Developer account
2. Create a new application in Spotify Dashboard
3. Copy Client ID and Client Secret from app settings
4. Used for Client Credentials Flow (app-only authentication)

**API Capabilities**:
- Search for albums and artists
- Retrieve Spotify album IDs
- Generate streaming links for releases
- Access public music catalog data

#### Apple Music API
```json
{
    "apple_music_client_id": "put_your_apple_music_key_id_here",
    "apple_developer_team_id": "put_your_apple_music_team_id_here"
}
```

**Purpose**: Developer credentials for Apple Music API JWT token generation

**How to Obtain**:
1. Enroll in Apple Developer Program ($99/year)
2. Create MusicKit identifier in Developer Console
3. Generate private key (.p8 file) - stored separately in `backups/apple_private_key.p8`
4. Note Key ID and Team ID from developer account

**API Capabilities**:
- Search Apple Music catalog
- Retrieve high-resolution album artwork (2000x2000px)
- Access editorial notes and release information
- Get streaming URLs and metadata

### Security Considerations

#### File Handling
- **Example file**: Checked into version control as template
- **Actual secrets**: Must be in `.secrets.json` (gitignored)
- **Key file storage**: Private key stored in `backups/` directory
- **Token lifecycle**: Apple Music tokens expire after 12 hours (auto-regenerated)

#### Access Patterns
- **Read-only operations**: All APIs used for data retrieval only
- **Rate limiting**: All services implement request throttling
- **Error handling**: Graceful degradation when services unavailable
- **Offline mode**: Core functionality works without external APIs

---

## requirements.txt - Python Dependencies

### Core Music Industry APIs
```
python3-discogs-client
```
**Purpose**: Official Python client for Discogs API
- **Functionality**: Collection access, release data, artist information
- **Rate limiting**: Built-in request throttling
- **Authentication**: Personal access token support

### HTTP & Web Frameworks
```
requests
Flask>=2.0.0
```
**requests**: HTTP client for API communications
- **Usage**: Apple Music, Spotify, Wikipedia API calls
- **Features**: Session management, timeout handling, retry logic

**Flask**: Web framework for database management interface
- **Usage**: CRUD operations on cached data
- **Features**: Template rendering, form handling, session management

### Authentication & Security
```
PyJWT
cryptography
```
**PyJWT**: JSON Web Token handling for Apple Music API
- **Algorithm**: ES256 signature validation
- **Token generation**: Automated JWT creation with expiration

**cryptography**: Cryptographic operations for JWT signing
- **Key handling**: ES256 private key operations
- **Security**: Secure token generation for Apple Music

### Data Processing & Templates
```
jinja2
```
**Purpose**: Template engine for markdown file generation
- **Templates**: Album and artist page generation
- **Features**: Variable substitution, conditional logic, filters
- **Output**: Hugo-compatible markdown with YAML frontmatter

### External Knowledge APIs
```
wikipedia
```
**Purpose**: Artist biographical information retrieval
- **Functionality**: Summary extraction, URL generation
- **Fallback**: Graceful handling when articles not found
- **Language**: English Wikipedia primary target

### User Interface & Progress
```
tqdm
```
**Purpose**: Progress bar visualization for long-running operations
- **Usage**: Collection processing progress
- **Features**: ETA calculation, rate display, customizable output
- **Integration**: Console and log file output

### Error Handling & Reliability
```
tenacity
```
**Purpose**: Retry logic for unreliable operations
- **Usage**: API call retries, download operations
- **Strategies**: Exponential backoff, maximum attempts
- **Logging**: Retry attempt tracking

### Content Processing
```
html2text==2024.2.26
```
**Purpose**: HTML to markdown conversion
- **Usage**: Apple Music editorial notes processing
- **Version pinned**: Ensures consistent output format
- **Features**: Clean markdown generation from HTML content

### Dependency Analysis

#### API Integration Stack
- **Primary**: discogs_client (core functionality)
- **Secondary**: requests (multi-service support)
- **Authentication**: PyJWT + cryptography (secure access)

#### Data Processing Pipeline
- **Input**: JSON from various APIs
- **Processing**: jinja2 templates + html2text conversion
- **Output**: Markdown files for static site generation

#### User Experience
- **Progress**: tqdm for visual feedback
- **Reliability**: tenacity for error recovery
- **Management**: Flask web interface for data administration

#### Version Considerations
- **Flask**: Minimum 2.0.0 for modern features
- **html2text**: Pinned version for consistency
- **Others**: Latest compatible versions for security updates

### Installation & Environment

#### Virtual Environment Setup
```bash
python -m venv venv
source venv/bin/activate  # Unix/macOS
pip install -r requirements.txt
```

#### Development Dependencies
- **Missing**: Testing framework (pytest recommended)
- **Missing**: Code formatting (black, flake8 recommended)
- **Missing**: Type checking (mypy recommended)

### Refactoring Considerations

#### Dependency Management
1. **Add development dependencies**: Testing, linting, formatting tools
2. **Pin more versions**: Ensure reproducible builds
3. **Dependency groups**: Separate dev/test/prod requirements
4. **Security scanning**: Regular vulnerability checks

#### Architecture Improvements
1. **Service abstraction**: Wrapper classes for each API client
2. **Configuration management**: Environment-based settings
3. **Async support**: Consider httpx for async HTTP operations
4. **Caching layer**: Redis or similar for API response caching

#### Security Enhancements
1. **Environment variables**: Move secrets to environment
2. **Key rotation**: Support for credential updates
3. **Token management**: Centralized token lifecycle
4. **Rate limit coordination**: Shared rate limiting across services 