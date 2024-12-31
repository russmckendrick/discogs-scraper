# Discogs Scraper 🎵

A basic scraper for generating files for [https://www.russ.fm/](https://www.russ.fm/) 🎸. While this was initially created for personal use, feel free to use it if you find it helpful! 😃 Although the documentation is minimal, the code is fairly straightforward.

You can find the repo containing the website files and config at [russmckendrick/records](https://github.com/russmckendrick/records/), it's a [Hugo-powered](https://gohugo.io/) site and there are ALOT of files.

## Getting Started 🚀

1. Clone the repository to your local machine.
2. Install the required dependencies using `pip install -r requirements.txt`.
3. Run the `discogs_scraper.py` script to start the scraper.

## Configuration ⚙️

To customize the scraper for your needs, create a copy of the `secrets.json.example` file calling it `secrets.json` and file in the details.

## How it Works 🛠

The scraper fetches data from the Discogs API and processes the information to generate markdown files and download images. This data can then be used to create a static site showcasing your music collection 🎧.

## New Features ✨

- **Discogs Scraper Enhancements:**
  - Integration with Apple Music and Spotify APIs for richer music data. 🎵
  - Wikipedia data retrieval for artist information. 📚
  - Automatic generation of markdown files for albums and artists. 📄

## Collection Editor 🛠️

The `collection_editor.py` script allows you to manage and edit your music collection data stored in the database. Perfect for maintaining an up-to-date record of your music library. 🎶

## Running the Collection Editor 🖥️

To run the `collection_editor.py` script, follow these steps:

1. **Ensure Dependencies are Installed:**
   - Install the required packages using the `requirements.txt` file.

2. **Run the Streamlit App:**
   - Execute the following command to start the app:
     ```bash
     streamlit run collection_editor.py
     ```

3. **Access the Application:**
   - Open your web browser and navigate to the URL provided by Streamlit, typically `http://localhost:8501`.

4. **Using the Application:**
   - Enter a Release ID in the search box to fetch and edit release data.
   - Make changes and click "Save Changes" to update the database.

## Running the Scraper 🏃‍♂️

The scraper can be run using the following commands:

To process just 10 releases every 2 seconds run the script without any flags;

```bash
$ python3 discogs_scraper.py
```

You can add the `--all` flag to process all releases in your collection;

```bash
$ python3 discogs_scraper.py --all
```

You can also add the `--num-items` flag to process a specific number of releases;

```bash
$ python3 discogs_scraper.py --num-items 100
```

Finally, you can override the default 2 second delay between requests using the `--delay` flag, this is not recommended as it may cause issues with the Discogs API so be careful;

```bash
$ python3 discogs_scraper.py --delay 0
```

You can also combine the flags to process a specific number of releases without any delay;

```bash
$ python3 discogs_scraper.py --all --delay 0
```

## Contribution 🤝

If you'd like to contribute or suggest improvements, feel free to submit a pull request or open an issue on GitHub. We appreciate your input! 🌟

Enjoy scraping and building your music collection website! 🎶

## One More Thing... 🤖

Oh yeah, it was mostly written by ChapGPT 💬 with me debugging 🐛 it and adding some features. 🤓

## Some random links

For when reviewing the wrong matches and you need to move a release to the `collection_cache_overrides.json` file from your `collection_cache.json` file.

- [https://jsonlint.com/](https://jsonlint.com/)
- [https://www.text-utils.com/json-formatter/](https://www.text-utils.com/json-formatter/)
- [https://tools.applemediaservices.com/?country=gb](https://tools.applemediaservices.com/?country=gb)