#!/usr/bin/env python3
"""
Admin Server — Albums + Photo Journal ("Feelings")
Run from repo root: python scripts/admin_server.py
  Albums admin:  http://localhost:5001/
  Photos admin:  http://localhost:5001/photos
"""

import hashlib
import io
import json
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

import cloudinary
import cloudinary.api
import cloudinary.uploader

from admin_helpers import (
    parse_markdown, serialize_markdown, read_markdown_file, write_markdown_file,
    list_markdown_dir, read_yaml, write_yaml, read_yaml_with_comments,
    write_yaml_raw, read_config_field, update_config_field,
    read_bib, write_bib, slugify,
)

load_dotenv()

# ---------------------------------------------------------------------------
# Paths (always relative to repo root, regardless of CWD)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "_data" / "albumsilike.csv"
COVERS_DIR = REPO_ROOT / "assets" / "img" / "albums I like"
CSV_FIELDS = ["Artist", "Album", "Genre", "Year", "SpotifyUrl"]
THINGS_I_SAW_PATH = REPO_ROOT / "_data" / "feelings.json"

# Content directories
NEWS_DIR = REPO_ROOT / "_news"
POSTS_DIR = REPO_ROOT / "_posts"
PROJECTS_DIR = REPO_ROOT / "_projects"
BOOKS_DIR = REPO_ROOT / "_books"
BIB_PATH = REPO_ROOT / "_bibliography" / "papers.bib"
CONFIG_PATH = REPO_ROOT / "_config.yml"
SOCIALS_PATH = REPO_ROOT / "_data" / "socials.yml"
ABOUT_PATH = REPO_ROOT / "_pages" / "about.md"
PUB_PREVIEW_DIR = REPO_ROOT / "assets" / "img" / "publication_preview"
PDF_DIR = REPO_ROOT / "assets" / "pdf"
BOOK_COVERS_DIR = REPO_ROOT / "assets" / "img" / "book_covers"

# ---------------------------------------------------------------------------
# Spotify client (optional — photo admin works without it)
# ---------------------------------------------------------------------------
CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

sp = None
if CLIENT_ID and CLIENT_SECRET:
    try:
        sp = spotipy.Spotify(
            client_credentials_manager=SpotifyClientCredentials(
                client_id=CLIENT_ID, client_secret=CLIENT_SECRET
            )
        )
    except Exception as _e:
        print(f"Warning: Spotify client initialization failed: {_e}")
else:
    print(
        "\nWarning: Spotify credentials not found — album lookup disabled.\n"
        "Photo admin (/photos) is still available.\n"
    )

# ---------------------------------------------------------------------------
# Cloudinary client (required for photo uploads)
# ---------------------------------------------------------------------------
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True,
    )
    print(f"Cloudinary configured: cloud_name={CLOUDINARY_CLOUD_NAME}")
else:
    print(
        "\nWarning: Cloudinary credentials not found — photo uploads will be disabled.\n"
        "Add CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET to .env\n"
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
# Feelings helpers
# ---------------------------------------------------------------------------

def read_tis_json() -> list:
    """Read feelings.json; return [] if file doesn't exist yet."""
    if not THINGS_I_SAW_PATH.exists():
        return []
    with open(THINGS_I_SAW_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def write_tis_json(data: list) -> None:
    """Write feelings.json atomically."""
    tmp = THINGS_I_SAW_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, THINGS_I_SAW_PATH)


def find_month_index(data: list, month_id: str) -> int:
    """Return index of month with given id, or -1."""
    for i, m in enumerate(data):
        if m.get("id") == month_id:
            return i
    return -1


def find_event_index(month: dict, event_id: str) -> int:
    """Return index of event within month's events list, or -1."""
    for i, e in enumerate(month.get("events", [])):
        if e.get("id") == event_id:
            return i
    return -1


def cloudinary_public_id(url: str) -> str:
    """Extract Cloudinary public_id from a secure URL."""
    try:
        path = url.split("/upload/")[-1]
        # Strip version segment (v<digits>/) if present
        if path.startswith("v") and "/" in path:
            parts = path.split("/", 1)
            if parts[0][1:].isdigit():
                path = parts[1]
        # Remove file extension
        return path.rsplit(".", 1)[0]
    except Exception:
        return ""


def cloudinary_delete(url: str) -> None:
    """Delete a Cloudinary asset by URL. Logs warnings but never raises."""
    try:
        public_id = cloudinary_public_id(url)
        if public_id:
            cloudinary.uploader.destroy(public_id, resource_type="image")
    except Exception as e:
        print(f"Warning: Cloudinary delete failed for {url}: {e}")


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)


@app.route("/api/albums", methods=["GET"])
def get_albums():
    return jsonify(read_csv())


