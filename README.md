# Discogs Scraper 🎵

A basic scraper for generating files for [https://www.mckendrick.rocks/](https://www.mckendrick.rocks/) 🎸.

While this was initially created for personal use, feel free to use it if you find it helpful! 😃 Although the documentation is minimal, the code is fairly straightforward.

## Getting Started 🚀

1. Clone the repository to your local machine.
2. Install the required dependencies using `pip install -r requirements.txt`.
3. Run the `discogs_scraper.py` script to start the scraper.

## Configuration ⚙️

To customize the scraper for your needs, create a copy of the `secrets.json.example` file calling it `secrets.json` and file in the details.

## How it Works 🛠

The scraper fetches data from the Discogs API and processes the information to generate markdown files and download images. This data can then be used to create a static site showcasing your music collection 🎧.

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
