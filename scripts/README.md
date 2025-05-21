# Album Cover Downloader

This script downloads album cover images from Spotify for albums listed in `_data/albumsilike.csv`.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up Spotify API credentials:

   You'll need to get your Spotify API credentials from the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).

   Then, set the credentials as environment variables. You can do this in one of two ways:

   **Option 1: Set environment variables in your terminal**
   ```bash
   export SPOTIFY_CLIENT_ID='your_client_id'
   export SPOTIFY_CLIENT_SECRET='your_client_secret'
   ```

   **Option 2: Create a local .env file (not tracked in git)**
   Create a file named `.env` in the scripts directory with:
   ```
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   ```
   Then install python-dotenv:
   ```bash
   pip install python-dotenv
   ```
   And add this line at the top of the script:
   ```python
   from dotenv import load_dotenv
   load_dotenv()
   ```

## Usage

Run the script:
```bash
python download_album_covers.py
```

The script will:
1. Read albums from `_data/albumsilike.csv`
2. Check which album covers already exist in `assets/img/albums I like/`
3. Download missing album covers from Spotify
4. Save them with proper filename sanitization

## Security Note

Never commit your Spotify API credentials to git. The `.env` file is already in `.gitignore` to prevent accidental commits. 