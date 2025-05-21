import os
import csv
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from urllib.parse import quote
import time
from pathlib import Path

# Get Spotify API credentials from environment variables
CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

if not CLIENT_ID or not CLIENT_SECRET:
    raise ValueError(
        "Spotify API credentials not found in environment variables. "
        "Please set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables. "
        "You can do this by running:\n\n"
        "export SPOTIFY_CLIENT_ID='your_client_id'\n"
        "export SPOTIFY_CLIENT_SECRET='your_client_secret'\n\n"
        "Or by creating a .env file (not tracked in git) with these variables."
    )

# Initialize Spotify client
client_credentials_manager = SpotifyClientCredentials(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET
)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

def sanitize_filename(filename):
    """Sanitize filename by replacing special characters."""
    replacements = {
        ':': '_',
        '?': '',
        "'": '',
        '.': '',
        '%': '',
        '•': '',
        '/': '_',
        '"': '',
        '*': '',
        '<': '',
        '>': '',
        '|': '',
        '\\': '_'
    }
    for old, new in replacements.items():
        filename = filename.replace(old, new)
    return filename

def get_album_cover_url(spotify_url):
    """Get album cover URL from Spotify."""
    try:
        # Extract album ID from Spotify URL
        album_id = spotify_url.split('/')[-1].split('?')[0]
        
        # Get album info from Spotify
        album = sp.album(album_id)
        
        # Get the highest resolution image
        if album['images']:
            # Sort by width and get the largest image
            images = sorted(album['images'], key=lambda x: x['width'], reverse=True)
            return images[0]['url']
        return None
    except Exception as e:
        print(f"Error getting album cover for {spotify_url}: {str(e)}")
        return None

def download_image(url, filepath):
    """Download image from URL and save to filepath."""
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Error downloading image to {filepath}: {str(e)}")
        return False

def main():
    # Paths
    csv_path = '_data/albumsilike.csv'
    output_dir = Path('assets/img/albums I like')
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get list of existing files
    existing_files = {f.name for f in output_dir.glob('*')}
    
    # Read CSV and process albums
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        albums = list(reader)
    
    print(f"Found {len(albums)} albums in CSV")
    print(f"Found {len(existing_files)} existing album covers")
    
    # Process each album
    for album in albums:
        # Create filename
        filename = f"{album['Artist']} - {album['Album']}"
        filename = sanitize_filename(filename)
        jpg_path = f"{filename}.jpg"
        png_path = f"{filename}.png"
        
        # Skip if either jpg or png exists
        if jpg_path in existing_files or png_path in existing_files:
            continue
        
        print(f"\nProcessing: {filename}")
        
        # Get album cover URL
        cover_url = get_album_cover_url(album['SpotifyUrl'])
        if not cover_url:
            print(f"Could not get cover URL for {filename}")
            continue
        
        # Try downloading as jpg first
        filepath = output_dir / jpg_path
        if download_image(cover_url, filepath):
            print(f"Successfully downloaded {jpg_path}")
        else:
            # If jpg fails, try png
            filepath = output_dir / png_path
            if download_image(cover_url, filepath):
                print(f"Successfully downloaded {png_path}")
            else:
                print(f"Failed to download cover for {filename}")
        
        # Rate limiting - be nice to Spotify API
        time.sleep(0.5)

if __name__ == "__main__":
    main() 