@app.route("/api/lookup", methods=["POST"])
def lookup():
    if sp is None:
        return jsonify({"error": "Spotify not configured — add credentials to .env"}), 503

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
  :root {
    --bg: #0f0f0f; --bg-panel: #1a1a1a; --border: #2a2a2a; --border-light: #1e1e1e; --border-field: #333;
    --text: #e0e0e0; --text-strong: #fff; --text-muted: #888; --text-faint: #666; --text-sub: #aaa;
    --accent: #1DB954; --accent-hover: #1ed760;
    --input-bg: #0f0f0f; --hover-bg: #1a1a1a;
    --secondary-bg: #2a2a2a; --secondary-hover: #333;
  }
  [data-theme="light"] {
    --bg: #f5f5f5; --bg-panel: #fff; --border: #ddd; --border-light: #eee; --border-field: #ccc;
    --text: #333; --text-strong: #111; --text-muted: #777; --text-faint: #999; --text-sub: #555;
    --input-bg: #fff; --hover-bg: #f0f0f0;
    --secondary-bg: #e8e8e8; --secondary-hover: #ddd;
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; transition: background 0.2s, color 0.2s; }
  header { background: var(--bg-panel); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 1.2rem; font-weight: 600; color: var(--text-strong); }
  header span { color: var(--accent); font-size: 1.4rem; }
  header nav { display: flex; align-items: center; gap: 4px; margin-left: auto; }
  header nav a { color: var(--text-muted); text-decoration: none; font-size: 0.875rem; padding: 4px 10px; border-radius: 6px; transition: color 0.15s, background 0.15s; }
  header nav a:hover { color: var(--text); background: var(--hover-bg); }
  header nav a.active { color: var(--accent); }
  .theme-toggle { background: transparent; border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; color: var(--text-muted); font-size: 0.82rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
  .theme-toggle:hover { color: var(--text); border-color: var(--text-faint); }
  .container { max-width: 960px; margin: 0 auto; padding: 32px 24px; }

  /* Add panel */
  .add-panel { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-bottom: 32px; }
  .add-panel h2 { font-size: 1rem; font-weight: 600; margin-bottom: 16px; color: var(--text-strong); }
  .url-row { display: flex; gap: 8px; }
  .url-row input { flex: 1; background: var(--input-bg); border: 1px solid var(--border-field); border-radius: 8px; padding: 10px 14px; color: var(--text); font-size: 0.9rem; outline: none; transition: border-color 0.15s; }
  .url-row input:focus { border-color: var(--accent); }
  button { background: var(--accent); color: #000; border: none; border-radius: 8px; padding: 10px 18px; font-size: 0.875rem; font-weight: 600; cursor: pointer; transition: background 0.15s, opacity 0.15s; white-space: nowrap; }
  button:hover { background: var(--accent-hover); }
  button:disabled { opacity: 0.4; cursor: not-allowed; }
  button.secondary { background: var(--secondary-bg); color: var(--text); }
  button.secondary:hover { background: var(--secondary-hover); }
  button.danger { background: transparent; color: #e05252; padding: 4px 10px; font-size: 0.8rem; }
  button.danger:hover { background: rgba(224,82,82,0.1); }

  /* Preview card */
  #preview { display: none; margin-top: 20px; border-top: 1px solid var(--border); padding-top: 20px; }
  .preview-inner { display: flex; gap: 20px; align-items: flex-start; }
  #preview-cover { width: 96px; height: 96px; object-fit: cover; border-radius: 8px; background: var(--border); flex-shrink: 0; }
  .preview-meta { flex: 1; }
  .preview-meta .preview-title { font-size: 1.05rem; font-weight: 600; color: var(--text-strong); margin-bottom: 2px; }
  .preview-meta .preview-sub { font-size: 0.85rem; color: var(--text-muted); margin-bottom: 14px; }
  .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .field label { display: block; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 4px; text-transform: uppercase; letter-spacing: 0.05em; }
  .field input { width: 100%; background: var(--input-bg); border: 1px solid var(--border-field); border-radius: 6px; padding: 8px 12px; color: var(--text); font-size: 0.9rem; outline: none; transition: border-color 0.15s; }
  .field input:focus { border-color: var(--accent); }
  .add-row { margin-top: 14px; display: flex; gap: 8px; align-items: center; }

  /* Status toast */
  #status { display: none; margin-top: 14px; padding: 10px 14px; border-radius: 8px; font-size: 0.875rem; }
  #status.success { background: rgba(29,185,84,0.15); color: #1DB954; border: 1px solid rgba(29,185,84,0.3); }
  #status.error { background: rgba(224,82,82,0.15); color: #e05252; border: 1px solid rgba(224,82,82,0.3); }

  /* Album list */
  .list-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .list-header h2 { font-size: 1rem; font-weight: 600; color: var(--text-strong); }
  #search { background: var(--bg-panel); border: 1px solid var(--border); border-radius: 8px; padding: 8px 14px; color: var(--text); font-size: 0.875rem; outline: none; width: 220px; transition: border-color 0.15s; }
  #search:focus { border-color: var(--accent); }

  table { width: 100%; border-collapse: collapse; font-size: 0.875rem; }
  thead th { text-align: left; padding: 8px 12px; color: var(--text-faint); font-weight: 500; text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.06em; border-bottom: 1px solid var(--border); }
  tbody tr { border-bottom: 1px solid var(--border-light); transition: background 0.1s; }
  tbody tr:hover { background: var(--hover-bg); }
  tbody td { padding: 8px 12px; vertical-align: middle; }
  .thumb { width: 40px; height: 40px; object-fit: cover; border-radius: 4px; background: var(--border); display: block; }
  .album-name { color: var(--text-strong); font-weight: 500; }
  .artist-name { color: var(--text-sub); font-size: 0.82rem; }
  #album-count { color: var(--text-faint); font-size: 0.85rem; }
  .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid var(--border-field); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; vertical-align: middle; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
<header>
  <span>&#9835;</span>
  <h1>Albums Admin</h1>
  <nav>
    <a href="/" class="active">Albums</a>
    <a href="/photos">Photos</a>
    <a href="/news">News</a>
    <a href="/blog">Blog</a>
    <a href="/projects">Projects</a>
    <a href="/books">Books</a>
    <a href="/publications">Pubs</a>
    <a href="/settings">Settings</a>
  </nav>
  <button class="theme-toggle" onclick="toggleTheme()" id="theme-btn">Light</button>
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
// Theme toggle — shares localStorage key with photos admin
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('photos-admin-theme', next);
  document.getElementById('theme-btn').textContent = next === 'light' ? 'Dark' : 'Light';
}
(function initTheme() {
  const saved = localStorage.getItem('photos-admin-theme') || 'dark';
  if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
  document.getElementById('theme-btn').textContent = saved === 'light' ? 'Dark' : 'Light';
})();

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


# ---------------------------------------------------------------------------
# Feelings — API routes
# ---------------------------------------------------------------------------

@app.route("/api/photos/months", methods=["GET"])
def tis_get_months():
    return jsonify(read_tis_json())


@app.route("/api/photos/months", methods=["POST"])
def tis_create_month():
    body = request.json or {}
    month_id = (body.get("id") or "").strip()
    month_label = (body.get("month_label") or "").strip()
    description = (body.get("description") or "").strip()
    playlist_url = (body.get("playlist_url") or "").strip()
    if not month_id or not month_label:
        return jsonify({"error": "id and month_label are required"}), 400

    data = read_tis_json()
    if find_month_index(data, month_id) != -1:
        return jsonify({"error": f"Month '{month_id}' already exists"}), 409

    data.append({"id": month_id, "month_label": month_label, "description": description, "playlist_url": playlist_url, "events": []})
    data.sort(key=lambda m: m["id"], reverse=True)
    write_tis_json(data)
    return jsonify({"ok": True})


@app.route("/api/photos/months/reorder", methods=["POST"])
def tis_reorder_months():
    body = request.json or {}
    ordered_ids = body.get("ordered_ids")
    if not ordered_ids or not isinstance(ordered_ids, list):
        return jsonify({"error": "ordered_ids is required"}), 400
    data = read_tis_json()
    id_to_month = {m["id"]: m for m in data}
    for mid in ordered_ids:
        if mid not in id_to_month:
            return jsonify({"error": f"Month '{mid}' not found"}), 404
    write_tis_json([id_to_month[mid] for mid in ordered_ids])
    return jsonify({"ok": True})


@app.route("/api/photos/months/<month_id>", methods=["PUT"])
def tis_update_month(month_id):
    body = request.json or {}
    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    if "month_label" in body:
        data[idx]["month_label"] = body["month_label"].strip()
    if "description" in body:
        data[idx]["description"] = body["description"].strip()
    if "playlist_url" in body:
        data[idx]["playlist_url"] = body["playlist_url"].strip()
    write_tis_json(data)
    return jsonify({"ok": True})


@app.route("/api/photos/months/<month_id>", methods=["DELETE"])
def tis_delete_month(month_id):
    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    # Delete all photos from Cloudinary
    for event in data[idx].get("events", []):
        for photo in event.get("photos", []):
            cloudinary_delete(photo.get("url", ""))
    data.pop(idx)
    write_tis_json(data)
    return jsonify({"ok": True})


# ---- Event routes ----

@app.route("/api/photos/months/<month_id>/events", methods=["POST"])
def tis_create_event(month_id):
    body = request.json or {}
    event_id = (body.get("id") or "").strip()
    title = (body.get("title") or "").strip()
    if not event_id:
        return jsonify({"error": "id is required"}), 400

    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    if find_event_index(data[idx], event_id) != -1:
        return jsonify({"error": f"Event '{event_id}' already exists in this month"}), 409

    data[idx]["events"].append({"id": event_id, "title": title, "photos": []})
    write_tis_json(data)
    return jsonify({"ok": True})


@app.route("/api/photos/months/<month_id>/events/<event_id>", methods=["PUT"])
def tis_update_event(month_id, event_id):
    body = request.json or {}
    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    eidx = find_event_index(data[idx], event_id)
    if eidx == -1:
        return jsonify({"error": "Event not found"}), 404
    if "title" in body:
        data[idx]["events"][eidx]["title"] = body["title"].strip()
    write_tis_json(data)
    return jsonify({"ok": True})


@app.route("/api/photos/months/<month_id>/events/<event_id>", methods=["DELETE"])
def tis_delete_event(month_id, event_id):
    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    eidx = find_event_index(data[idx], event_id)
    if eidx == -1:
        return jsonify({"error": "Event not found"}), 404
    # Delete all photos from Cloudinary
    for photo in data[idx]["events"][eidx].get("photos", []):
        cloudinary_delete(photo.get("url", ""))
    data[idx]["events"].pop(eidx)
    write_tis_json(data)
    return jsonify({"ok": True})


# ---- Photo routes (per-event) ----

@app.route("/api/photos/months/<month_id>/events/<event_id>/photos", methods=["POST"])
def tis_upload_photo(month_id, event_id):
    if not CLOUDINARY_CLOUD_NAME:
        return jsonify({"error": "Cloudinary not configured — add credentials to .env"}), 503

    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    eidx = find_event_index(data[idx], event_id)
    if eidx == -1:
        return jsonify({"error": "Event not found"}), 404

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    caption = (request.form.get("caption") or "").strip()

    # Upload to Cloudinary first to get the canonical etag hash
    file_bytes = file.read()
    try:
        result = cloudinary.uploader.upload(
            file_bytes,
            folder="things-i-saw",
            resource_type="image",
            image_metadata=True,
        )
    except Exception as e:
        return jsonify({"error": f"Cloudinary upload failed: {e}"}), 500

    file_hash = result.get("etag", "") or hashlib.md5(file_bytes).hexdigest()

    # Check for duplicates across all months/events
    for m in data:
        for ev in m.get("events", []):
            for p in ev.get("photos", []):
                if p.get("hash") == file_hash:
                    # Already uploaded to Cloudinary, so clean it up
                    cloudinary_delete(result["secure_url"])
                    return jsonify({
                        "error": f"Duplicate photo — already exists in \"{m.get('month_label', m['id'])}\" / \"{ev.get('title') or ev['id']}\""
                    }), 409

    width = result.get("width", 0)
    height = result.get("height", 0)
    orientation = "landscape" if width >= height else "portrait"

    # Extract EXIF date for sorting
    date_taken = ""
    meta = result.get("image_metadata") or {}
    for key in ("DateTimeOriginal", "DateTime", "CreateDate"):
        if key in meta:
            date_taken = meta[key]
            break

    photo = {
        "url": result["secure_url"],
        "caption": caption,
        "width": width,
        "height": height,
        "orientation": orientation,
        "date_taken": date_taken,
        "hash": file_hash,
    }
    data[idx]["events"][eidx]["photos"].append(photo)

    # Sort photos by date_taken descending (most recent first) within the event
    data[idx]["events"][eidx]["photos"].sort(
        key=lambda p: p.get("date_taken") or "", reverse=True
    )

    write_tis_json(data)
    return jsonify({"ok": True, "photo": photo})


@app.route("/api/photos/months/<month_id>/events/<event_id>/photos/<int:photo_idx>", methods=["PUT"])
def tis_update_photo(month_id, event_id, photo_idx):
    body = request.json or {}
    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    eidx = find_event_index(data[idx], event_id)
    if eidx == -1:
        return jsonify({"error": "Event not found"}), 404
    photos = data[idx]["events"][eidx]["photos"]
    if photo_idx < 0 or photo_idx >= len(photos):
        return jsonify({"error": "Photo index out of range"}), 404
    if "caption" in body:
        photos[photo_idx]["caption"] = body["caption"].strip()
    if "hidden" in body:
        photos[photo_idx]["hidden"] = bool(body["hidden"])
    write_tis_json(data)
    return jsonify({"ok": True})


@app.route("/api/photos/months/<month_id>/events/<event_id>/photos/<int:photo_idx>", methods=["DELETE"])
def tis_delete_photo(month_id, event_id, photo_idx):
    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    eidx = find_event_index(data[idx], event_id)
    if eidx == -1:
        return jsonify({"error": "Event not found"}), 404
    photos = data[idx]["events"][eidx]["photos"]
    if photo_idx < 0 or photo_idx >= len(photos):
        return jsonify({"error": "Photo index out of range"}), 404
    cloudinary_delete(photos[photo_idx].get("url", ""))
    photos.pop(photo_idx)
    write_tis_json(data)
    return jsonify({"ok": True})


@app.route("/api/photos/months/<month_id>/events/<event_id>/photos/reorder", methods=["POST"])
def tis_reorder_photos(month_id, event_id):
    body = request.json or {}
    from_idx = body.get("from_index")
    to_idx = body.get("to_index")
    if from_idx is None or to_idx is None:
        return jsonify({"error": "from_index and to_index are required"}), 400

    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    eidx = find_event_index(data[idx], event_id)
    if eidx == -1:
        return jsonify({"error": "Event not found"}), 404
    photos = data[idx]["events"][eidx]["photos"]
    if not (0 <= from_idx < len(photos) and 0 <= to_idx < len(photos)):
        return jsonify({"error": "Index out of range"}), 400

    photo = photos.pop(from_idx)
    photos.insert(to_idx, photo)
    write_tis_json(data)
    return jsonify({"ok": True})


@app.route("/api/photos/backfill-hashes", methods=["POST"])
def tis_backfill_hashes():
    """Backfill MD5 hashes for existing photos using Cloudinary's etag."""
    if not CLOUDINARY_CLOUD_NAME:
        return jsonify({"error": "Cloudinary not configured"}), 503

    data = read_tis_json()
    updated = 0
    errors = 0

    for month in data:
        for event in month.get("events", []):
            for photo in event.get("photos", []):
                if photo.get("hash"):
                    continue
                public_id = cloudinary_public_id(photo.get("url", ""))
                if not public_id:
                    errors += 1
                    continue
                try:
                    info = cloudinary.api.resource(public_id, resource_type="image")
                    photo["hash"] = info.get("etag", "")
                    if photo["hash"]:
                        updated += 1
                    else:
                        errors += 1
                except Exception as e:
                    print(f"Warning: could not get etag for {public_id}: {e}")
                    errors += 1

    write_tis_json(data)
    return jsonify({"ok": True, "updated": updated, "errors": errors})


@app.route("/api/photos/bulk-action", methods=["POST"])
def tis_bulk_action():
    """Bulk actions on multiple photos: hide, unhide, delete, move."""
    body = request.json or {}
    action = body.get("action")  # "hide", "unhide", "delete", "move"
    photos = body.get("photos", [])  # [{month_id, event_id, photo_idx}, ...]
    dst_event_id = body.get("dst_event_id", "")  # only for "move"

    if action not in ("hide", "unhide", "delete", "move"):
        return jsonify({"error": "Invalid action"}), 400
    if not photos:
        return jsonify({"error": "No photos selected"}), 400
    if action == "move" and not dst_event_id:
        return jsonify({"error": "dst_event_id is required for move"}), 400

    data = read_tis_json()

    # Process in reverse-index order so that popping doesn't shift later indices
    # Group by month+event, sort by photo_idx descending
    photos_sorted = sorted(photos, key=lambda p: (p["month_id"], p["event_id"], -p["photo_idx"]))

    moved = []
    count = 0
    for sel in photos_sorted:
        midx = find_month_index(data, sel["month_id"])
        if midx == -1:
            continue
        eidx = find_event_index(data[midx], sel["event_id"])
        if eidx == -1:
            continue
        photo_list = data[midx]["events"][eidx]["photos"]
        pi = sel["photo_idx"]
        if pi < 0 or pi >= len(photo_list):
            continue

        if action == "hide":
            photo_list[pi]["hidden"] = True
            count += 1
        elif action == "unhide":
            photo_list[pi]["hidden"] = False
            count += 1
        elif action == "delete":
            cloudinary_delete(photo_list[pi].get("url", ""))
            photo_list.pop(pi)
            count += 1
        elif action == "move":
            photo = photo_list.pop(pi)
            moved.append((midx, photo))
            count += 1

    if action == "move" and moved:
        # All selected photos go to dst_event within the same month as each photo
        for midx, photo in moved:
            dst_eidx = find_event_index(data[midx], dst_event_id)
            if dst_eidx == -1:
                continue
            data[midx]["events"][dst_eidx]["photos"].append(photo)

    write_tis_json(data)
    return jsonify({"ok": True, "count": count})


@app.route("/api/photos/months/<month_id>/move-photo", methods=["POST"])
def tis_move_photo_between_events(month_id):
    body = request.json or {}
    src_event = (body.get("src_event") or "").strip()
    dst_event = (body.get("dst_event") or "").strip()
    photo_idx = body.get("photo_index")
    if not src_event or not dst_event or photo_idx is None:
        return jsonify({"error": "src_event, dst_event, and photo_index are required"}), 400

    data = read_tis_json()
    idx = find_month_index(data, month_id)
    if idx == -1:
        return jsonify({"error": "Month not found"}), 404
    src_eidx = find_event_index(data[idx], src_event)
    dst_eidx = find_event_index(data[idx], dst_event)
    if src_eidx == -1 or dst_eidx == -1:
        return jsonify({"error": "Event not found"}), 404
    src_photos = data[idx]["events"][src_eidx]["photos"]
    if photo_idx < 0 or photo_idx >= len(src_photos):
        return jsonify({"error": "Photo index out of range"}), 404

    photo = src_photos.pop(photo_idx)
    data[idx]["events"][dst_eidx]["photos"].append(photo)
    write_tis_json(data)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# News API
# ---------------------------------------------------------------------------

@app.route("/api/news")
def api_news_list():
    items = list_markdown_dir(NEWS_DIR)
    return jsonify(items)


@app.route("/api/news", methods=["POST"])
def api_news_create():
    body = request.json or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    filename = slugify(title) + ".md"
    path = NEWS_DIR / filename
    if path.exists():
        return jsonify({"error": f"File '{filename}' already exists"}), 409
    data = {
        "layout": "post",
        "date": body.get("date", ""),
        "inline": body.get("inline", True),
        "show": body.get("show", True),
    }
    write_markdown_file(path, {**data, "body": body.get("body", "")})
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/news/<filename>", methods=["PUT"])
def api_news_update(filename):
    path = NEWS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    body = request.json or {}
    existing = read_markdown_file(path)
    if "date" in body:
        existing["date"] = body["date"]
    if "inline" in body:
        existing["inline"] = body["inline"]
    if "show" in body:
        existing["show"] = body["show"]
    if "body" in body:
        existing["body"] = body["body"]
    write_markdown_file(path, existing)
    return jsonify({"ok": True})


@app.route("/api/news/<filename>", methods=["DELETE"])
def api_news_delete(filename):
    path = NEWS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    path.unlink()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Blog Posts API
# ---------------------------------------------------------------------------

@app.route("/api/posts")
def api_posts_list():
    items = list_markdown_dir(POSTS_DIR)
    # Exclude examples subdirectory (only .md in root)
    return jsonify(items)


@app.route("/api/posts", methods=["POST"])
def api_posts_create():
    body = request.json or {}
    title = (body.get("title") or "").strip()
    date = (body.get("date") or "").strip()
    if not title or not date:
        return jsonify({"error": "Title and date are required"}), 400
    # Date should be YYYY-MM-DD format
    date_prefix = date[:10]
    filename = f"{date_prefix}-{slugify(title)}.md"
    path = POSTS_DIR / filename
    if path.exists():
        return jsonify({"error": f"File '{filename}' already exists"}), 409
    data = {
        "layout": "post",
        "title": title,
        "date": body.get("date", ""),
        "description": body.get("description", ""),
        "tags": body.get("tags", ""),
        "categories": body.get("categories", ""),
        "thumbnail": body.get("thumbnail", ""),
        "published": body.get("published", True),
    }
    write_markdown_file(path, {**data, "body": body.get("body", "")})
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/posts/<filename>", methods=["PUT"])
def api_posts_update(filename):
    path = POSTS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    body = request.json or {}
    existing = read_markdown_file(path)
    for key in ("title", "date", "description", "tags", "categories", "thumbnail", "published", "body", "importance"):
        if key in body:
            existing[key] = body[key]
    write_markdown_file(path, existing)
    return jsonify({"ok": True})


@app.route("/api/posts/<filename>", methods=["DELETE"])
def api_posts_delete(filename):
    path = POSTS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    path.unlink()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Projects API
# ---------------------------------------------------------------------------

@app.route("/api/projects")
def api_projects_list():
    items = list_markdown_dir(PROJECTS_DIR)
    return jsonify(items)


@app.route("/api/projects", methods=["POST"])
def api_projects_create():
    body = request.json or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    # Number based on existing files
    existing = sorted(PROJECTS_DIR.glob("*.md"))
    num = len(existing) + 1
    filename = f"{num}_project.md"
    path = PROJECTS_DIR / filename
    data = {
        "layout": "page",
        "title": title,
        "description": body.get("description", ""),
        "img": body.get("img", ""),
        "importance": body.get("importance", num),
        "category": body.get("category", ""),
        "related_publications": body.get("related_publications", False),
    }
    write_markdown_file(path, {**data, "body": body.get("body", "")})
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/projects/<filename>", methods=["PUT"])
def api_projects_update(filename):
    path = PROJECTS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    body = request.json or {}
    existing = read_markdown_file(path)
    for key in ("title", "description", "img", "importance", "category", "related_publications", "body"):
        if key in body:
            existing[key] = body[key]
    write_markdown_file(path, existing)
    return jsonify({"ok": True})


@app.route("/api/projects/<filename>", methods=["DELETE"])
def api_projects_delete(filename):
    path = PROJECTS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    path.unlink()
    return jsonify({"ok": True})


@app.route("/api/projects/upload-image", methods=["POST"])
def api_projects_upload_image():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    filename = file.filename or "image.jpg"
    dest = REPO_ROOT / "assets" / "img" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    file.save(dest)
    return jsonify({"ok": True, "path": f"assets/img/{filename}"})


# ---------------------------------------------------------------------------
# Books API
# ---------------------------------------------------------------------------

@app.route("/api/books")
def api_books_list():
    items = list_markdown_dir(BOOKS_DIR)
    return jsonify(items)


@app.route("/api/books", methods=["POST"])
def api_books_create():
    body = request.json or {}
    title = (body.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    filename = slugify(title) + ".md"
    path = BOOKS_DIR / filename
    if path.exists():
        return jsonify({"error": f"File '{filename}' already exists"}), 409
    data = {
        "layout": "book-review",
        "title": title,
        "author": body.get("author", ""),
        "cover": body.get("cover", ""),
        "isbn": body.get("isbn", ""),
        "olid": body.get("olid", ""),
        "categories": body.get("categories", ""),
        "tags": body.get("tags", ""),
        "buy_link": body.get("buy_link", ""),
        "started": body.get("started", ""),
        "finished": body.get("finished", ""),
        "released": body.get("released", ""),
        "stars": body.get("stars", ""),
        "status": body.get("status", "Reading"),
    }
    write_markdown_file(path, {**data, "body": body.get("body", "")})
    return jsonify({"ok": True, "filename": filename})


@app.route("/api/books/<filename>", methods=["PUT"])
def api_books_update(filename):
    path = BOOKS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    body = request.json or {}
    existing = read_markdown_file(path)
    for key in ("title", "author", "cover", "isbn", "olid", "categories", "tags",
                "buy_link", "started", "finished", "released", "stars", "status", "body"):
        if key in body:
            existing[key] = body[key]
    write_markdown_file(path, existing)
    return jsonify({"ok": True})


@app.route("/api/books/<filename>", methods=["DELETE"])
def api_books_delete(filename):
    path = BOOKS_DIR / filename
    if not path.exists():
        return jsonify({"error": "Not found"}), 404
    path.unlink()
    return jsonify({"ok": True})


@app.route("/api/books/upload-cover", methods=["POST"])
def api_books_upload_cover():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    filename = file.filename or "cover.jpg"
    BOOK_COVERS_DIR.mkdir(parents=True, exist_ok=True)
    dest = BOOK_COVERS_DIR / filename
    file.save(dest)
    return jsonify({"ok": True, "path": f"assets/img/book_covers/{filename}"})


# ---------------------------------------------------------------------------
# Publications API
# ---------------------------------------------------------------------------

@app.route("/api/publications")
def api_pubs_list():
    entries = read_bib(BIB_PATH)
    return jsonify(entries)


@app.route("/api/publications", methods=["POST"])
def api_pubs_create():
    body = request.json or {}
    key = (body.get("key") or "").strip()
    if not key:
        return jsonify({"error": "Citation key is required"}), 400
    entries = read_bib(BIB_PATH)
    if any(e["key"] == key for e in entries):
        return jsonify({"error": f"Key '{key}' already exists"}), 409
    entry = {
        "entry_type": body.get("entry_type", "article"),
        "key": key,
    }
    for field in ("title", "author", "year", "journal", "booktitle", "abstract",
                  "url", "html", "pdf", "preview", "selected", "month",
                  "volume", "number", "pages", "keywords", "language", "eprint", "primaryClass"):
        if field in body and body[field]:
            entry[field] = str(body[field])
    entries.insert(0, entry)  # newest first
    write_bib(BIB_PATH, entries)
    return jsonify({"ok": True})


@app.route("/api/publications/<key>", methods=["PUT"])
def api_pubs_update(key):
    body = request.json or {}
    entries = read_bib(BIB_PATH)
    idx = next((i for i, e in enumerate(entries) if e["key"] == key), -1)
    if idx == -1:
        return jsonify({"error": "Not found"}), 404
    for field in ("title", "author", "year", "journal", "booktitle", "abstract",
                  "url", "html", "pdf", "preview", "selected", "month",
                  "volume", "number", "pages", "keywords", "language",
                  "eprint", "primaryClass", "entry_type"):
        if field in body:
            if body[field]:
                entries[idx][field] = str(body[field])
            else:
                entries[idx].pop(field, None)
    write_bib(BIB_PATH, entries)
    return jsonify({"ok": True})


@app.route("/api/publications/<key>", methods=["DELETE"])
def api_pubs_delete(key):
    entries = read_bib(BIB_PATH)
    entries = [e for e in entries if e["key"] != key]
    write_bib(BIB_PATH, entries)
    return jsonify({"ok": True})


@app.route("/api/publications/<key>/preview", methods=["POST"])
def api_pubs_upload_preview(key):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    ext = Path(file.filename).suffix if file.filename else ".png"
    dest_name = f"{slugify(key)}{ext}"
    PUB_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    dest = PUB_PREVIEW_DIR / dest_name
    file.save(dest)
    # Update the bib entry
    entries = read_bib(BIB_PATH)
    idx = next((i for i, e in enumerate(entries) if e["key"] == key), -1)
    if idx != -1:
        entries[idx]["preview"] = dest_name
        write_bib(BIB_PATH, entries)
    return jsonify({"ok": True, "preview": dest_name})


@app.route("/api/publications/<key>/pdf", methods=["POST"])
def api_pubs_upload_pdf(key):
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    dest_name = file.filename or f"{slugify(key)}.pdf"
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    dest = PDF_DIR / dest_name
    file.save(dest)
    entries = read_bib(BIB_PATH)
    idx = next((i for i, e in enumerate(entries) if e["key"] == key), -1)
    if idx != -1:
        entries[idx]["pdf"] = dest_name
        write_bib(BIB_PATH, entries)
    return jsonify({"ok": True, "pdf": dest_name})


@app.route("/api/publications/reorder", methods=["POST"])
def api_pubs_reorder():
    body = request.json or {}
    keys = body.get("keys", [])
    if not keys:
        return jsonify({"error": "keys list is required"}), 400
    entries = read_bib(BIB_PATH)
    entry_map = {e["key"]: e for e in entries}
    reordered = []
    for key in keys:
        if key in entry_map:
            reordered.append(entry_map.pop(key))
    # Append any entries not in the keys list (shouldn't happen, but safe)
    reordered.extend(entry_map.values())
    write_bib(BIB_PATH, reordered)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Site Settings API
# ---------------------------------------------------------------------------

@app.route("/api/settings/site")
def api_settings_site():
    text = read_yaml_with_comments(CONFIG_PATH)
    fields = {}
    for key in ("first_name", "middle_name", "last_name", "title", "description",
                "footer_text", "blog_name", "blog_description"):
        fields[key] = read_config_field(text, key)
    return jsonify(fields)


@app.route("/api/settings/site", methods=["PUT"])
def api_settings_site_update():
    body = request.json or {}
    text = read_yaml_with_comments(CONFIG_PATH)
    for key in ("first_name", "middle_name", "last_name", "title", "description",
                "footer_text", "blog_name", "blog_description"):
        if key in body:
            text = update_config_field(text, key, body[key])
    write_yaml_raw(CONFIG_PATH, text)
    return jsonify({"ok": True})


@app.route("/api/settings/about")
def api_settings_about():
    data = read_markdown_file(ABOUT_PATH)
    return jsonify(data)


@app.route("/api/settings/about", methods=["PUT"])
def api_settings_about_update():
    body = request.json or {}
    existing = read_markdown_file(ABOUT_PATH)
    # Update front matter fields
    if "subtitle" in body:
        existing["subtitle"] = body["subtitle"]
    if "body" in body:
        existing["body"] = body["body"]
    if "profile" in body:
        existing["profile"] = body["profile"]
    if "announcements" in body:
        existing["announcements"] = body["announcements"]
    if "latest_posts" in body:
        existing["latest_posts"] = body["latest_posts"]
    if "selected_papers" in body:
        existing["selected_papers"] = body["selected_papers"]
    write_markdown_file(ABOUT_PATH, existing)
    return jsonify({"ok": True})


@app.route("/api/settings/socials")
def api_settings_socials():
    text = read_yaml_with_comments(SOCIALS_PATH)
    # Parse both active and commented-out entries
    socials = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        commented = line.startswith("#")
        clean = line.lstrip("# ").strip()
        if ":" in clean:
            key = clean.split(":")[0].strip()
            val = ":".join(clean.split(":")[1:]).strip()
            # Skip comment-only lines that aren't social entries
            if key in ("this", "the", "can"):
                continue
            socials[key] = {"value": val if not commented else "", "enabled": not commented, "comment_value": val}
    return jsonify(socials)


@app.route("/api/settings/socials", methods=["PUT"])
def api_settings_socials_update():
    body = request.json or {}
    # Rebuild the socials.yml preserving the original structure
    original = read_yaml_with_comments(SOCIALS_PATH)
    lines = original.splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            new_lines.append(line)
            continue
        # Check if this is a social entry (active or commented)
        commented = stripped.startswith("#")
        clean = stripped.lstrip("# ").strip()
        if ":" in clean:
            key = clean.split(":")[0].strip()
            if key in body:
                val = body[key].get("value", "")
                enabled = body[key].get("enabled", False)
                if enabled and val:
                    new_lines.append(f"{key}: {val}")
                elif enabled:
                    new_lines.append(f"{key}:")
                else:
                    comment_val = body[key].get("comment_value", val)
                    new_lines.append(f"# {key}: {comment_val}")
                continue
        new_lines.append(line)
    write_yaml_raw(SOCIALS_PATH, "\n".join(new_lines) + "\n")
    return jsonify({"ok": True})


@app.route("/api/settings/profile-photo", methods=["POST"])
def api_settings_profile_photo():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    file = request.files["file"]
    dest = REPO_ROOT / "assets" / "img" / "prof_pic.jpg"
    file.save(dest)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Photos admin HTML UI
# ---------------------------------------------------------------------------
PHOTOS_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Photos Admin — Feelings</title>
<style>
  :root {
    --bg: #0f0f0f; --bg-raised: #141414; --bg-card: #1a1a1a;
    --border: #2a2a2a; --border-light: #222; --border-row: #1a1a1a;
    --text: #e0e0e0; --text-strong: #fff; --text-muted: #888; --text-faint: #555; --text-faintest: #444;
    --accent: #f3931e; --accent-hover: #f5a83e;
    --input-bg: #0f0f0f;
    --active-bg: #1e1910;
    --hover-bg: #181818;
    --overlay: rgba(0,0,0,0.7);
    --success-bg: rgba(29,185,84,0.12); --success: #1DB954; --success-border: rgba(29,185,84,0.25);
    --error-bg: rgba(224,82,82,0.12); --error: #e05252; --error-border: rgba(224,82,82,0.25);
    --upload-hover-bg: rgba(243,147,30,0.04);
  }
  [data-theme="light"] {
    --bg: #f5f5f5; --bg-raised: #fff; --bg-card: #fff;
    --border: #ddd; --border-light: #e0e0e0; --border-row: #eee;
    --text: #333; --text-strong: #111; --text-muted: #777; --text-faint: #999; --text-faintest: #bbb;
    --input-bg: #fff;
    --active-bg: #fff3e0;
    --hover-bg: #f0f0f0;
    --overlay: rgba(0,0,0,0.5);
    --upload-hover-bg: rgba(243,147,30,0.08);
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; transition: background 0.2s, color 0.2s; }
  header { background: var(--bg-raised); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 1.2rem; font-weight: 600; color: var(--text-strong); }
  header nav { display: flex; align-items: center; gap: 4px; }
  header nav a { color: var(--text-muted); text-decoration: none; font-size: 0.875rem; padding: 4px 10px; border-radius: 6px; transition: color 0.15s, background 0.15s; }
  header nav a:hover { color: var(--text); background: var(--hover-bg); }
  header nav a.active { color: var(--accent); }
  .theme-toggle { margin-left: auto; background: transparent; border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; color: var(--text-muted); font-size: 0.82rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
  .theme-toggle:hover { color: var(--text); border-color: var(--text-faint); }

  .layout { display: flex; height: calc(100vh - 57px); overflow: hidden; }

  /* Left panel */
  .months-panel { width: 280px; flex-shrink: 0; border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
  .panel-top { padding: 14px; border-bottom: 1px solid var(--border); background: var(--bg-raised); }
  .panel-top h2 { font-size: 0.78rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 10px; }
  .new-month-form { display: flex; flex-direction: column; gap: 6px; }
  .new-month-form input, .new-month-form textarea { background: var(--input-bg); border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; color: var(--text); font-size: 0.82rem; outline: none; font-family: inherit; resize: none; transition: border-color 0.15s; }
  .new-month-form input:focus, .new-month-form textarea:focus { border-color: var(--accent); }
  .months-list { flex: 1; overflow-y: auto; }
  .month-row { padding: 11px 14px; border-bottom: 1px solid var(--border-row); cursor: pointer; display: flex; align-items: center; justify-content: space-between; gap: 8px; transition: background 0.1s; }
  .month-row:hover { background: var(--hover-bg); }
  .month-row:hover .drag-handle { opacity: 1; }
  .month-row.active { background: var(--active-bg); border-left: 3px solid var(--accent); }
  .month-row.dragging { opacity: 0.35; }
  .month-row.drag-over-top { box-shadow: inset 0 2px 0 var(--accent); }
  .month-row.drag-over-bottom { box-shadow: inset 0 -2px 0 var(--accent); }
  .drag-handle { color: var(--text-faintest); font-size: 0.9rem; cursor: grab; flex-shrink: 0; user-select: none; opacity: 0; transition: opacity 0.15s; line-height: 1; }
  .drag-handle:active { cursor: grabbing; }
  .month-row-label { font-size: 0.88rem; font-weight: 500; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .month-row-count { font-size: 0.72rem; color: var(--text-faint); margin-top: 2px; }
  .icon-btn { background: transparent; color: var(--text-faint); border: none; padding: 3px 6px; cursor: pointer; border-radius: 3px; font-size: 0.8rem; flex-shrink: 0; transition: color 0.15s; }
  .icon-btn:hover { color: var(--error); }

  /* Right panel */
  .events-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .events-header { padding: 14px 18px; border-bottom: 1px solid var(--border); background: var(--bg-raised); }
  .events-header-top { display: flex; align-items: center; gap: 10px; }
  .events-header h2 { font-size: 0.85rem; font-weight: 600; color: var(--text-strong); text-transform: uppercase; letter-spacing: 0.06em; flex: 1; }
  .btn-sm { background: transparent; border: 1px solid var(--border); border-radius: 5px; padding: 4px 10px; color: var(--text-muted); font-size: 0.78rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; white-space: nowrap; }
  .btn-sm:hover { color: var(--text); border-color: var(--text-faint); }
  .edit-month-form { display: none; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--border-light); flex-direction: column; gap: 6px; }
  .edit-month-form.open { display: flex; }
  .edit-month-form input, .edit-month-form textarea { background: var(--input-bg); border: 1px solid var(--border); border-radius: 6px; padding: 7px 9px; color: var(--text); font-size: 0.82rem; outline: none; font-family: inherit; resize: none; transition: border-color 0.15s; }
  .edit-month-form input:focus, .edit-month-form textarea:focus { border-color: var(--accent); }
  .form-row { display: flex; gap: 6px; }

  .events-body { flex: 1; overflow-y: auto; padding: 18px; }

  /* Add event bar */
  .add-event-bar { display: flex; gap: 8px; margin-bottom: 20px; }
  .add-event-bar input { flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px; color: var(--text); font-size: 0.85rem; outline: none; font-family: inherit; transition: border-color 0.15s; }
  .add-event-bar input:focus { border-color: var(--accent); }

  /* Event card */
  .event-card { background: var(--bg-raised); border: 1px solid var(--border-light); border-radius: 10px; margin-bottom: 16px; overflow: hidden; }
  .event-card-header { display: flex; align-items: center; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--border-row); }
  .event-title-input { flex: 1; background: transparent; border: none; color: var(--text); font-size: 0.88rem; font-family: inherit; outline: none; padding: 2px 0; border-bottom: 1px solid transparent; transition: border-color 0.15s; }
  .event-title-input:focus { border-bottom-color: var(--accent); }
  .event-title-input::placeholder { color: var(--text-faintest); font-style: italic; }
  .event-card-body { padding: 12px 14px; }

  /* Photo grid */
  .photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; margin-bottom: 10px; }
  .photo-card { position: relative; border-radius: 6px; overflow: hidden; background: var(--bg-card); }
  .photo-card img { width: 100%; height: 110px; object-fit: cover; display: block; }
  .photo-card-del { position: absolute; top: 4px; right: 4px; background: var(--overlay); border: none; border-radius: 3px; color: var(--error); padding: 2px 6px; font-size: 0.75rem; cursor: pointer; opacity: 0; transition: opacity 0.15s; }
  .photo-card:hover .photo-card-del { opacity: 1; }
  .photo-card-actions { display: flex; gap: 3px; padding: 4px 6px 0; }
  .photo-card-actions button { flex: 1; background: var(--bg-card); border: 1px solid var(--border); border-radius: 3px; color: var(--text-muted); padding: 3px 0; font-size: 0.68rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; }
  .photo-card-actions button:hover { color: var(--text); border-color: var(--text-faint); }
  .photo-card-actions button:disabled { opacity: 0.3; cursor: not-allowed; }
  .photo-idx-badge { position: absolute; top: 4px; left: 4px; background: rgba(0,0,0,0.6); color: #888; font-size: 0.65rem; padding: 1px 4px; border-radius: 2px; }
  .photo-card-caption { padding: 5px 6px; }
  .photo-card-caption input { width: 100%; background: transparent; border: none; border-bottom: 1px solid transparent; color: var(--text-muted); font-size: 0.75rem; font-family: inherit; outline: none; padding: 2px 0; transition: border-color 0.15s; }
  .photo-card-caption input:focus { border-bottom-color: var(--accent); color: var(--text); }
  .photo-card-caption input::placeholder { color: var(--text-faintest); }
  .photo-date { display: block; font-size: 0.65rem; color: var(--text-faintest); margin-top: 2px; }
  .photo-card.is-hidden { opacity: 0.35; }
  .photo-card.is-hidden .photo-hidden-badge { display: block; }
  .photo-hidden-badge { display: none; position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); background: var(--overlay); color: #fff; font-size: 0.7rem; padding: 2px 8px; border-radius: 4px; pointer-events: none; }
  .photo-card[draggable="true"] { cursor: grab; }
  .photo-card[draggable="true"]:active { cursor: grabbing; }
  .photo-card.dragging { opacity: 0.4; }
  .event-card-body.drag-over { outline: 2px dashed var(--accent); outline-offset: -2px; border-radius: 8px; }

  /* Multi-select */
  .photo-card .select-check { position: absolute; top: 4px; left: 4px; width: 20px; height: 20px; background: var(--overlay); border: 2px solid rgba(255,255,255,0.5); border-radius: 4px; cursor: pointer; z-index: 2; opacity: 0; transition: opacity 0.15s; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 0.75rem; }
  .photo-card:hover .select-check, .photo-card.selected .select-check { opacity: 1; }
  .photo-card.selected .select-check { background: var(--accent); border-color: var(--accent); }
  .photo-card.selected { outline: 2px solid var(--accent); outline-offset: -2px; }
  .photo-card.selected .photo-idx-badge { display: none; }

  /* Bulk action bar */
  .bulk-bar { display: none; position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); background: var(--bg-raised); border: 1px solid var(--border); border-radius: 10px; padding: 8px 14px; z-index: 998; box-shadow: 0 4px 20px rgba(0,0,0,0.4); align-items: center; gap: 10px; }
  .bulk-bar.visible { display: flex; }
  .bulk-bar .bulk-count { font-size: 0.82rem; color: var(--text); font-weight: 600; white-space: nowrap; }
  .bulk-bar button { background: transparent; border: 1px solid var(--border); border-radius: 5px; padding: 5px 12px; color: var(--text-muted); font-size: 0.78rem; cursor: pointer; transition: color 0.15s, border-color 0.15s; white-space: nowrap; }
  .bulk-bar button:hover { color: var(--text); border-color: var(--text-faint); }
  .bulk-bar button.danger { color: var(--error); border-color: var(--error); }
  .bulk-bar button.danger:hover { background: var(--error); color: #fff; }
  .bulk-bar select { background: var(--input-bg); border: 1px solid var(--border); border-radius: 5px; padding: 5px 8px; color: var(--text); font-size: 0.78rem; outline: none; }
  .bulk-bar .bulk-close { background: transparent; border: none; color: var(--text-faint); font-size: 1rem; cursor: pointer; padding: 2px 6px; }

  /* Upload zone (compact, per-event) */
  .event-upload { border: 1px dashed var(--border); border-radius: 6px; padding: 10px; text-align: center; cursor: pointer; transition: border-color 0.15s, background 0.15s; }
  .event-upload:hover, .event-upload.drag-over { border-color: var(--accent); background: var(--upload-hover-bg); }
  .event-upload span { font-size: 0.8rem; color: var(--text-faint); }
  .event-upload input[type="file"] { display: none; }
  .progress-wrap { height: 3px; background: var(--border-light); border-radius: 2px; margin-top: 6px; display: none; }
  .progress-bar { height: 100%; background: var(--accent); border-radius: 2px; width: 0%; transition: width 0.2s; }

  /* Shared */
  .btn-primary { background: var(--accent); color: #000; border: none; border-radius: 6px; padding: 7px 14px; font-size: 0.82rem; font-weight: 600; cursor: pointer; transition: background 0.15s; white-space: nowrap; }
  .btn-primary:hover { background: var(--accent-hover); }
  .btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
  #status { display: none; position: fixed; bottom: 20px; right: 20px; padding: 11px 16px; border-radius: 8px; font-size: 0.85rem; z-index: 999; max-width: 340px; }
  #status.success { background: var(--success-bg); color: var(--success); border: 1px solid var(--success-border); }
  #status.error { background: var(--error-bg); color: var(--error); border: 1px solid var(--error-border); }
  .empty-state { color: var(--text-faintest); text-align: center; padding: 40px; font-size: 0.88rem; }
</style>
</head>
<body>

<header>
  <h1>&#128247; Feelings — Admin</h1>
  <nav>
    <a href="/">Albums</a>
    <a href="/photos" class="active">Photos</a>
    <a href="/news">News</a>
    <a href="/blog">Blog</a>
    <a href="/projects">Projects</a>
    <a href="/books">Books</a>
    <a href="/publications">Pubs</a>
    <a href="/settings">Settings</a>
  </nav>
  <button class="theme-toggle" onclick="toggleTheme()" id="theme-btn">Light</button>
</header>

<div id="status"></div>

<div class="bulk-bar" id="bulk-bar">
  <span class="bulk-count" id="bulk-count">0 selected</span>
  <button onclick="bulkAction('hide')">Hide</button>
  <button onclick="bulkAction('unhide')">Unhide</button>
  <select id="bulk-move-target"><option value="">Move to event...</option></select>
  <button onclick="bulkMove()">Move</button>
  <button class="danger" onclick="bulkAction('delete')">Delete</button>
  <button class="bulk-close" onclick="clearSelection()">&#10005;</button>
</div>

<div class="layout">

  <!-- Left: month list -->
  <div class="months-panel">
    <div class="panel-top">
      <h2>Months</h2>
      <div class="new-month-form">
        <input id="new-id" type="text" placeholder="ID: 2025-03">
        <input id="new-label" type="text" placeholder="Label: March 2025">
        <textarea id="new-desc" rows="2" placeholder="Description (optional)"></textarea>
        <input id="new-playlist" type="text" placeholder="Playlist URL (optional)">
        <button class="btn-primary" onclick="createMonth()">+ New Month</button>
        <button class="btn-sm" style="margin-top:4px;width:100%" onclick="backfillHashes()">Backfill photo hashes</button>
      </div>
    </div>
    <div class="months-list" id="months-list"></div>
  </div>

  <!-- Right: events for selected month -->
  <div class="events-panel">
    <div class="events-header">
      <div class="events-header-top">
        <h2 id="events-heading">Select a month</h2>
        <button class="btn-sm" id="edit-month-btn" onclick="toggleEditMonth()" style="display:none">Edit month</button>
      </div>
      <div class="edit-month-form" id="edit-month-form">
        <input type="text" id="edit-label" placeholder="Month label">
        <textarea id="edit-desc" rows="2" placeholder="Description"></textarea>
        <input type="text" id="edit-playlist" placeholder="Playlist URL (optional)">
        <div class="form-row">
          <button class="btn-primary" onclick="saveEditMonth()">Save</button>
          <button class="btn-sm" onclick="toggleEditMonth()">Cancel</button>
        </div>
      </div>
    </div>
    <div class="events-body" id="events-body">
      <div class="empty-state">Select a month to view its events and photos.</div>
    </div>
  </div>

</div>

<script>
// Theme toggle — persists in localStorage
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('photos-admin-theme', next);
  document.getElementById('theme-btn').textContent = next === 'light' ? 'Dark' : 'Light';
}
(function initTheme() {
  const saved = localStorage.getItem('photos-admin-theme') || 'dark';
  if (saved === 'light') document.documentElement.setAttribute('data-theme', 'light');
  document.getElementById('theme-btn').textContent = saved === 'light' ? 'Dark' : 'Light';
})();

let months = [];
let selectedMonthId = null;

async function loadMonths() {
  const res = await fetch('/api/photos/months');
  months = await res.json();
  renderMonthList();
  if (selectedMonthId) renderEvents(selectedMonthId);
}

// ---- Month list ----
function renderMonthList() {
  const el = document.getElementById('months-list');
  if (!months.length) { el.innerHTML = '<div class="empty-state">No months yet.</div>'; return; }
  el.innerHTML = months.map(m => {
    const photoCount = m.events.reduce((s, e) => s + e.photos.length, 0);
    const hiddenCount = m.events.reduce((s, e) => s + e.photos.filter(p => p.hidden).length, 0);
    const hiddenInfo = hiddenCount > 0 ? ` · ${hiddenCount} hidden` : '';
    return `
      <div class="month-row ${m.id === selectedMonthId ? 'active' : ''}"
           data-month-id="${escHtml(m.id)}"
           draggable="true"
           ondragstart="onMonthDragStart(event, '${escJs(m.id)}')"
           ondragend="onMonthDragEnd(event)"
           ondragover="onMonthDragOver(event)"
           ondragleave="onMonthDragLeave(event)"
           ondrop="onMonthDrop(event)"
           onclick="selectMonth('${escJs(m.id)}')">
        <span class="drag-handle" ondragstart="event.stopPropagation()" onclick="event.stopPropagation()">⠿</span>
        <div style="flex:1;min-width:0">
          <div class="month-row-label">${escHtml(m.month_label)}</div>
          <div class="month-row-count">${m.events.length} event${m.events.length !== 1 ? 's' : ''} · ${photoCount} photo${photoCount !== 1 ? 's' : ''}${hiddenInfo}</div>
        </div>
        <button class="icon-btn" onclick="event.stopPropagation(); deleteMonth('${escJs(m.id)}', '${escJs(m.month_label)}')">&#10005;</button>
      </div>`;
  }).join('');
}

function selectMonth(id) {
  selectedMonthId = id;
  renderMonthList();
  renderEvents(id);
}

// ---- Events panel ----
function renderEvents(id) {
  const month = months.find(m => m.id === id);
  if (!month) return;

  document.getElementById('events-heading').textContent = month.month_label;
  document.getElementById('edit-month-btn').style.display = 'inline-block';
  document.getElementById('edit-label').value = month.month_label;
  document.getElementById('edit-desc').value = month.description || '';
  document.getElementById('edit-playlist').value = month.playlist_url || '';
  document.getElementById('edit-month-form').classList.remove('open');

  const addBar = `
    <div class="add-event-bar">
      <input type="text" id="new-event-title" placeholder="New event title (e.g. John Scofield at the Blue Note)">
      <button class="btn-primary" onclick="addNewEvent()">+ Add Event</button>
    </div>`;

  const eventsHtml = month.events.length === 0
    ? '<div class="empty-state">No events yet — add one above.</div>'
    : month.events.map(e => eventCardHtml(id, e)).join('');

  document.getElementById('events-body').innerHTML = addBar + eventsHtml;
}

function eventCardHtml(monthId, ev) {
  const photoGrid = ev.photos.length === 0
    ? ''
    : `<div class="photo-grid">${ev.photos.map((p, i) => photoCardHtml(monthId, ev.id, p, i, ev.photos.length)).join('')}</div>`;

  const uploadId = `file-${escHtml(ev.id)}`;
  return `
    <div class="event-card">
      <div class="event-card-header">
        <input class="event-title-input" value="${escHtml(ev.title)}" placeholder="(untitled event)"
               onblur="saveEventTitle('${escJs(monthId)}', '${escJs(ev.id)}', this.value)">
        <button class="btn-sm" style="color:#e05252;border-color:#e05252"
                onclick="deleteEvent('${escJs(monthId)}', '${escJs(ev.id)}', '${escJs(ev.title || '(untitled)')}')">Delete event</button>
      </div>
      <div class="event-card-body" data-event-id="${escHtml(ev.id)}" data-month-id="${escHtml(monthId)}"
           ondragover="onEventDragOver(event)" ondragleave="onEventDragLeave(event)" ondrop="onEventDrop(event)">
        ${photoGrid}
        <div class="event-upload" id="zone-${escHtml(ev.id)}"
             onclick="document.getElementById('${uploadId}').click()"
             ondragover="event.preventDefault(); this.classList.add('drag-over')"
             ondragleave="this.classList.remove('drag-over')"
             ondrop="handleDrop(event, '${escJs(monthId)}', '${escJs(ev.id)}')">
          <input type="file" id="${uploadId}" multiple accept="image/*"
                 onchange="handleFiles(this.files, '${escJs(monthId)}', '${escJs(ev.id)}')">
          <span>&#128247; Drop photos or click to upload</span>
          <div class="progress-wrap" id="progress-${escHtml(ev.id)}">
            <div class="progress-bar" id="bar-${escHtml(ev.id)}"></div>
          </div>
        </div>
      </div>
    </div>`;
}

function photoCardHtml(monthId, eventId, photo, idx, total) {
  const thumb = photo.url.replace('/upload/', '/upload/w_280,h_220,c_fill/');
  const dateStr = photo.date_taken ? `<span class="photo-date">${escHtml(photo.date_taken)}</span>` : '';
  const isHidden = photo.hidden;
  const hideLabel = isHidden ? 'Show' : 'Hide';
  const selKey = `${monthId}|${eventId}|${idx}`;
  const isSel = selectedPhotos.has(selKey);
  return `
    <div class="photo-card ${isHidden ? 'is-hidden' : ''} ${isSel ? 'selected' : ''}" draggable="true"
         ondragstart="onPhotoDragStart(event, '${escJs(monthId)}', '${escJs(eventId)}', ${idx})"
         ondragend="onPhotoDragEnd(event)">
      <div class="select-check" onclick="event.stopPropagation(); toggleSelect('${escJs(monthId)}', '${escJs(eventId)}', ${idx}, event)">${isSel ? '&#10003;' : ''}</div>
      <span class="photo-idx-badge">${idx + 1}</span>
      <span class="photo-hidden-badge">Hidden</span>
      <img src="${escHtml(thumb)}" loading="lazy">
      <button class="photo-card-del" onclick="deletePhoto('${escJs(monthId)}', '${escJs(eventId)}', ${idx})">&#10005;</button>
      <div class="photo-card-actions">
        <button ${idx === 0 ? 'disabled' : ''} onclick="movePhoto('${escJs(monthId)}', '${escJs(eventId)}', ${idx}, ${idx - 1})">&#8592;</button>
        <button onclick="toggleHidePhoto('${escJs(monthId)}', '${escJs(eventId)}', ${idx}, ${isHidden ? 'false' : 'true'})">${hideLabel}</button>
        <button ${idx === total - 1 ? 'disabled' : ''} onclick="movePhoto('${escJs(monthId)}', '${escJs(eventId)}', ${idx}, ${idx + 1})">&#8594;</button>
      </div>
      <div class="photo-card-caption">
        <input type="text" value="${escHtml(photo.caption || '')}" placeholder="Caption..."
               onblur="saveCaption('${escJs(monthId)}', '${escJs(eventId)}', ${idx}, this.value)">
        ${dateStr}
      </div>
    </div>`;
}

// ---- Edit month ----
function toggleEditMonth() { document.getElementById('edit-month-form').classList.toggle('open'); }

async function saveEditMonth() {
  const label = document.getElementById('edit-label').value.trim();
  const desc = document.getElementById('edit-desc').value.trim();
  const playlist_url = document.getElementById('edit-playlist').value.trim();
  if (!label) { showStatus('Label cannot be empty', 'error'); return; }
  const res = await fetch(`/api/photos/months/${encodeURIComponent(selectedMonthId)}`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({month_label: label, description: desc, playlist_url}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  document.getElementById('edit-month-form').classList.remove('open');
  showStatus('Month updated', 'success');
  await loadMonths();
}

// ---- Month CRUD ----
async function createMonth() {
  const id = document.getElementById('new-id').value.trim();
  const label = document.getElementById('new-label').value.trim();
  const desc = document.getElementById('new-desc').value.trim();
  const playlist_url = document.getElementById('new-playlist').value.trim();
  if (!id || !label) { showStatus('ID and Label are required', 'error'); return; }
  const res = await fetch('/api/photos/months', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({id, month_label: label, description: desc, playlist_url}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  ['new-id','new-label','new-desc','new-playlist'].forEach(k => document.getElementById(k).value = '');
  showStatus(`Created "${label}"`, 'success');
  await loadMonths();
  selectMonth(id);
}

async function backfillHashes() {
  if (!confirm('Fetch hashes from Cloudinary for all photos missing a hash?')) return;
  showStatus('Backfilling hashes — this may take a moment...', 'success');
  try {
    const res = await fetch('/api/photos/backfill-hashes', {method: 'POST'});
    const d = await res.json();
    if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
    showStatus(`Backfill complete: ${d.updated} updated, ${d.errors} errors`, 'success');
    await loadMonths();
  } catch (e) {
    showStatus('Network error: ' + e.message, 'error');
  }
}

async function deleteMonth(id, label) {
  if (!confirm(`Delete "${label}" and all its photos from Cloudinary?`)) return;
  const res = await fetch(`/api/photos/months/${encodeURIComponent(id)}`, {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  if (selectedMonthId === id) {
    selectedMonthId = null;
    document.getElementById('events-heading').textContent = 'Select a month';
    document.getElementById('events-body').innerHTML = '<div class="empty-state">Select a month to view its events and photos.</div>';
    document.getElementById('edit-month-btn').style.display = 'none';
  }
  showStatus(`Deleted "${label}"`, 'success');
  await loadMonths();
}

// ---- Event CRUD ----
async function addNewEvent() {
  try {
    if (!selectedMonthId) { showStatus('Select a month first', 'error'); return; }
    const titleInput = document.getElementById('new-event-title');
    const title = titleInput ? titleInput.value.trim() : '';
    // Generate a slug-style id: slug from title + short timestamp to avoid collisions
    const slug = title ? title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') : 'event';
    const id = `${slug}-${Date.now().toString(36)}`;
    const res = await fetch(`/api/photos/months/${encodeURIComponent(selectedMonthId)}/events`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({id, title}),
    });
    const d = await res.json();
    if (!res.ok) { showStatus(d.error || 'Failed to create event', 'error'); return; }
    if (titleInput) titleInput.value = '';
    showStatus(title ? `Created "${title}"` : 'Created event', 'success');
    await loadMonths();
  } catch (e) {
    showStatus('Error creating event: ' + e.message, 'error');
  }
}

async function saveEventTitle(monthId, eventId, title) {
  const res = await fetch(`/api/photos/months/${encodeURIComponent(monthId)}/events/${encodeURIComponent(eventId)}`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed to save', 'error');
  else await loadMonths();
}

async function deleteEvent(monthId, eventId, title) {
  if (!confirm(`Delete event "${title}" and all its photos from Cloudinary?`)) return;
  const res = await fetch(`/api/photos/months/${encodeURIComponent(monthId)}/events/${encodeURIComponent(eventId)}`, {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus(`Deleted "${title}"`, 'success');
  await loadMonths();
}

// ---- Photo upload ----
function handleDrop(e, monthId, eventId) {
  e.preventDefault();
  document.getElementById(`zone-${eventId}`).classList.remove('drag-over');
  handleFiles(e.dataTransfer.files, monthId, eventId);
}

async function handleFiles(files, monthId, eventId) {
  if (!files.length) return;
  const total = files.length;
  let succeeded = 0, processed = 0;
  const progressWrap = document.getElementById(`progress-${eventId}`);
  const progressBar = document.getElementById(`bar-${eventId}`);
  if (progressWrap) progressWrap.style.display = 'block';

  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`/api/photos/months/${encodeURIComponent(monthId)}/events/${encodeURIComponent(eventId)}/photos`, {
        method: 'POST', body: formData,
      });
      const d = await res.json();
      if (!res.ok) showStatus(d.error || `Failed: ${file.name}`, 'error');
      else succeeded++;
    } catch (e) { showStatus(`Network error: ${e.message}`, 'error'); }
    processed++;
    if (progressBar) progressBar.style.width = `${(processed / total) * 100}%`;
  }

  if (progressWrap) { progressWrap.style.display = 'none'; }
  if (progressBar) progressBar.style.width = '0%';
  if (succeeded > 0) showStatus(`Uploaded ${succeeded} of ${total} photo${total !== 1 ? 's' : ''}`, 'success');
  await loadMonths();
}

// ---- Photo actions ----
async function saveCaption(monthId, eventId, photoIdx, caption) {
  const res = await fetch(`/api/photos/months/${encodeURIComponent(monthId)}/events/${encodeURIComponent(eventId)}/photos/${photoIdx}`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({caption}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed to save caption', 'error');
}

async function toggleHidePhoto(monthId, eventId, photoIdx, hide) {
  const res = await fetch(`/api/photos/months/${encodeURIComponent(monthId)}/events/${encodeURIComponent(eventId)}/photos/${photoIdx}`, {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({hidden: hide}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus(hide ? 'Photo hidden' : 'Photo visible', 'success');
  await loadMonths();
}

async function deletePhoto(monthId, eventId, photoIdx) {
  if (!confirm('Delete this photo from Cloudinary?')) return;
  const res = await fetch(`/api/photos/months/${encodeURIComponent(monthId)}/events/${encodeURIComponent(eventId)}/photos/${photoIdx}`, {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Photo deleted', 'success');
  await loadMonths();
}

async function movePhoto(monthId, eventId, fromIdx, toIdx) {
  const res = await fetch(`/api/photos/months/${encodeURIComponent(monthId)}/events/${encodeURIComponent(eventId)}/photos/reorder`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({from_index: fromIdx, to_index: toIdx}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  await loadMonths();
}

// ---- Multi-select ----
const selectedPhotos = new Set();  // keys: "monthId|eventId|photoIdx"
let lastClickedKey = null;

function toggleSelect(monthId, eventId, idx, e) {
  const key = `${monthId}|${eventId}|${idx}`;

  if (e && e.shiftKey && lastClickedKey && lastClickedKey !== key) {
    // Shift-click: select range within same event
    const [lm, le, li] = lastClickedKey.split('|');
    if (lm === monthId && le === eventId) {
      const from = Math.min(parseInt(li), idx);
      const to = Math.max(parseInt(li), idx);
      for (let i = from; i <= to; i++) {
        selectedPhotos.add(`${monthId}|${eventId}|${i}`);
      }
    } else {
      selectedPhotos.has(key) ? selectedPhotos.delete(key) : selectedPhotos.add(key);
    }
  } else {
    selectedPhotos.has(key) ? selectedPhotos.delete(key) : selectedPhotos.add(key);
  }

  lastClickedKey = key;
  updateBulkBar();
  renderEvents(selectedMonthId);
}

function clearSelection() {
  selectedPhotos.clear();
  lastClickedKey = null;
  updateBulkBar();
  renderEvents(selectedMonthId);
}

function updateBulkBar() {
  const bar = document.getElementById('bulk-bar');
  const count = selectedPhotos.size;
  if (count === 0) {
    bar.classList.remove('visible');
    return;
  }
  bar.classList.add('visible');
  document.getElementById('bulk-count').textContent = `${count} selected`;

  // Populate move target dropdown with events from current month
  const select = document.getElementById('bulk-move-target');
  const month = months.find(m => m.id === selectedMonthId);
  const opts = '<option value="">Move to event...</option>' +
    (month ? month.events.map(e => `<option value="${escHtml(e.id)}">${escHtml(e.title || e.id)}</option>`).join('') : '');
  select.innerHTML = opts;
}

function getSelectedPhotos() {
  // Convert set to sorted array of {month_id, event_id, photo_idx}
  return Array.from(selectedPhotos).map(key => {
    const [month_id, event_id, photo_idx] = key.split('|');
    return {month_id, event_id, photo_idx: parseInt(photo_idx)};
  });
}

async function bulkAction(action) {
  const items = getSelectedPhotos();
  if (!items.length) return;
  const label = action === 'delete' ? `Delete ${items.length} photo${items.length !== 1 ? 's' : ''} from Cloudinary?`
    : `${action.charAt(0).toUpperCase() + action.slice(1)} ${items.length} photo${items.length !== 1 ? 's' : ''}?`;
  if (!confirm(label)) return;
  try {
    const res = await fetch('/api/photos/bulk-action', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action, photos: items}),
    });
    const d = await res.json();
    if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
    showStatus(`${d.count} photo${d.count !== 1 ? 's' : ''} ${action === 'delete' ? 'deleted' : action === 'hide' ? 'hidden' : 'unhidden'}`, 'success');
    clearSelection();
    await loadMonths();
  } catch (e) {
    showStatus('Error: ' + e.message, 'error');
  }
}

async function bulkMove() {
  const items = getSelectedPhotos();
  if (!items.length) return;
  const dst = document.getElementById('bulk-move-target').value;
  if (!dst) { showStatus('Select a destination event', 'error'); return; }
  if (!confirm(`Move ${items.length} photo${items.length !== 1 ? 's' : ''} to this event?`)) return;
  try {
    const res = await fetch('/api/photos/bulk-action', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({action: 'move', photos: items, dst_event_id: dst}),
    });
    const d = await res.json();
    if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
    showStatus(`Moved ${d.count} photo${d.count !== 1 ? 's' : ''}`, 'success');
    clearSelection();
    await loadMonths();
  } catch (e) {
    showStatus('Error: ' + e.message, 'error');
  }
}

// ---- Drag months to reorder ----
let monthDragSrc = null;

function onMonthDragStart(e, id) {
  monthDragSrc = id;
  e.target.closest('.month-row').classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', id);
}

function onMonthDragEnd(e) {
  monthDragSrc = null;
  document.querySelectorAll('.month-row').forEach(el =>
    el.classList.remove('dragging', 'drag-over-top', 'drag-over-bottom'));
}

function onMonthDragOver(e) {
  if (!monthDragSrc) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  const row = e.target.closest('.month-row');
  if (!row) return;
  document.querySelectorAll('.month-row').forEach(el =>
    el.classList.remove('drag-over-top', 'drag-over-bottom'));
  const rect = row.getBoundingClientRect();
  row.classList.add(e.clientY < rect.top + rect.height / 2 ? 'drag-over-top' : 'drag-over-bottom');
}

function onMonthDragLeave(e) {
  const row = e.target.closest('.month-row');
  if (row && !row.contains(e.relatedTarget))
    row.classList.remove('drag-over-top', 'drag-over-bottom');
}

async function onMonthDrop(e) {
  e.preventDefault();
  const row = e.target.closest('.month-row');
  if (!row || !monthDragSrc) return;
  const targetId = row.dataset.monthId;
  const isTop = row.classList.contains('drag-over-top');
  document.querySelectorAll('.month-row').forEach(el =>
    el.classList.remove('dragging', 'drag-over-top', 'drag-over-bottom'));
  if (targetId === monthDragSrc) return;

  const ids = months.map(m => m.id);
  ids.splice(ids.indexOf(monthDragSrc), 1);
  let targetIdx = ids.indexOf(targetId);
  ids.splice(isTop ? targetIdx : targetIdx + 1, 0, monthDragSrc);
  monthDragSrc = null;

  const res = await fetch('/api/photos/months/reorder', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ordered_ids: ids}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Order saved', 'success');
  await loadMonths();
}

// ---- Drag photos between events ----
let dragData = null;

function onPhotoDragStart(e, monthId, eventId, photoIdx) {
  dragData = {monthId, eventId, photoIdx};
  e.target.closest('.photo-card').classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  // Need to set some data for Firefox
  e.dataTransfer.setData('text/plain', '');
}

function onPhotoDragEnd(e) {
  dragData = null;
  document.querySelectorAll('.photo-card.dragging').forEach(el => el.classList.remove('dragging'));
  document.querySelectorAll('.event-card-body.drag-over').forEach(el => el.classList.remove('drag-over'));
}

function onEventDragOver(e) {
  if (!dragData) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  const body = e.target.closest('.event-card-body');
  if (body) body.classList.add('drag-over');
}

function onEventDragLeave(e) {
  const body = e.target.closest('.event-card-body');
  if (body && !body.contains(e.relatedTarget)) body.classList.remove('drag-over');
}

async function onEventDrop(e) {
  e.preventDefault();
  const body = e.target.closest('.event-card-body');
  if (body) body.classList.remove('drag-over');
  if (!dragData) return;

  const dstEvent = body ? body.dataset.eventId : null;
  const dstMonth = body ? body.dataset.monthId : null;
  if (!dstEvent || !dstMonth) return;
  if (dstEvent === dragData.eventId) return; // same event, ignore

  try {
    const res = await fetch(`/api/photos/months/${encodeURIComponent(dragData.monthId)}/move-photo`, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({src_event: dragData.eventId, dst_event: dstEvent, photo_index: dragData.photoIdx}),
    });
    const d = await res.json();
    if (!res.ok) { showStatus(d.error || 'Failed to move photo', 'error'); return; }
    showStatus('Photo moved', 'success');
    await loadMonths();
  } catch (err) {
    showStatus('Error: ' + err.message, 'error');
  }
  dragData = null;
}

// ---- Utilities ----
function showStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg; el.className = type; el.style.display = 'block';
  clearTimeout(el._t); el._t = setTimeout(() => { el.style.display = 'none'; }, 4000);
}
function escHtml(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escJs(s) { return String(s||'').replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }

loadMonths();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Shared HTML builder for new admin pages
# ---------------------------------------------------------------------------

SHARED_CSS = """
  :root {
    --bg: #0f0f0f; --bg-raised: #141414; --bg-card: #1a1a1a;
    --border: #2a2a2a; --border-light: #222; --border-row: #1e1e1e;
    --text: #e0e0e0; --text-strong: #fff; --text-muted: #999; --text-faint: #666; --text-faintest: #444;
    --input-bg: #1e1e1e;
    --accent: #f3931e; --accent-hover: #e0850a;
    --error: #e05252; --error-bg: rgba(224,82,82,0.1); --error-border: rgba(224,82,82,0.3);
    --success: #4caf50; --success-bg: rgba(76,175,80,0.1); --success-border: rgba(76,175,80,0.3);
    --hover-bg: #1a1a1a; --active-bg: #1f1700;
    --overlay: rgba(0,0,0,0.5);
  }
  [data-theme="light"] {
    --bg: #f5f5f5; --bg-raised: #fff; --bg-card: #fff;
    --border: #ddd; --border-light: #e0e0e0; --border-row: #eee;
    --text: #333; --text-strong: #111; --text-muted: #777; --text-faint: #999; --text-faintest: #bbb;
    --input-bg: #fff; --active-bg: #fff3e0; --hover-bg: #f0f0f0; --overlay: rgba(0,0,0,0.5);
  }
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }
  header { background: var(--bg-raised); border-bottom: 1px solid var(--border); padding: 16px 24px; display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 1.2rem; font-weight: 600; color: var(--text-strong); }
  header nav { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
  header nav a { color: var(--text-muted); text-decoration: none; font-size: 0.82rem; padding: 4px 10px; border-radius: 6px; transition: color 0.15s, background 0.15s; }
  header nav a:hover { color: var(--text); background: var(--hover-bg); }
  header nav a.active { color: var(--accent); font-weight: 600; }
  .theme-toggle { margin-left: auto; background: transparent; border: 1px solid var(--border); border-radius: 6px; padding: 4px 10px; color: var(--text-muted); font-size: 0.82rem; cursor: pointer; }
  .theme-toggle:hover { color: var(--text); border-color: var(--text-faint); }
  .container { max-width: 1000px; margin: 0 auto; padding: 24px; }
  .btn-primary { background: var(--accent); color: #000; border: none; border-radius: 6px; padding: 7px 14px; font-size: 0.82rem; font-weight: 600; cursor: pointer; white-space: nowrap; }
  .btn-primary:hover { background: var(--accent-hover); }
  .btn-sm { background: transparent; border: 1px solid var(--border); border-radius: 5px; padding: 4px 10px; color: var(--text-muted); font-size: 0.78rem; cursor: pointer; white-space: nowrap; }
  .btn-sm:hover { color: var(--text); border-color: var(--text-faint); }
  .btn-danger { color: var(--error); border-color: var(--error); }
  .btn-danger:hover { background: var(--error); color: #fff; }
  #status { display: none; position: fixed; bottom: 20px; right: 20px; padding: 11px 16px; border-radius: 8px; font-size: 0.85rem; z-index: 999; max-width: 340px; }
  #status.success { background: var(--success-bg); color: var(--success); border: 1px solid var(--success-border); display: block; }
  #status.error { background: var(--error-bg); color: var(--error); border: 1px solid var(--error-border); display: block; }
  .card { background: var(--bg-raised); border: 1px solid var(--border-light); border-radius: 10px; margin-bottom: 12px; overflow: hidden; }
  .card-header { display: flex; align-items: center; gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--border-row); cursor: pointer; }
  .card-header:hover { background: var(--hover-bg); }
  .card-body { padding: 14px 16px; display: none; }
  .card-body.open { display: block; }
  .form-group { margin-bottom: 10px; }
  .form-group label { display: block; font-size: 0.75rem; color: var(--text-muted); margin-bottom: 3px; text-transform: uppercase; letter-spacing: 0.04em; }
  .form-group input, .form-group textarea, .form-group select { width: 100%; background: var(--input-bg); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; color: var(--text); font-size: 0.85rem; font-family: inherit; outline: none; }
  .form-group input:focus, .form-group textarea:focus, .form-group select:focus { border-color: var(--accent); }
  .form-group textarea { min-height: 120px; resize: vertical; }
  .form-row { display: flex; gap: 10px; }
  .form-row .form-group { flex: 1; }
  .toggle { display: flex; align-items: center; gap: 6px; font-size: 0.82rem; color: var(--text-muted); cursor: pointer; }
  .toggle input { width: auto; }
  .section-title { font-size: 0.78rem; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; margin: 20px 0 10px; }
  .add-form { background: var(--bg-raised); border: 1px solid var(--border-light); border-radius: 10px; padding: 16px; margin-bottom: 20px; }
  .add-form h2 { font-size: 0.9rem; font-weight: 600; color: var(--text-strong); margin-bottom: 12px; }
  .card-title { font-size: 0.9rem; font-weight: 500; color: var(--text); flex: 1; }
  .card-meta { font-size: 0.75rem; color: var(--text-faint); }
  .card-actions { display: flex; gap: 6px; }
  .badge { font-size: 0.7rem; padding: 2px 6px; border-radius: 3px; background: var(--bg-card); border: 1px solid var(--border); color: var(--text-faint); }
  .badge.active { background: var(--success-bg); color: var(--success); border-color: var(--success-border); }
  .thumb { width: 40px; height: 40px; object-fit: cover; border-radius: 4px; background: var(--border); }
  .empty-state { color: var(--text-faintest); text-align: center; padding: 40px; font-size: 0.88rem; }
"""

SHARED_JS = """
function showStatus(msg, type) {
  const el = document.getElementById('status');
  el.textContent = msg; el.className = type;
  clearTimeout(el._t); el._t = setTimeout(() => { el.className = ''; el.style.display = 'none'; }, 3500);
  el.style.display = 'block';
}

function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
  html.setAttribute('data-theme', next);
  document.getElementById('theme-btn').textContent = next === 'light' ? 'Dark' : 'Light';
  localStorage.setItem('photos-admin-theme', next);
}
(function() {
  const saved = localStorage.getItem('photos-admin-theme');
  if (saved) { document.documentElement.setAttribute('data-theme', saved); }
  document.addEventListener('DOMContentLoaded', () => {
    const t = document.documentElement.getAttribute('data-theme');
    document.getElementById('theme-btn').textContent = t === 'light' ? 'Dark' : 'Light';
  });
})();

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function escJs(s) { return String(s||'').replace(/\\\\/g,'\\\\\\\\').replace(/'/g,"\\\\'"); }

function toggleCard(el) {
  const body = el.nextElementSibling;
  body.classList.toggle('open');
}
"""


def make_page(title, nav_active, body_html, extra_css="", extra_js=""):
    """Generate a full admin page HTML string."""
    nav_items = [
        ("/", "Albums"), ("/photos", "Photos"), ("/news", "News"),
        ("/blog", "Blog"), ("/projects", "Projects"), ("/books", "Books"),
        ("/publications", "Pubs"), ("/settings", "Settings"),
    ]
    nav_html = "\n    ".join(
        f'<a href="{href}" class="active">{label}</a>' if href == nav_active
        else f'<a href="{href}">{label}</a>'
        for href, label in nav_items
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — Admin</title>
<style>{SHARED_CSS}{extra_css}</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <nav>
    {nav_html}
  </nav>
  <button class="theme-toggle" onclick="toggleTheme()" id="theme-btn">Light</button>
</header>
<div id="status"></div>
<div class="container">
{body_html}
</div>
<script>
{SHARED_JS}
{extra_js}
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# News Admin HTML
# ---------------------------------------------------------------------------

NEWS_HTML = make_page("News", "/news", """
<div class="add-form" id="add-form">
  <h2>Add News Item</h2>
  <div class="form-row">
    <div class="form-group"><label>Title (used as filename slug)</label><input id="new-title" placeholder="e.g. NeurIPS 2025"></div>
    <div class="form-group"><label>Date</label><input id="new-date" type="datetime-local"></div>
  </div>
  <div class="form-row">
    <div class="form-group"><label class="toggle"><input type="checkbox" id="new-inline" checked> Inline</label></div>
    <div class="form-group"><label class="toggle"><input type="checkbox" id="new-show" checked> Show</label></div>
  </div>
  <div class="form-group"><label>Body (Markdown)</label><textarea id="new-body" rows="4"></textarea></div>
  <button class="btn-primary" onclick="createNews()">+ Add News</button>
</div>
<div id="news-list"></div>
""", extra_js="""
let allNews = [];

async function loadNews() {
  const res = await fetch('/api/news');
  allNews = await res.json();
  renderNews();
}

function renderNews() {
  const el = document.getElementById('news-list');
  if (!allNews.length) { el.innerHTML = '<div class="empty-state">No news items yet.</div>'; return; }
  el.innerHTML = allNews.map(n => {
    const dateStr = n.date ? String(n.date).substring(0, 16) : '';
    return `
    <div class="card">
      <div class="card-header" onclick="toggleCard(this)">
        <span class="card-title">${escHtml(n.body ? n.body.substring(0, 80) : '(empty)')}</span>
        <span class="card-meta">${escHtml(dateStr)}</span>
        ${n.show ? '<span class="badge active">visible</span>' : '<span class="badge">hidden</span>'}
      </div>
      <div class="card-body">
        <div class="form-row">
          <div class="form-group"><label>Date</label><input value="${escHtml(dateStr)}" onblur="updateNews('${escJs(n.filename)}', 'date', this.value)"></div>
          <div class="form-group"><label class="toggle"><input type="checkbox" ${n.inline ? 'checked' : ''} onchange="updateNews('${escJs(n.filename)}', 'inline', this.checked)"> Inline</label></div>
          <div class="form-group"><label class="toggle"><input type="checkbox" ${n.show ? 'checked' : ''} onchange="updateNews('${escJs(n.filename)}', 'show', this.checked)"> Show</label></div>
        </div>
        <div class="form-group"><label>Body</label><textarea onblur="updateNews('${escJs(n.filename)}', 'body', this.value)">${escHtml(n.body || '')}</textarea></div>
        <div class="card-actions">
          <button class="btn-sm btn-danger" onclick="deleteNews('${escJs(n.filename)}')">Delete</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function createNews() {
  const title = document.getElementById('new-title').value.trim();
  const date = document.getElementById('new-date').value;
  const inline = document.getElementById('new-inline').checked;
  const show = document.getElementById('new-show').checked;
  const body = document.getElementById('new-body').value;
  if (!title) { showStatus('Title is required', 'error'); return; }
  const res = await fetch('/api/news', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, date, inline, show, body}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Created news item', 'success');
  document.getElementById('new-title').value = '';
  document.getElementById('new-body').value = '';
  await loadNews();
}

async function updateNews(filename, field, value) {
  const res = await fetch('/api/news/' + encodeURIComponent(filename), {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[field]: value}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else await loadNews();
}

async function deleteNews(filename) {
  if (!confirm('Delete this news item?')) return;
  const res = await fetch('/api/news/' + encodeURIComponent(filename), {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Deleted', 'success');
  await loadNews();
}

loadNews();
""")


# ---------------------------------------------------------------------------
# Blog Admin HTML
# ---------------------------------------------------------------------------

BLOG_HTML = make_page("Blog Posts", "/blog", """
<div class="add-form" id="add-form">
  <h2>Add Blog Post</h2>
  <div class="form-row">
    <div class="form-group"><label>Title</label><input id="new-title" placeholder="My New Post"></div>
    <div class="form-group"><label>Date</label><input id="new-date" type="datetime-local"></div>
  </div>
  <div class="form-group"><label>Description</label><input id="new-desc" placeholder="A brief description..."></div>
  <div class="form-row">
    <div class="form-group"><label>Tags</label><input id="new-tags" placeholder="tag1, tag2"></div>
    <div class="form-group"><label>Categories</label><input id="new-cats" placeholder="research"></div>
  </div>
  <div class="form-group"><label>Body (Markdown)</label><textarea id="new-body" rows="6"></textarea></div>
  <button class="btn-primary" onclick="createPost()">+ Add Post</button>
</div>
<div id="posts-list"></div>
""", extra_js="""
let allPosts = [];

async function loadPosts() {
  const res = await fetch('/api/posts');
  allPosts = await res.json();
  allPosts.sort((a, b) => String(b.date || '').localeCompare(String(a.date || '')));
  renderPosts();
}

function renderPosts() {
  const el = document.getElementById('posts-list');
  if (!allPosts.length) { el.innerHTML = '<div class="empty-state">No blog posts yet.</div>'; return; }
  el.innerHTML = allPosts.map(p => {
    const pub = p.published !== false;
    return `
    <div class="card">
      <div class="card-header" onclick="toggleCard(this)">
        <span class="card-title">${escHtml(p.title || p.filename)}</span>
        <span class="card-meta">${escHtml(String(p.date || '').substring(0, 10))}</span>
        ${pub ? '<span class="badge active">published</span>' : '<span class="badge">draft</span>'}
      </div>
      <div class="card-body">
        <div class="form-row">
          <div class="form-group"><label>Title</label><input value="${escHtml(p.title || '')}" onblur="updatePost('${escJs(p.filename)}', 'title', this.value)"></div>
          <div class="form-group"><label>Date</label><input value="${escHtml(String(p.date || '').substring(0, 16))}" onblur="updatePost('${escJs(p.filename)}', 'date', this.value)"></div>
        </div>
        <div class="form-group"><label>Description</label><input value="${escHtml(p.description || '')}" onblur="updatePost('${escJs(p.filename)}', 'description', this.value)"></div>
        <div class="form-row">
          <div class="form-group"><label>Tags</label><input value="${escHtml(p.tags || '')}" onblur="updatePost('${escJs(p.filename)}', 'tags', this.value)"></div>
          <div class="form-group"><label>Categories</label><input value="${escHtml(p.categories || '')}" onblur="updatePost('${escJs(p.filename)}', 'categories', this.value)"></div>
        </div>
        <div class="form-group"><label class="toggle"><input type="checkbox" ${pub ? 'checked' : ''} onchange="updatePost('${escJs(p.filename)}', 'published', this.checked)"> Published</label></div>
        <div class="form-group"><label>Body</label><textarea rows="10" onblur="updatePost('${escJs(p.filename)}', 'body', this.value)">${escHtml(p.body || '')}</textarea></div>
        <div class="card-actions">
          <button class="btn-sm btn-danger" onclick="deletePost('${escJs(p.filename)}')">Delete</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function createPost() {
  const title = document.getElementById('new-title').value.trim();
  const date = document.getElementById('new-date').value;
  const description = document.getElementById('new-desc').value.trim();
  const tags = document.getElementById('new-tags').value.trim();
  const categories = document.getElementById('new-cats').value.trim();
  const body = document.getElementById('new-body').value;
  if (!title || !date) { showStatus('Title and date are required', 'error'); return; }
  const res = await fetch('/api/posts', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, date, description, tags, categories, body, published: true}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Post created', 'success');
  ['new-title','new-date','new-desc','new-tags','new-cats','new-body'].forEach(id => document.getElementById(id).value = '');
  await loadPosts();
}

async function updatePost(filename, field, value) {
  const res = await fetch('/api/posts/' + encodeURIComponent(filename), {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[field]: value}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else await loadPosts();
}

async function deletePost(filename) {
  if (!confirm('Delete this blog post?')) return;
  const res = await fetch('/api/posts/' + encodeURIComponent(filename), {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Deleted', 'success');
  await loadPosts();
}

loadPosts();
""")


# ---------------------------------------------------------------------------
# Projects Admin HTML
# ---------------------------------------------------------------------------

PROJECTS_HTML = make_page("Projects", "/projects", """
<div class="add-form">
  <h2>Add Project</h2>
  <div class="form-row">
    <div class="form-group"><label>Title</label><input id="new-title" placeholder="My Project"></div>
    <div class="form-group"><label>Category</label><input id="new-cat" placeholder="work"></div>
    <div class="form-group"><label>Importance</label><input id="new-imp" type="number" value="1"></div>
  </div>
  <div class="form-group"><label>Description</label><input id="new-desc" placeholder="Brief description"></div>
  <div class="form-group"><label>Body (Markdown)</label><textarea id="new-body" rows="4"></textarea></div>
  <button class="btn-primary" onclick="createProject()">+ Add Project</button>
</div>
<div id="projects-list"></div>
""", extra_js="""
let allProjects = [];

async function loadProjects() {
  const res = await fetch('/api/projects');
  allProjects = await res.json();
  allProjects.sort((a, b) => (a.importance || 99) - (b.importance || 99));
  renderProjects();
}

function renderProjects() {
  const el = document.getElementById('projects-list');
  if (!allProjects.length) { el.innerHTML = '<div class="empty-state">No projects yet.</div>'; return; }
  el.innerHTML = allProjects.map(p => `
    <div class="card">
      <div class="card-header" onclick="toggleCard(this)">
        ${p.img ? '<img class="thumb" src="/' + escHtml(p.img) + '" onerror="this.style.display=\\'none\\'">' : ''}
        <span class="card-title">${escHtml(p.title || p.filename)}</span>
        <span class="badge">${escHtml(p.category || '')}</span>
        <span class="card-meta">#${p.importance || '?'}</span>
      </div>
      <div class="card-body">
        <div class="form-row">
          <div class="form-group"><label>Title</label><input value="${escHtml(p.title || '')}" onblur="updateProject('${escJs(p.filename)}', 'title', this.value)"></div>
          <div class="form-group"><label>Category</label><input value="${escHtml(p.category || '')}" onblur="updateProject('${escJs(p.filename)}', 'category', this.value)"></div>
          <div class="form-group"><label>Importance</label><input type="number" value="${p.importance || ''}" onblur="updateProject('${escJs(p.filename)}', 'importance', parseInt(this.value))"></div>
        </div>
        <div class="form-group"><label>Description</label><input value="${escHtml(p.description || '')}" onblur="updateProject('${escJs(p.filename)}', 'description', this.value)"></div>
        <div class="form-group"><label>Image path</label><input value="${escHtml(p.img || '')}" onblur="updateProject('${escJs(p.filename)}', 'img', this.value)"></div>
        <div class="form-group"><label>Upload Image</label><input type="file" accept="image/*" onchange="uploadProjectImage(this.files[0], '${escJs(p.filename)}', this)"></div>
        <div class="form-group"><label class="toggle"><input type="checkbox" ${p.related_publications ? 'checked' : ''} onchange="updateProject('${escJs(p.filename)}', 'related_publications', this.checked)"> Related publications</label></div>
        <div class="form-group"><label>Body</label><textarea rows="8" onblur="updateProject('${escJs(p.filename)}', 'body', this.value)">${escHtml(p.body || '')}</textarea></div>
        <div class="card-actions">
          <button class="btn-sm btn-danger" onclick="deleteProject('${escJs(p.filename)}')">Delete</button>
        </div>
      </div>
    </div>
  `).join('');
}

async function createProject() {
  const title = document.getElementById('new-title').value.trim();
  const category = document.getElementById('new-cat').value.trim();
  const importance = parseInt(document.getElementById('new-imp').value) || 1;
  const description = document.getElementById('new-desc').value.trim();
  const body = document.getElementById('new-body').value;
  if (!title) { showStatus('Title is required', 'error'); return; }
  const res = await fetch('/api/projects', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, category, importance, description, body}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Project created', 'success');
  ['new-title','new-cat','new-desc','new-body'].forEach(id => document.getElementById(id).value = '');
  await loadProjects();
}

async function updateProject(filename, field, value) {
  const res = await fetch('/api/projects/' + encodeURIComponent(filename), {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[field]: value}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else await loadProjects();
}

async function uploadProjectImage(file, filename, inputEl) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/projects/upload-image', {method: 'POST', body: formData});
  const d = await res.json();
  if (inputEl) inputEl.value = '';
  if (!res.ok) { showStatus(d.error || 'Upload failed', 'error'); return; }
  await updateProject(filename, 'img', d.path);
  showStatus('Image uploaded', 'success');
}

async function deleteProject(filename) {
  if (!confirm('Delete this project?')) return;
  const res = await fetch('/api/projects/' + encodeURIComponent(filename), {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Deleted', 'success');
  await loadProjects();
}

loadProjects();
""")


# ---------------------------------------------------------------------------
# Books Admin HTML
# ---------------------------------------------------------------------------

BOOKS_HTML = make_page("Books", "/books", """
<div class="add-form">
  <h2>Add Book Review</h2>
  <div class="form-row">
    <div class="form-group"><label>Title</label><input id="new-title" placeholder="The Great Gatsby"></div>
    <div class="form-group"><label>Author</label><input id="new-author" placeholder="F. Scott Fitzgerald"></div>
  </div>
  <div class="form-row">
    <div class="form-group"><label>Stars (1-5)</label><input id="new-stars" type="number" min="1" max="5"></div>
    <div class="form-group"><label>Status</label><select id="new-status"><option>Reading</option><option>Finished</option><option>Abandoned</option></select></div>
    <div class="form-group"><label>Released (year)</label><input id="new-released" type="number"></div>
  </div>
  <div class="form-group"><label>Body (Review markdown)</label><textarea id="new-body" rows="4"></textarea></div>
  <button class="btn-primary" onclick="createBook()">+ Add Book</button>
</div>
<div id="books-list"></div>
""", extra_js="""
let allBooks = [];

async function loadBooks() {
  const res = await fetch('/api/books');
  allBooks = await res.json();
  renderBooks();
}

function starsHtml(n) { return '★'.repeat(n || 0) + '☆'.repeat(5 - (n || 0)); }

function renderBooks() {
  const el = document.getElementById('books-list');
  if (!allBooks.length) { el.innerHTML = '<div class="empty-state">No book reviews yet.</div>'; return; }
  el.innerHTML = allBooks.map(b => `
    <div class="card">
      <div class="card-header" onclick="toggleCard(this)">
        ${b.cover ? '<img class="thumb" src="/' + escHtml(b.cover) + '" onerror="this.style.display=\\'none\\'">' : ''}
        <span class="card-title">${escHtml(b.title || b.filename)}</span>
        <span class="card-meta">${escHtml(b.author || '')}</span>
        <span class="card-meta" style="color:var(--accent)">${starsHtml(b.stars)}</span>
        <span class="badge">${escHtml(b.status || '')}</span>
      </div>
      <div class="card-body">
        <div class="form-row">
          <div class="form-group"><label>Title</label><input value="${escHtml(b.title || '')}" onblur="updateBook('${escJs(b.filename)}', 'title', this.value)"></div>
          <div class="form-group"><label>Author</label><input value="${escHtml(b.author || '')}" onblur="updateBook('${escJs(b.filename)}', 'author', this.value)"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>Stars</label><input type="number" min="1" max="5" value="${b.stars || ''}" onblur="updateBook('${escJs(b.filename)}', 'stars', parseInt(this.value))"></div>
          <div class="form-group"><label>Status</label><select onchange="updateBook('${escJs(b.filename)}', 'status', this.value)">
            <option ${b.status === 'Reading' ? 'selected' : ''}>Reading</option>
            <option ${b.status === 'Finished' ? 'selected' : ''}>Finished</option>
            <option ${b.status === 'Abandoned' ? 'selected' : ''}>Abandoned</option>
          </select></div>
          <div class="form-group"><label>Released</label><input type="number" value="${b.released || ''}" onblur="updateBook('${escJs(b.filename)}', 'released', this.value)"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>Started</label><input type="date" value="${escHtml(String(b.started || ''))}" onblur="updateBook('${escJs(b.filename)}', 'started', this.value)"></div>
          <div class="form-group"><label>Finished</label><input type="date" value="${escHtml(String(b.finished || ''))}" onblur="updateBook('${escJs(b.filename)}', 'finished', this.value)"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>ISBN</label><input value="${escHtml(b.isbn || '')}" onblur="updateBook('${escJs(b.filename)}', 'isbn', this.value)"></div>
          <div class="form-group"><label>OLID</label><input value="${escHtml(b.olid || '')}" onblur="updateBook('${escJs(b.filename)}', 'olid', this.value)"></div>
        </div>
        <div class="form-group"><label>Cover path</label><input value="${escHtml(b.cover || '')}" onblur="updateBook('${escJs(b.filename)}', 'cover', this.value)"></div>
        <div class="form-group"><label>Upload Cover</label><input type="file" accept="image/*" onchange="uploadBookCover(this.files[0], '${escJs(b.filename)}', this)"></div>
        <div class="form-group"><label>Buy Link</label><input value="${escHtml(b.buy_link || '')}" onblur="updateBook('${escJs(b.filename)}', 'buy_link', this.value)"></div>
        <div class="form-row">
          <div class="form-group"><label>Categories</label><input value="${escHtml(b.categories || '')}" onblur="updateBook('${escJs(b.filename)}', 'categories', this.value)"></div>
          <div class="form-group"><label>Tags</label><input value="${escHtml(b.tags || '')}" onblur="updateBook('${escJs(b.filename)}', 'tags', this.value)"></div>
        </div>
        <div class="form-group"><label>Body</label><textarea rows="8" onblur="updateBook('${escJs(b.filename)}', 'body', this.value)">${escHtml(b.body || '')}</textarea></div>
        <div class="card-actions">
          <button class="btn-sm btn-danger" onclick="deleteBook('${escJs(b.filename)}')">Delete</button>
        </div>
      </div>
    </div>
  `).join('');
}

async function createBook() {
  const title = document.getElementById('new-title').value.trim();
  const author = document.getElementById('new-author').value.trim();
  const stars = parseInt(document.getElementById('new-stars').value) || '';
  const status = document.getElementById('new-status').value;
  const released = document.getElementById('new-released').value;
  const body = document.getElementById('new-body').value;
  if (!title) { showStatus('Title is required', 'error'); return; }
  const res = await fetch('/api/books', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title, author, stars, status, released, body}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Book added', 'success');
  ['new-title','new-author','new-stars','new-released','new-body'].forEach(id => document.getElementById(id).value = '');
  await loadBooks();
}

async function updateBook(filename, field, value) {
  const res = await fetch('/api/books/' + encodeURIComponent(filename), {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[field]: value}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else await loadBooks();
}

async function uploadBookCover(file, filename, inputEl) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/books/upload-cover', {method: 'POST', body: formData});
  const d = await res.json();
  if (inputEl) inputEl.value = '';
  if (!res.ok) { showStatus(d.error || 'Upload failed', 'error'); return; }
  await updateBook(filename, 'cover', d.path);
  showStatus('Cover uploaded', 'success');
}

async function deleteBook(filename) {
  if (!confirm('Delete this book review?')) return;
  const res = await fetch('/api/books/' + encodeURIComponent(filename), {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Deleted', 'success');
  await loadBooks();
}

loadBooks();
""")


# ---------------------------------------------------------------------------
# Publications Admin HTML
# ---------------------------------------------------------------------------

PUBS_HTML = make_page("Publications", "/publications", """
<div class="add-form">
  <h2>Add Publication</h2>
  <div class="form-row">
    <div class="form-group"><label>Citation Key</label><input id="new-key" placeholder="AuthorYear-xx"></div>
    <div class="form-group"><label>Type</label><select id="new-type"><option value="article">Article</option><option value="inproceedings">Conference</option></select></div>
    <div class="form-group"><label>Year</label><input id="new-year" type="number"></div>
  </div>
  <div class="form-group"><label>Title</label><input id="new-title"></div>
  <div class="form-group"><label>Authors</label><input id="new-author" placeholder="Last, First and Last, First"></div>
  <div class="form-row">
    <div class="form-group"><label>Journal / Booktitle</label><input id="new-venue"></div>
    <div class="form-group"><label>URL</label><input id="new-url"></div>
  </div>
  <div class="form-group"><label>Abstract</label><textarea id="new-abstract" rows="3"></textarea></div>
  <div class="form-group"><label class="toggle"><input type="checkbox" id="new-selected"> Selected (show on about page)</label></div>
  <button class="btn-primary" onclick="createPub()">+ Add Publication</button>
</div>
<div id="pubs-list"></div>
""", extra_css="""
  .pub-preview { width: 60px; height: 60px; object-fit: contain; border-radius: 4px; background: var(--bg-card); }
  .reorder-btns { display: flex; flex-direction: column; gap: 2px; flex-shrink: 0; }
  .reorder-btns button { padding: 1px 6px; font-size: 0.6rem; line-height: 1; }
""", extra_js="""
let allPubs = [];

async function loadPubs() {
  const res = await fetch('/api/publications');
  if (!res.ok) { const d = await res.json(); showStatus(d.error || 'Failed to load', 'error'); return; }
  allPubs = await res.json();
  renderPubs();
}

function renderPubs() {
  const el = document.getElementById('pubs-list');
  if (!allPubs.length) { el.innerHTML = '<div class="empty-state">No publications yet.</div>'; return; }
  el.innerHTML = allPubs.map((p, i) => {
    const sel = p.selected && (p.selected === 'true' || p.selected === '{true}' || p.selected === true);
    return `
    <div class="card" data-pub-key="${escHtml(p.key)}">
      <div class="card-header" onclick="toggleCard(this)">
        <div class="reorder-btns" onclick="event.stopPropagation()">
          <button class="btn-sm" ${i === 0 ? 'disabled' : ''} onclick="movePub(${i}, ${i - 1})" title="Move up">&#9650;</button>
          <button class="btn-sm" ${i === allPubs.length - 1 ? 'disabled' : ''} onclick="movePub(${i}, ${i + 1})" title="Move down">&#9660;</button>
        </div>
        ${p.preview ? '<img class="pub-preview" src="/assets/img/publication_preview/' + escHtml(p.preview.replace(/[{}]/g, '')) + '">' : ''}
        <div style="flex:1;min-width:0">
          <span class="card-title" style="display:block">${escHtml(p.title || p.key)}</span>
          <span class="card-meta">${escHtml(p.author ? p.author.substring(0, 80) : '')}</span>
        </div>
        <span class="card-meta">${escHtml(p.year || '')}</span>
        ${sel ? '<span class="badge active">selected</span>' : ''}
      </div>
      <div class="card-body">
        <div class="form-row">
          <div class="form-group"><label>Key</label><input value="${escHtml(p.key)}" disabled></div>
          <div class="form-group"><label>Type</label><select onchange="updatePub('${escJs(p.key)}', 'entry_type', this.value)">
            <option value="article" ${p.entry_type === 'article' ? 'selected' : ''}>Article</option>
            <option value="inproceedings" ${p.entry_type === 'inproceedings' ? 'selected' : ''}>Conference</option>
          </select></div>
          <div class="form-group"><label>Year</label><input value="${escHtml(p.year || '')}" onblur="updatePub('${escJs(p.key)}', 'year', this.value)"></div>
        </div>
        <div class="form-group"><label>Title</label><input value="${escHtml(p.title || '')}" onblur="updatePub('${escJs(p.key)}', 'title', this.value)"></div>
        <div class="form-group"><label>Authors</label><input value="${escHtml(p.author || '')}" onblur="updatePub('${escJs(p.key)}', 'author', this.value)"></div>
        <div class="form-row">
          <div class="form-group"><label>Journal</label><input value="${escHtml(p.journal || '')}" onblur="updatePub('${escJs(p.key)}', 'journal', this.value)"></div>
          <div class="form-group"><label>Booktitle</label><input value="${escHtml(p.booktitle || '')}" onblur="updatePub('${escJs(p.key)}', 'booktitle', this.value)"></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>URL</label><input value="${escHtml(p.url || '')}" onblur="updatePub('${escJs(p.key)}', 'url', this.value)"></div>
          <div class="form-group"><label>HTML</label><input value="${escHtml(p.html || '')}" onblur="updatePub('${escJs(p.key)}', 'html', this.value)"></div>
        </div>
        <div class="form-group"><label>Abstract</label><textarea rows="4" onblur="updatePub('${escJs(p.key)}', 'abstract', this.value)">${escHtml(p.abstract || '')}</textarea></div>
        <div class="form-row">
          <div class="form-group"><label>PDF filename</label><div style="display:flex;gap:6px;align-items:center"><input style="flex:1" value="${escHtml((p.pdf || '').replace(/[{}]/g, ''))}" onblur="updatePub('${escJs(p.key)}', 'pdf', this.value)">${p.pdf ? `<button class="btn-sm btn-danger" onclick="removePubFile('${escJs(p.key)}', 'pdf')" title="Remove PDF">✕</button>` : ''}</div></div>
          <div class="form-group"><label>Preview filename</label><div style="display:flex;gap:6px;align-items:center"><input style="flex:1" value="${escHtml((p.preview || '').replace(/[{}]/g, ''))}" onblur="updatePub('${escJs(p.key)}', 'preview', this.value)">${p.preview ? `<button class="btn-sm btn-danger" onclick="removePubFile('${escJs(p.key)}', 'preview')" title="Remove preview">✕</button>` : ''}</div></div>
        </div>
        <div class="form-row">
          <div class="form-group"><label>Upload Preview Image</label><input type="file" accept="image/*" onchange="uploadPubFile('${escJs(p.key)}', 'preview', this.files[0], this)"></div>
          <div class="form-group"><label>Upload PDF</label><input type="file" accept=".pdf" onchange="uploadPubFile('${escJs(p.key)}', 'pdf', this.files[0], this)"></div>
        </div>
        <div class="form-group"><label class="toggle"><input type="checkbox" ${sel ? 'checked' : ''} onchange="updatePub('${escJs(p.key)}', 'selected', this.checked ? 'true' : '')"> Selected (show on about page)</label></div>
        <div class="card-actions">
          <button class="btn-sm btn-danger" onclick="deletePub('${escJs(p.key)}')">Delete</button>
        </div>
      </div>
    </div>`;
  }).join('');
}

async function createPub() {
  const key = document.getElementById('new-key').value.trim();
  const entry_type = document.getElementById('new-type').value;
  const year = document.getElementById('new-year').value;
  const title = document.getElementById('new-title').value.trim();
  const author = document.getElementById('new-author').value.trim();
  const venue = document.getElementById('new-venue').value.trim();
  const url = document.getElementById('new-url').value.trim();
  const abstract = document.getElementById('new-abstract').value.trim();
  const selected = document.getElementById('new-selected').checked;
  if (!key) { showStatus('Citation key is required', 'error'); return; }
  const data = {key, entry_type, year, title, author, abstract, url, html: url};
  if (entry_type === 'article') data.journal = venue;
  else data.booktitle = venue;
  if (selected) data.selected = 'true';
  const res = await fetch('/api/publications', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Publication added', 'success');
  ['new-key','new-year','new-title','new-author','new-venue','new-url','new-abstract'].forEach(id => document.getElementById(id).value = '');
  await loadPubs();
}

async function updatePub(key, field, value) {
  const res = await fetch('/api/publications/' + encodeURIComponent(key), {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({[field]: value}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else await loadPubs();
}

async function uploadPubFile(key, type, file, inputEl) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/publications/' + encodeURIComponent(key) + '/' + type, {method: 'POST', body: formData});
  const d = await res.json();
  if (inputEl) inputEl.value = '';
  if (!res.ok) { showStatus(d.error || 'Upload failed', 'error'); return; }
  showStatus(type + ' uploaded', 'success');
  await loadPubs();
}

async function removePubFile(key, field) {
  if (!confirm('Remove ' + field + ' from this publication?')) return;
  await updatePub(key, field, '');
  showStatus(field + ' removed', 'success');
  await loadPubs();
}

async function deletePub(key) {
  if (!confirm('Delete this publication?')) return;
  const res = await fetch('/api/publications/' + encodeURIComponent(key), {method: 'DELETE'});
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed', 'error'); return; }
  showStatus('Deleted', 'success');
  await loadPubs();
}

async function movePub(fromIdx, toIdx) {
  if (toIdx < 0 || toIdx >= allPubs.length) return;
  const item = allPubs.splice(fromIdx, 1)[0];
  allPubs.splice(toIdx, 0, item);
  renderPubs();
  const keys = allPubs.map(p => p.key);
  const res = await fetch('/api/publications/reorder', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({keys}),
  });
  const d = await res.json();
  if (!res.ok) { showStatus(d.error || 'Failed to reorder', 'error'); await loadPubs(); }
}

loadPubs();
""")


# ---------------------------------------------------------------------------
# Site Settings Admin HTML
# ---------------------------------------------------------------------------

SETTINGS_HTML = make_page("Site Settings", "/settings", """
<div class="section-title">Site Identity</div>
<div class="add-form" id="site-form">
  <div class="form-row">
    <div class="form-group"><label>First Name</label><input id="cfg-first_name"></div>
    <div class="form-group"><label>Middle Name</label><input id="cfg-middle_name"></div>
    <div class="form-group"><label>Last Name</label><input id="cfg-last_name"></div>
  </div>
  <div class="form-group"><label>Site Title</label><input id="cfg-title"></div>
  <div class="form-group"><label>Description</label><textarea id="cfg-description" rows="2"></textarea></div>
  <div class="form-group"><label>Footer Text</label><textarea id="cfg-footer_text" rows="2"></textarea></div>
  <button class="btn-primary" onclick="saveSiteConfig()">Save Site Config</button>
</div>

<div class="section-title">About Page</div>
<div class="add-form" id="about-form">
  <div class="form-group"><label>Subtitle</label><input id="about-subtitle"></div>
  <div class="form-group"><label>Profile Photo</label>
    <div style="display:flex;gap:12px;align-items:center">
      <img id="profile-preview" src="/assets/img/prof_pic.jpg" style="width:80px;height:80px;border-radius:8px;object-fit:cover;background:var(--border)">
      <input type="file" accept="image/*" onchange="uploadProfilePhoto(this.files[0], this)">
    </div>
  </div>
  <div class="form-group"><label>Bio (Markdown body)</label><textarea id="about-body" rows="6"></textarea></div>
  <button class="btn-primary" onclick="saveAbout()">Save About Page</button>
</div>

<div class="section-title">Social Links</div>
<div class="add-form" id="socials-form">
  <div id="socials-list"></div>
  <button class="btn-primary" onclick="saveSocials()" style="margin-top:10px">Save Social Links</button>
</div>
""", extra_css="""
  .social-row { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
  .social-row label { font-size: 0.8rem; color: var(--text-muted); width: 160px; flex-shrink: 0; }
  .social-row input[type="text"] { flex: 1; background: var(--input-bg); border: 1px solid var(--border); border-radius: 5px; padding: 5px 8px; color: var(--text); font-size: 0.82rem; outline: none; }
  .social-row input[type="text"]:focus { border-color: var(--accent); }
  .social-row input[type="checkbox"] { width: auto; }
""", extra_js="""
let siteConfig = {};
let aboutData = {};
let socialsData = {};

async function loadSettings() {
  const [siteRes, aboutRes, socialsRes] = await Promise.all([
    fetch('/api/settings/site'),
    fetch('/api/settings/about'),
    fetch('/api/settings/socials'),
  ]);
  siteConfig = await siteRes.json();
  aboutData = await aboutRes.json();
  socialsData = await socialsRes.json();
  renderSettings();
}

function renderSettings() {
  // Site config
  for (const key of ['first_name', 'middle_name', 'last_name', 'title', 'description', 'footer_text']) {
    const el = document.getElementById('cfg-' + key);
    if (el) el.value = siteConfig[key] || '';
  }
  // About
  document.getElementById('about-subtitle').value = aboutData.subtitle || '';
  document.getElementById('about-body').value = aboutData.body || '';
  // Socials
  const el = document.getElementById('socials-list');
  const keys = Object.keys(socialsData).sort();
  el.innerHTML = keys.map(key => {
    const s = socialsData[key];
    return `<div class="social-row">
      <input type="checkbox" data-key="${escHtml(key)}" ${s.enabled ? 'checked' : ''}>
      <label>${escHtml(key)}</label>
      <input type="text" data-key="${escHtml(key)}" value="${escHtml(s.value || s.comment_value || '')}">
    </div>`;
  }).join('');
}

async function saveSiteConfig() {
  const data = {};
  for (const key of ['first_name', 'middle_name', 'last_name', 'title', 'description', 'footer_text']) {
    data[key] = document.getElementById('cfg-' + key).value;
  }
  const res = await fetch('/api/settings/site', {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else showStatus('Site config saved', 'success');
}

async function saveAbout() {
  const subtitle = document.getElementById('about-subtitle').value;
  const body = document.getElementById('about-body').value;
  const res = await fetch('/api/settings/about', {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({subtitle, body}),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else showStatus('About page saved', 'success');
}

async function uploadProfilePhoto(file, inputEl) {
  if (!file) return;
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch('/api/settings/profile-photo', {method: 'POST', body: formData});
  const d = await res.json();
  if (inputEl) inputEl.value = '';
  if (!res.ok) { showStatus(d.error || 'Upload failed', 'error'); return; }
  document.getElementById('profile-preview').src = '/assets/img/prof_pic.jpg?' + Date.now();
  showStatus('Profile photo updated', 'success');
}

async function saveSocials() {
  const data = {};
  const checkboxes = document.querySelectorAll('#socials-list input[type="checkbox"]');
  checkboxes.forEach(cb => {
    const key = cb.dataset.key;
    const input = document.querySelector('#socials-list input[type="text"][data-key="' + key + '"]');
    data[key] = {
      value: input ? input.value : '',
      enabled: cb.checked,
      comment_value: input ? input.value : '',
    };
  });
  const res = await fetch('/api/settings/socials', {
    method: 'PUT', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  });
  const d = await res.json();
  if (!res.ok) showStatus(d.error || 'Failed', 'error');
  else showStatus('Social links saved', 'success');
}

loadSettings();
""")


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@app.route("/photos")
def photos_admin():
    return Response(PHOTOS_HTML, mimetype="text/html")


@app.route("/news")
def news_admin():
    return Response(NEWS_HTML, mimetype="text/html")


@app.route("/blog")
def blog_admin():
    return Response(BLOG_HTML, mimetype="text/html")


@app.route("/projects")
def projects_admin():
    return Response(PROJECTS_HTML, mimetype="text/html")


@app.route("/books")
def books_admin():
    return Response(BOOKS_HTML, mimetype="text/html")


@app.route("/publications")
def pubs_admin():
    return Response(PUBS_HTML, mimetype="text/html")


@app.route("/settings")
def settings_admin():
    return Response(SETTINGS_HTML, mimetype="text/html")


@app.route("/")
def index():
    return Response(HTML, mimetype="text/html")


# Serve local assets (album covers, publication previews, project images, etc.)
@app.route("/assets/<path:filepath>")
def serve_assets(filepath):
    from flask import send_from_directory
    return send_from_directory(REPO_ROOT / "assets", filepath)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    PORT = 5001
    url = f"http://localhost:{PORT}"
    print(f"\nAdmin Server running at {url}\n")
    # Open browser after a short delay so the server is ready
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    app.run(host="127.0.0.1", port=PORT, debug=False)
