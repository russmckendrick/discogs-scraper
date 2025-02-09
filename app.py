import os
import shutil
import json
from datetime import datetime
import logging
import argparse

from flask import Flask, render_template, request, redirect, url_for, flash
from db_handler import DatabaseHandler

# Parse command line arguments
parser = argparse.ArgumentParser(description='Run the Vinyl Collection Manager web application')
parser.add_argument('--debug-data', action='store_true', help='Enable data debugging output')
args = parser.parse_args()

# Ensure necessary directories exist
for folder in ['logs', 'backups']:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Configure logging: logs are stored in logs/log_<timestamp>.log
log_filename = os.path.join('logs', f'log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Backup the database file on launch
DB_PATH = 'collection_cache.db'
if os.path.exists(DB_PATH):
    backup_filename = os.path.join('backups', f'collection_cache_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    shutil.copy(DB_PATH, backup_filename)
    logger.info(f"Database backed up to {backup_filename}")
else:
    logger.error(f"Database file {DB_PATH} does not exist.")

# Initialize the DatabaseHandler
db = DatabaseHandler(db_path=DB_PATH)

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Adjust for your local environment

# Register a custom template filter to parse JSON strings.
@app.template_filter('load_json')
def load_json_filter(s):
    try:
        return json.loads(s)
    except Exception:
        return {}

# Helper function to filter and sort releases
def get_releases(query=None, sort_key=None):
    releases = db.get_all_releases()
    if args.debug_data:
        logger.info(f"Raw releases type: {type(releases)}")
        if releases:
            logger.info(f"First release: {json.dumps(next(iter(releases)) if isinstance(releases, (list, set, dict)) else releases, indent=2)}")
    
    # Convert release data to list if not already
    if not isinstance(releases, list):
        releases = list(releases)
    
    # Ensure every item is a dictionary and contains the full release data
    processed_releases = []
    for r in releases:
        if isinstance(r, int):
            # If we only got an ID, fetch the full release data
            full_release = db.get_release(r)
            if full_release:
                processed_releases.append(full_release)
            else:
                processed_releases.append({"Release ID": r})
        elif isinstance(r, dict):
            processed_releases.append(r)
        else:
            processed_releases.append({})
    
    if args.debug_data:
        logger.info(f"Processed releases count: {len(processed_releases)}")
        if processed_releases:
            logger.info(f"First processed release: {json.dumps(processed_releases[0], indent=2)}")
    
    # Filter by query if provided
    if query:
        query_lower = query.lower()
        processed_releases = [
            r for r in processed_releases
            if (r.get("Artist Name", "").lower().find(query_lower) != -1 or 
                r.get("Album Title", "").lower().find(query_lower) != -1)
        ]
    
    # Default sorting: use Date Added descending if no sort_key provided.
    if not sort_key:
        sort_key = "Date Added"
    if sort_key == "Date Added":
        def parse_date(date_str):
            try:
                return datetime.fromisoformat(date_str)
            except Exception:
                return datetime.min
        processed_releases.sort(key=lambda r: parse_date(r.get("Date Added", "1970-01-01T00:00:00")), reverse=True)
    else:
        processed_releases.sort(key=lambda r: r.get(sort_key, ""))
    
    return processed_releases

@app.route("/")
def index():
    query = request.args.get('q', '')
    sort_key = request.args.get('sort', '')
    releases = get_releases(query=query, sort_key=sort_key)
    return render_template("index.html", releases=releases, query=query, sort_key=sort_key, args=args)

@app.route("/release/new", methods=["GET", "POST"])
def new_release():
    if request.method == "POST":
        try:
            # Expecting release JSON text from the form
            release_json = request.form.get("release_json", "{}")
            release_data = json.loads(release_json)
            # Use a provided id or generate one (if your schema allows auto-assignment, adjust accordingly)
            release_id = int(request.form.get("release_id", "0"))
            if release_id == 0:
                flash("Please provide a valid Release ID for the new record.", "danger")
                return redirect(url_for("new_release"))
            db.save_release(release_id, release_data)
            logger.info(f"Created new release with ID {release_id}")
            flash(f"Release {release_id} created successfully.", "success")
            return redirect(url_for("index"))
        except Exception as e:
            logger.error(f"Error creating release: {str(e)}")
            flash(f"Error creating release: {str(e)}", "danger")
            return redirect(url_for("new_release"))
    # GET request – show an empty form
    return render_template("release_detail.html", release={}, is_new=True)

@app.route("/release/<int:release_id>", methods=["GET", "POST"])
def release_detail(release_id):
    if request.method == "POST":
        try:
            release_json = request.form.get("release_json", "{}")
            release_data = json.loads(release_json)
            db.save_release(release_id, release_data)
            logger.info(f"Updated release {release_id}")
            flash(f"Release {release_id} updated successfully.", "success")
            return redirect(url_for("release_detail", release_id=release_id))
        except Exception as e:
            logger.error(f"Error updating release {release_id}: {str(e)}")
            flash(f"Error updating release {release_id}: {str(e)}", "danger")
            return redirect(url_for("release_detail", release_id=release_id))
    # GET: load release data and display
    release_data = db.get_release(release_id)
    if not release_data:
        flash(f"No release found with ID {release_id}.", "warning")
        return redirect(url_for("index"))
    # Pretty-format JSON for the textarea (indentation)
    release_pretty = json.dumps(release_data, indent=4, ensure_ascii=False)
    return render_template("release_detail.html", release=release_pretty, release_id=release_id, is_new=False)

@app.route("/release/<int:release_id>/delete", methods=["POST"])
def delete_release(release_id):
    try:
        # A simple delete implementation. Adjust if your DatabaseHandler has a dedicated delete.
        # Here we simply set the release to an empty dict or remove it.
        # Assuming your DatabaseHandler manages deletion via a method; if not, you may need to execute a DELETE SQL.
        # For this example, we simulate deletion by saving an empty record.
        db.save_release(release_id, {})
        logger.info(f"Deleted release {release_id}")
        flash(f"Release {release_id} deleted successfully.", "success")
    except Exception as e:
        logger.error(f"Error deleting release {release_id}: {str(e)}")
        flash(f"Error deleting release {release_id}: {str(e)}", "danger")
    return redirect(url_for("index"))

if __name__ == "__main__":
    # Run the Flask development server locally.
    app.run(debug=True) 