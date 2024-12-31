import streamlit as st
import sqlite3
import json
import logging
from db_handler import DatabaseHandler
import pandas as pd

# Configure logging
logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Vinyl Collection Editor",
    layout="wide"
)

# Initialize database handler with backup database
db = DatabaseHandler(db_path='collection_cache.db')

def update_release(release_id, data):
    """Update release data in the database"""
    db.save_release(release_id, data)
    st.success(f"Successfully updated release {release_id}")

def flatten_dict(d, parent_key='', sep='_'):
    """Flatten a nested dictionary"""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

# Title
st.title("Vinyl Collection Editor")

# Search box for release ID
release_id = st.text_input("Enter Release ID")

if release_id:
    try:
        release_id = int(release_id)
        logging.info(f"Fetching release {release_id}")
        release_data = db.get_release(release_id)
        
        if release_data:
            logging.info(f"Release data loaded: {json.dumps(release_data, indent=2)}")
            st.subheader("Release Information")
            
            # Create tabs for different sections
            tabs = st.tabs([
                "Basic Info", "Track List", "Formats", "Identifiers", 
                "Labels", "Videos", "Images", "Streaming", "Wiki Info", 
                "Notes & Credits", "Advanced"
            ])
            
            edited_data = release_data.copy()
            
            # Basic Info Tab
            with tabs[0]:
                st.write("Basic Information:")
                artwork_url = release_data.get('Apple Music attributes', {}).get('artwork', {}).get('url', '').replace('{w}x{h}', '1425x1425')
                if not artwork_url:
                    artwork_url = release_data.get('Album Cover URL', '')
                st.image(artwork_url, width=300)
                edited_data['Artist Name'] = st.text_input(
                    "Artist Name",
                    value=release_data.get('Artist Name', '')
                )
                edited_data['Album Title'] = st.text_input(
                    "Album Title",
                    value=release_data.get('Album Title', '')
                )
                edited_data['Release Date'] = st.number_input(
                    "Year",
                    value=int(release_data.get('Release Date', 2000)),
                    min_value=1900,
                    max_value=2100,
                    key="year"
                )
                
                # Genres
                genres = release_data.get('Genre', [])
                genres_str = ', '.join(genres) if genres else ''
                new_genres = st.text_input("Genres (comma-separated)", value=genres_str)
                edited_data['Genre'] = [g.strip() for g in new_genres.split(',') if g.strip()]
                
                # Styles
                styles = release_data.get('Style', [])
                styles_str = ', '.join(styles) if styles else ''
                new_styles = st.text_input("Styles (comma-separated)", value=styles_str)
                edited_data['Style'] = [s.strip() for s in new_styles.split(',') if s.strip()]
                
                # Label and Catalog Number
                edited_data['Label'] = st.text_input(
                    "Label",
                    value=release_data.get('Label', ''),
                    key="label"
                )
                
                edited_data['Catalog Number'] = st.text_input(
                    "Catalog Number",
                    value=release_data.get('Catalog Number', ''),
                    key="catalog_number"
                )
            
            # Track List Tab
            with tabs[1]:
                if 'Track List' in release_data:
                    tracks = release_data['Track List']
                    st.write("Track List:")
                    
                    new_tracks = []
                    for i, track in enumerate(tracks):
                        with st.expander(f"Track {track.get('number', str(i+1))}"):
                            new_track = {}
                            new_track['number'] = st.text_input("Track Number", value=track.get('number', ''), key=f"track_num_{i}")
                            new_track['title'] = st.text_input("Track Title", value=track.get('title', ''), key=f"track_title_{i}")
                            new_track['duration'] = st.text_input("Duration", value=track.get('duration', ''), key=f"track_duration_{i}")
                            if new_track['title']:  # Only add if title exists
                                new_tracks.append(new_track)
                    
                    edited_data['Track List'] = new_tracks

            # Formats Tab
            with tabs[2]:
                if 'Release Formats' in release_data:
                    formats = release_data['Release Formats']
                    st.write("Formats:")
                    new_formats = []
                    for i, fmt in enumerate(formats):
                        with st.expander(f"Format {i+1}"):
                            new_format = {}
                            new_format['name'] = st.text_input("Format Name", value=fmt.get('name', ''), key=f"fmt_name_{i}")
                            if 'descriptions' in fmt:
                                desc_str = ', '.join(fmt['descriptions'])
                                new_desc = st.text_input("Descriptions (comma-separated)", value=desc_str, key=f"fmt_desc_{i}")
                                new_format['descriptions'] = [d.strip() for d in new_desc.split(',') if d.strip()]
                            new_formats.append(new_format)
                    edited_data['Release Formats'] = new_formats

            # Identifiers Tab
            with tabs[3]:
                if 'Identifiers' in release_data:
                    identifiers = release_data['Identifiers']
                    st.write("Identifiers:")
                    new_identifiers = []
                    for i, ident in enumerate(identifiers):
                        with st.expander(f"Identifier {i+1}"):
                            new_identifier = {}
                            new_identifier['type'] = st.text_input("Type", value=ident.get('type', ''), key=f"id_type_{i}")
                            new_identifier['value'] = st.text_input("Value", value=ident.get('value', ''), key=f"id_value_{i}")
                            if new_identifier['type'] and new_identifier['value']:
                                new_identifiers.append(new_identifier)
                    edited_data['Identifiers'] = new_identifiers

            # Labels Tab
            with tabs[4]:
                if 'Label' in release_data:
                    labels = release_data['Label']
                    if isinstance(labels, str):
                        labels = [{'name': labels}]
                    elif not isinstance(labels, list):
                        labels = []
                    
                    st.write("Labels:")
                    new_labels = []
                    for i, label in enumerate(labels):
                        with st.expander(f"Label {i+1}"):
                            new_label = {}
                            if isinstance(label, str):
                                new_label['name'] = st.text_input("Label Name", value=label, key=f"label_name_{i}")
                            else:
                                new_label['name'] = st.text_input("Label Name", value=label.get('name', ''), key=f"label_name_{i}")
                                new_label['catno'] = st.text_input("Catalog Number", value=label.get('catno', ''), key=f"label_catno_{i}")
                            if new_label['name']:
                                new_labels.append(new_label)
                    
                    edited_data['Label'] = new_labels

            # Videos Tab
            with tabs[5]:
                if 'Videos' in release_data:
                    videos = release_data['Videos']
                    st.write("Videos:")
                    
                    new_videos = []
                    for i, video in enumerate(videos):
                        with st.expander(f"Video {i+1}"):
                            new_video = {}
                            new_video['title'] = st.text_input("Video Title", value=video.get('title', ''), key=f"video_title_{i}")
                            new_video['url'] = st.text_input("Video URL", value=video.get('url', ''), key=f"video_url_{i}")
                            if new_video['url']:  # Only add if URL exists
                                new_videos.append(new_video)
                                
                                # Show video preview if it's YouTube
                                if 'youtube.com' in new_video['url']:
                                    st.video(new_video['url'])
                    
                    edited_data['Videos'] = new_videos

            # Images Tab
            with tabs[6]:
                if 'All Images URLs' in release_data:
                    images = release_data['All Images URLs']
                    st.write("Album Images:")
                    cols = st.columns(3)
                    for i, img_url in enumerate(images):
                        with cols[i % 3]:
                            st.image(img_url, caption=f"Image {i+1}", width=500, use_container_width=False)

            # Streaming Tab
            with tabs[7]:
                st.write("Apple Music Information:")
                edited_data['Apple Music ID'] = st.text_input("Apple Music ID", value=release_data.get('Apple Music id', ''))
                edited_data['Apple Music Type'] = st.text_input("Type", value=release_data.get('Apple Music type', ''))
                edited_data['Apple Music URL'] = st.text_input("URL", value=release_data.get('Apple Music attributes', {}).get('url', ''))
                edited_data['Apple Music Release Date'] = st.date_input("Release Date", value=pd.to_datetime(release_data.get('Apple Music attributes', {}).get('releaseDate', '')))
                edited_data['Apple Music Record Label'] = st.text_input("Record Label", value=release_data.get('Apple Music attributes', {}).get('recordLabel', ''))
                edited_data['Apple Music Genre Names'] = st.text_area("Genre Names", value=", ".join(release_data.get('Apple Music attributes', {}).get('genreNames', [])), height=100)
                st.write("Apple Music Artwork:")
                edited_data['Apple Music Artwork URL'] = st.text_input("Artwork URL", value=release_data.get('Apple Music attributes', {}).get('artwork', {}).get('url', '').replace('{w}x{h}', '1425x1425'))
                st.write("Artwork Dimensions:")
                st.text(f"Width: {release_data.get('Apple Music attributes', {}).get('artwork', {}).get('width', '')}")
                st.text(f"Height: {release_data.get('Apple Music attributes', {}).get('artwork', {}).get('height', '')}")
                st.write("Artwork Colors:")
                st.text(f"Background Color: {release_data.get('Apple Music attributes', {}).get('artwork', {}).get('bgColor', '')}")
                st.text(f"Text Color 1: {release_data.get('Apple Music attributes', {}).get('artwork', {}).get('textColor1', '')}")
                st.text(f"Text Color 2: {release_data.get('Apple Music attributes', {}).get('artwork', {}).get('textColor2', '')}")
                st.text(f"Text Color 3: {release_data.get('Apple Music attributes', {}).get('artwork', {}).get('textColor3', '')}")
                st.text(f"Text Color 4: {release_data.get('Apple Music attributes', {}).get('artwork', {}).get('textColor4', '')}")
                # Additional Apple Music attributes
                edited_data['Apple Music Attributes URL'] = st.text_input("Apple Music Attributes URL", value=release_data.get('Apple Music attributes', {}).get('url', ''))
                edited_data['Apple Music Attributes Artwork URL'] = st.text_input(
                    "Apple Music Attributes Artwork URL",
                    value=release_data.get('Apple Music attributes', {}).get('artwork', {}).get('url', '')
                )
                st.write("Spotify Info:")
                edited_data['Spotify ID'] = st.text_input("Spotify ID", value=release_data.get('Spotify ID', ''))

            # Wiki Info Tab
            with tabs[8]:
                st.write("Wikipedia Information:")
                edited_data['Wikipedia URL'] = st.text_input(
                    "Wikipedia URL",
                    value=release_data.get('Wikipedia URL', '')
                )
                edited_data['Wikipedia Summary'] = st.text_area(
                    "Wikipedia Summary",
                    value=release_data.get('Wikipedia Summary', ''),
                    height=200
                )

            # Notes & Credits Tab
            with tabs[9]:
                st.write("Notes & Credits:")
                edited_data['Notes'] = st.text_area(
                    "Notes",
                    value=release_data.get('Notes', ''),
                    height=150
                )
                edited_data['Credits'] = st.text_area(
                    "Credits",
                    value=release_data.get('Credits', ''),
                    height=150
                )

            # Advanced Tab
            with tabs[10]:
                st.write("Advanced Information:")
                st.json(release_data, expanded=False)
                
                # Add a text area for editing JSON data
                json_data = st.text_area("Edit Release Information", json.dumps(release_data, indent=4), height=400)

                # Update the release data if changes are made
                try:
                    updated_data = json.loads(json_data)
                    if updated_data != release_data:
                        db.save_release(release_id, updated_data)
                        st.success("Release information updated successfully.")
                except json.JSONDecodeError:
                    st.error("Invalid JSON format. Please correct it and try again.")
            
            # Save Changes button (outside tabs)
            if st.button("Save Changes"):
                try:
                    # Convert date to string for JSON serialization
                    edited_data['Apple Music Release Date'] = edited_data['Apple Music Release Date'].strftime('%Y-%m-%d')
                    update_release(release_id, edited_data)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving changes: {str(e)}")
                
        else:
            st.warning(f"No release found with ID {release_id}")
            
    except ValueError:
        st.error("Please enter a valid release ID (numbers only)")
