#!/usr/bin/env python3

import os
import re
import logging
from datetime import datetime

# Setup logging
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

log_file = f"{log_dir}/apple_music_url_update_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)

# Directory with album folders
albums_dir = "website/content/albums"

# Regular expression to extract Apple Music URL from content
apple_music_regex = r'{{\s*<\s*applemusic\s+url="([^"]+)"\s*>\s*}}'

# Count statistics
total_files = 0
updated_files = 0
already_has_field = 0
no_url_found = 0

logging.info("Starting to process album index.md files")

# Iterate through album directories
for album_dir in os.listdir(albums_dir):
    album_path = os.path.join(albums_dir, album_dir)
    
    # Skip if not a directory
    if not os.path.isdir(album_path):
        continue
    
    index_file = os.path.join(album_path, "index.md")
    
    # Skip if index.md doesn't exist
    if not os.path.exists(index_file):
        logging.warning(f"No index.md found in {album_dir}")
        continue
    
    total_files += 1
    logging.info(f"Processing {index_file}")
    
    # Read the file content
    with open(index_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Check if apple_music_url already exists in frontmatter
    if re.search(r'^apple_music_url:', content, re.MULTILINE):
        logging.info(f"  Already has apple_music_url field: {album_dir}")
        already_has_field += 1
        continue
    
    # Find the frontmatter section (between --- and ---)
    frontmatter_match = re.search(r'^---\s+(.*?)\s+---', content, re.DOTALL | re.MULTILINE)
    if not frontmatter_match:
        logging.warning(f"  Could not find frontmatter in {album_dir}/index.md")
        continue
    
    frontmatter = frontmatter_match.group(1)
    frontmatter_end = frontmatter_match.end()
    
    # Try to extract Apple Music URL from content
    apple_music_match = re.search(apple_music_regex, content)
    apple_music_url = apple_music_match.group(1) if apple_music_match else ""
    
    if not apple_music_url:
        logging.info(f"  No Apple Music URL found in {album_dir}")
        no_url_found += 1
    
    # Find the position to insert the apple_music_url line
    # We'll insert after release_id line
    release_id_match = re.search(r'^release_id:', frontmatter, re.MULTILINE)
    
    if release_id_match:
        # Insert after release_id line
        insert_pos = release_id_match.end()
        
        # Find the end of the line
        newline_pos = frontmatter.find('\n', insert_pos)
        if newline_pos != -1:
            insert_pos = newline_pos + 1
        
        # Insert the apple_music_url line
        new_frontmatter = (
            frontmatter[:insert_pos] + 
            f'apple_music_url: "{apple_music_url}"\n' + 
            frontmatter[insert_pos:]
        )
        
        # Reconstruct the file content
        new_content = content[:frontmatter_match.start(1)] + new_frontmatter + content[frontmatter_match.end(1):]
        
        # Write the updated content back
        with open(index_file, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        updated_files += 1
        logging.info(f"  Updated {album_dir}/index.md with Apple Music URL: {apple_music_url}")
    else:
        logging.warning(f"  Could not find release_id field in {album_dir}/index.md")

logging.info(f"Finished processing files")
logging.info(f"Total files processed: {total_files}")
logging.info(f"Files already with apple_music_url: {already_has_field}")
logging.info(f"Files updated: {updated_files}")
logging.info(f"Files with no Apple Music URL found: {no_url_found}") 