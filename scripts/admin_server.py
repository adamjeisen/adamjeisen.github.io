#!/usr/bin/env python3
"""
Albums Admin Server
Run from repo root: python scripts/admin_server.py
Then open http://localhost:5001
"""

import os
import csv
import sys
import time
import requests
import webbrowser
import threading
from pathlib import Path
from flask import Flask, jsonify, request, Response

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Paths (always relative to repo root, regardless of CWD)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "_data" / "albumsilike.csv"
COVERS_DIR = REPO_ROOT / "assets" / "img" / "albums I like"
CSV_FIELDS = ["Artist", "Album", "Genre", "Year", "SpotifyUrl"]

# ---------------------------------------------------------------------------
# Spotify client
# ---------------------------------------------------------------------------
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

if not CLIENT_ID or not CLIENT_SECRET:
    print(
        "\nError: Spotify API credentials not found.\n"
        "Please set environment variables before running:\n\n"
        "  export SPOTIFY_CLIENT_ID='your_client_id'\n"
        "  export SPOTIFY_CLIENT_SECRET='your_client_secret'\n"
    )
    sys.exit(1)

sp = spotipy.Spotify(
    client_credentials_manager=SpotifyClientCredentials(
        client_id=CLIENT_ID, client_secret=CLIENT_SECRET
    )
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Mirror the Liquid sanitize logic used in albums.md."""
    replacements = {
        ":": "_",
        "?": "",
        "'": "",
        ".": "",
        "%": "",
        "•": "",
        "/": "_",
        '"': "",
        "*": "",
        "<": "",
        ">": "",
        "|": "",
        "\\": "_",
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name


def read_csv() -> list[dict]:
    """Read CSV, skipping comment lines (# prefix)."""
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(
            (line for line in f if not line.lstrip().startswith("#")),
            fieldnames=CSV_FIELDS,
        )
        next(reader, None)  # skip header row
        for row in reader:
            rows.append(dict(row))
    return rows


def write_csv(rows: list[dict]) -> None:
    """Write rows back to CSV, preserving the comment header."""
    comment_line = None
    raw_lines = CSV_PATH.read_text(encoding="utf-8").splitlines(keepends=True)
    for line in raw_lines:
        if line.lstrip().startswith("#"):
            comment_line = line
            break

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        if comment_line:
            f.write(comment_line)
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def cover_exists(artist: str, album: str) -> bool:
    stem = sanitize_filename(f"{artist} - {album}")
    return (COVERS_DIR / f"{stem}.jpg").exists() or (COVERS_DIR / f"{stem}.png").exists()


def download_cover(cover_url: str, artist: str, album: str) -> bool:
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(f"{artist} - {album}")
    for ext in ("jpg", "png"):
        path = COVERS_DIR / f"{stem}.{ext}"
        try:
            r = requests.get(cover_url, stream=True, timeout=15)
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
            return True
        except Exception:
            if path.exists():
                path.unlink()
    return False


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/api/albums", methods=["GET"])
def get_albums():
    return jsonify(read_csv())


@app.route("/api/lookup", methods=["POST"])
def lookup():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400

    try:
        album_id = url.split("/")[-1].split("?")[0]
        album_data = sp.album(album_id)
    except Exception as e:
        return jsonify({"error": f"Spotify error: {e}"}), 400

    artist_name = ", ".join(a["name"] for a in album_data["artists"])
    album_name = album_data["name"]
    year = (album_data.get("release_date") or "")[:4]

    cover_url = ""
    if album_data.get("images"):
        images = sorted(album_data["images"], key=lambda x: x.get("width", 0), reverse=True)
        cover_url = images[0]["url"]

    genre_hint = ""
    try:
        artist_id = album_data["artists"][0]["id"]
        artist_data = sp.artist(artist_id)
        genres = artist_data.get("genres", [])
        if genres:
            genre_hint = ", ".join(g.title() for g in genres[:3])
    except Exception:
        pass

    return jsonify(
        {
            "artist": artist_name,
            "album": album_name,
            "year": year,
            "cover_url": cover_url,
            "genre_hint": genre_hint,
            "spotify_url": url,
        }
    )


@app.route("/api/albums", methods=["POST"])
def add_album():
    data = request.json or {}
    required = ["artist", "album", "genre", "year", "spotify_url"]
    missing = [k for k in required if not (data.get(k) or "").strip()]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    rows = read_csv()

    # Duplicate check (by Spotify URL, ignoring tracking params)
    new_base = data["spotify_url"].split("?")[0].rstrip("/")
    for row in rows:
        existing_base = (row.get("SpotifyUrl") or "").split("?")[0].rstrip("/")
        if existing_base == new_base:
            return jsonify({"error": "Album already in list"}), 409

    new_row = {
        "Artist": data["artist"].strip(),
        "Album": data["album"].strip(),
        "Genre": data["genre"].strip(),
        "Year": data["year"].strip(),
        "SpotifyUrl": data["spotify_url"].strip(),
    }
    rows.append(new_row)
    write_csv(rows)

    cover_downloaded = False
    if data.get("cover_url"):
        cover_downloaded = download_cover(
            data["cover_url"], new_row["Artist"], new_row["Album"]
        )

    return jsonify({"ok": True, "cover_downloaded": cover_downloaded})


@app.route("/api/albums/<int:index>", methods=["DELETE"])
def remove_album(index):
    rows = read_csv()
    if index < 0 or index >= len(rows):
        return jsonify({"error": "Index out of range"}), 404
    rows.pop(index)
    write_csv(rows)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Albums Admin</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0f0f0f;
    color: #e0e0e0;
    min-height: 100vh;
  }
  header {
    background: #1a1a1a;
    border-bottom: 1px solid #2a2a2a;
    padding: 16px 24px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  header h1 { font-size: 1.2rem; font-weight: 600; color: #fff; }
  header span { color: #1DB954; font-size: 1.4rem; }
  .container { max-width: 960px; margin: 0 auto; padding: 32px 24px; }

  /* Add panel */
  .add-panel {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 32px;
  }
  .add-panel h2 { font-size: 1rem; font-weight: 600; margin-bottom: 16px; color: #fff; }
  .url-row { display: flex; gap: 8px; }
  .url-row input {
    flex: 1;
    background: #0f0f0f;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 10px 14px;
    color: #e0e0e0;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .url-row input:focus { border-color: #1DB954; }
  button {
    background: #1DB954;
    color: #000;
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s, opacity 0.15s;
    white-space: nowrap;
  }
  button:hover { background: #1ed760; }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  button.secondary {
    background: #2a2a2a;
    color: #e0e0e0;
  }
  button.secondary:hover { background: #333; }
  button.danger {
    background: transparent;
    color: #e05252;
    padding: 4px 10px;
    font-size: 0.8rem;
  }
  button.danger:hover { background: rgba(224,82,82,0.1); }

  /* Preview card */
  #preview {
    display: none;
    margin-top: 20px;
    border-top: 1px solid #2a2a2a;
    padding-top: 20px;
  }
  .preview-inner {
    display: flex;
    gap: 20px;
    align-items: flex-start;
  }
  #preview-cover {
    width: 96px;
    height: 96px;
    object-fit: cover;
    border-radius: 8px;
    background: #2a2a2a;
    flex-shrink: 0;
  }
  .preview-meta { flex: 1; }
  .preview-meta .preview-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #fff;
    margin-bottom: 2px;
  }
  .preview-meta .preview-sub {
    font-size: 0.85rem;
    color: #888;
    margin-bottom: 14px;
  }
  .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .field label {
    display: block;
    font-size: 0.75rem;
    color: #888;
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .field input {
    width: 100%;
    background: #0f0f0f;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e0e0e0;
    font-size: 0.9rem;
    outline: none;
    transition: border-color 0.15s;
  }
  .field input:focus { border-color: #1DB954; }
  .add-row { margin-top: 14px; display: flex; gap: 8px; align-items: center; }

  /* Status toast */
  #status {
    display: none;
    margin-top: 14px;
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 0.875rem;
  }
  #status.success { background: rgba(29,185,84,0.15); color: #1DB954; border: 1px solid rgba(29,185,84,0.3); }
  #status.error { background: rgba(224,82,82,0.15); color: #e05252; border: 1px solid rgba(224,82,82,0.3); }

  /* Album list */
  .list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }
  .list-header h2 { font-size: 1rem; font-weight: 600; color: #fff; }
  #search {
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    padding: 8px 14px;
    color: #e0e0e0;
    font-size: 0.875rem;
    outline: none;
    width: 220px;
    transition: border-color 0.15s;
  }
  #search:focus { border-color: #1DB954; }

  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.875rem;
  }
  thead th {
    text-align: left;
    padding: 8px 12px;
    color: #666;
    font-weight: 500;
    text-transform: uppercase;
    font-size: 0.72rem;
    letter-spacing: 0.06em;
    border-bottom: 1px solid #2a2a2a;
  }
  tbody tr { border-bottom: 1px solid #1e1e1e; transition: background 0.1s; }
  tbody tr:hover { background: #1a1a1a; }
  tbody td { padding: 8px 12px; vertical-align: middle; }
  .thumb {
    width: 40px;
    height: 40px;
    object-fit: cover;
    border-radius: 4px;
    background: #2a2a2a;
    display: block;
  }
  .album-name { color: #fff; font-weight: 500; }
  .artist-name { color: #aaa; font-size: 0.82rem; }
  #album-count { color: #666; font-size: 0.85rem; }
  .spinner {
    display: inline-block;
    width: 14px; height: 14px;
    border: 2px solid #333;
    border-top-color: #1DB954;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    vertical-align: middle;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<header>
  <span>&#9835;</span>
  <h1>Albums Admin</h1>
</header>

<div class="container">

  <!-- Add Album Panel -->
  <div class="add-panel">
    <h2>Add Album</h2>
    <div class="url-row">
      <input id="spotify-url" type="text" placeholder="Paste Spotify album URL...">
      <button id="lookup-btn" onclick="lookupAlbum()">Lookup</button>
    </div>

    <div id="preview">
      <div class="preview-inner">
        <img id="preview-cover" src="" alt="cover">
        <div class="preview-meta">
          <div class="preview-title" id="preview-title"></div>
          <div class="preview-sub" id="preview-sub"></div>
          <div class="fields">
            <div class="field">
              <label>Genre</label>
              <input id="field-genre" type="text" placeholder="e.g. Folk">
            </div>
            <div class="field">
              <label>Year</label>
              <input id="field-year" type="text" placeholder="e.g. 2024">
            </div>
          </div>
          <div class="add-row">
            <button onclick="addAlbum()">Add to List</button>
            <button class="secondary" onclick="clearPreview()">Clear</button>
          </div>
        </div>
      </div>
    </div>

    <div id="status"></div>
  </div>

  <!-- Album List -->
  <div class="list-header">
    <h2>All Albums <span id="album-count"></span></h2>
    <input id="search" type="text" placeholder="Search..." oninput="filterTable()">
  </div>
  <table id="album-table">
    <thead>
      <tr>
        <th style="width:52px"></th>
        <th>Album</th>
        <th>Genre</th>
        <th>Year</th>
        <th></th>
      </tr>
    </thead>
    <tbody id="album-tbody"></tbody>
  </table>

</div>

<script>
let allAlbums = [];
let pendingData = null;

// ---- Lookup ----
async function lookupAlbum() {
  const url = document.getElementById('spotify-url').value.trim();
  if (!url) return;
  const btn = document.getElementById('lookup-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  clearStatus();

  try {
    const res = await fetch('/api/lookup', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url})
    });
    const data = await res.json();
    if (!res.ok) { showStatus(data.error || 'Lookup failed', 'error'); return; }

    pendingData = data;
    document.getElementById('preview-cover').src = data.cover_url || '';
    document.getElementById('preview-title').textContent = data.album;
    document.getElementById('preview-sub').textContent = data.artist;
    document.getElementById('field-genre').value = data.genre_hint || '';
    document.getElementById('field-year').value = data.year || '';
    document.getElementById('preview').style.display = 'block';
    document.getElementById('field-genre').focus();
  } catch (e) {
    showStatus('Network error: ' + e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = 'Lookup';
  }
}

// Allow Enter key in URL field
document.getElementById('spotify-url').addEventListener('keydown', e => {
  if (e.key === 'Enter') lookupAlbum();
});

// ---- Add Album ----
async function addAlbum() {
  if (!pendingData) return;
  const genre = document.getElementById('field-genre').value.trim();
  const year = document.getElementById('field-year').value.trim();
  if (!genre) { showStatus('Please enter a genre', 'error'); return; }

  clearStatus();
  try {
    const res = await fetch('/api/albums', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        artist: pendingData.artist,
        album: pendingData.album,
        genre,
        year,
        spotify_url: pendingData.spotify_url,
        cover_url: pendingData.cover_url,
      })
    });
    const data = await res.json();
    if (!res.ok) { showStatus(data.error || 'Failed to add album', 'error'); return; }

    const msg = data.cover_downloaded
      ? `Added "${pendingData.album}" and downloaded cover.`
      : `Added "${pendingData.album}" (cover download failed — run download_album_covers.py).`;
    showStatus(msg, 'success');
    clearPreview();
    document.getElementById('spotify-url').value = '';
    await loadAlbums();
  } catch (e) {
    showStatus('Network error: ' + e.message, 'error');
  }
}

// ---- Remove Album ----
async function removeAlbum(index, name) {
  if (!confirm(`Remove "${name}" from the list?`)) return;
  try {
    const res = await fetch(`/api/albums/${index}`, {method: 'DELETE'});
    const data = await res.json();
    if (!res.ok) { showStatus(data.error || 'Failed to remove album', 'error'); return; }
    showStatus(`Removed "${name}"`, 'success');
    await loadAlbums();
  } catch (e) {
    showStatus('Network error: ' + e.message, 'error');
  }
}

// ---- Load & Render ----
async function loadAlbums() {
  const res = await fetch('/api/albums');
  allAlbums = await res.json();
  renderTable(allAlbums);
}

function renderTable(albums) {
  const tbody = document.getElementById('album-tbody');
  document.getElementById('album-count').textContent = `(${albums.length})`;

  // Map back to original index in allAlbums for stable delete
  tbody.innerHTML = albums.map(a => {
    const origIndex = allAlbums.indexOf(a);
    const stem = sanitizeFilename(`${a.Artist} - ${a.Album}`);
    // Try to show cover from local assets
    const imgSrc = `/assets/img/albums I like/${stem}.jpg`;
    return `<tr>
      <td><img class="thumb" src="${escHtml(imgSrc)}" onerror="this.src='/assets/img/albums I like/${escHtml(stem)}.png'; this.onerror=null;" alt=""></td>
      <td>
        <div class="album-name">${escHtml(a.Album)}</div>
        <div class="artist-name">${escHtml(a.Artist)}</div>
      </td>
      <td>${escHtml(a.Genre || '')}</td>
      <td>${escHtml(a.Year || '')}</td>
      <td><button class="danger" onclick="removeAlbum(${origIndex}, '${escJs(a.Album)}')">Remove</button></td>
    </tr>`;
  }).join('');
}

function filterTable() {
  const q = document.getElementById('search').value.toLowerCase();
  if (!q) { renderTable(allAlbums); return; }
  const filtered = allAlbums.filter(a =>
    (a.Artist || '').toLowerCase().includes(q) ||
    (a.Album || '').toLowerCase().includes(q) ||
    (a.Genre || '').toLowerCase().includes(q)
  );
  renderTable(filtered);
}

// ---- Helpers ----
function clearPreview() {
  pendingData = null;
  document.getElementById('preview').style.display = 'none';
  document.getElementById('preview-cover').src = '';
}

function showStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = type;
  el.style.display = 'block';
}

function clearStatus() {
  const el = document.getElementById('status');
  el.style.display = 'none';
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function escJs(s) {
  return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'");
}

// Mirror Liquid sanitize_filename from albums.md
function sanitizeFilename(name) {
  const replacements = {':':'_','?':'','\'':'','.':'','%':'','•':'','/':'_','"':'','*':'','<':'','>':'','|':'','\\':'_'};
  for (const [k, v] of Object.entries(replacements)) {
    name = name.split(k).join(v);
  }
  return name;
}

loadAlbums();
</script>
</body>
</html>
"""


@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")


# Serve local album cover images so the table can show thumbnails
@app.route("/assets/img/albums I like/<path:filename>")
def serve_cover(filename):
    from flask import send_from_directory
    return send_from_directory(COVERS_DIR, filename)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    PORT = 5001
    url = f"http://localhost:{PORT}"
    print(f"\nAlbums Admin running at {url}\n")
    # Open browser after a short delay so the server is ready
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
