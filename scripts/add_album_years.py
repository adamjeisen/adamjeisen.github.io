import os
import csv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
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

def get_album_year(spotify_url):
    """Get album release year from Spotify."""
    try:
        # Extract album ID from Spotify URL
        album_id = spotify_url.split('/')[-1].split('?')[0]
        
        # Get album info from Spotify
        album = sp.album(album_id)
        
        # Extract release date
        release_date = album.get('release_date', '')
        if release_date:
            # Release date can be in format YYYY, YYYY-MM-DD, or YYYY-MM
            # Extract just the year
            year = release_date.split('-')[0]
            return year
        return ''
    except Exception as e:
        print(f"Error getting album year for {spotify_url}: {str(e)}")
        return ''

def main():
    # Paths
    csv_path = Path('_data/albumsilike.csv')
    
    # Read CSV and process albums
    albums = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        albums = list(reader)
    
    print(f"Found {len(albums)} albums in CSV")
    
    # Check if Year column already exists
    has_year_column = 'Year' in albums[0].keys() if albums else False
    
    # Process each album to get year if missing
    updated_count = 0
    for i, album in enumerate(albums):
        spotify_url = album.get('SpotifyUrl', '').strip()
        
        if not spotify_url:
            print(f"Skipping {album.get('Artist', 'Unknown')} - {album.get('Album', 'Unknown')}: No Spotify URL")
            if not has_year_column:
                album['Year'] = ''
            continue
        
        # Only fetch year if it's missing
        if not has_year_column or not album.get('Year', '').strip():
            print(f"Fetching year for {album.get('Artist', 'Unknown')} - {album.get('Album', 'Unknown')}...")
            year = get_album_year(spotify_url)
            album['Year'] = year
            updated_count += 1
            
            # Rate limiting - be nice to Spotify API
            time.sleep(0.2)
        else:
            print(f"Year already exists for {album.get('Artist', 'Unknown')} - {album.get('Album', 'Unknown')}: {album.get('Year', '')}")
    
    # Write updated CSV
    if albums:
        fieldnames = ['Artist', 'Album', 'Genre', 'Year', 'SpotifyUrl']
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(albums)
        
        print(f"\nUpdated CSV with {updated_count} new years")
        print(f"Total albums: {len(albums)}")
    else:
        print("No albums found in CSV")

if __name__ == "__main__":
    main()

