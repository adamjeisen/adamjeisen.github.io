---
layout: page
title: albums i like
permalink: /albums/
nav: true
nav_order: 6
description: some albums that I have enjoyed listening to over the years!
---

<style>
/* Override the default layout styles */
.post .post-header {
  display: none !important;
}

.post .post-content {
  max-width: 95% !important;
  margin: 0 auto !important;
  padding: 0 !important;
}

.page-description {
  margin-bottom: 0 !important;
}
</style>

<div class="custom-header">
  <div class="header-text">
    <h1>albums i like</h1>
    <p class="page-description">some albums that I have enjoyed listening to over the years!<br>(current list count: {{ site.data.albumsilike | size }})</p>
  </div>
  <div class="header-controls">
    <div class="sort-controls">
      <label for="sort-select" class="sort-label">Sort by:</label>
      <select id="sort-select" class="sort-select" onchange="sortAlbums()">
        <option value="artist">Artist</option>
        <option value="album">Album</option>
        <option value="year">Year</option>
      </select>
      <button id="sort-direction" class="sort-direction-btn" onclick="toggleSortDirection()" aria-label="Toggle sort direction" title="Toggle ascending/descending">
        <svg class="sort-direction-icon" width="16" height="16" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M4 10L8 6L12 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>
    <button class="shuffle-button" onclick="shuffleAlbums()" aria-label="Shuffle Albums">
      <img src="/assets/img/shuffle-light.png" alt="Shuffle" class="shuffle-icon light-mode-only">
      <img src="/assets/img/shuffle-dark.png" alt="Shuffle" class="shuffle-icon dark-mode-only">
    </button>
  </div>
</div>

<div class="albums-container" id="albums-container">
  {% assign albums = site.data.albumsilike %}
  {% for album in albums %}
    {% assign image_filename = album.Artist | append: ' - ' | append: album.Album | replace: ':', '_' | replace: '?', '' | replace: "'", '' | replace: '.', '' | replace: '%', '' | replace: '•', '' | replace: '/', '_' %}
    <div class="album-card" data-artist="{{ album.Artist }}" data-album="{{ album.Album }}" data-year="{{ album.Year }}" data-spotify-url="{{ album.SpotifyUrl }}" onclick="showEmbed('{{ album.SpotifyUrl }}')">
      <img src="/assets/img/albums I like/{{ image_filename }}.jpg" onerror="this.onerror=null; this.src='/assets/img/albums I like/{{ image_filename }}.png'" alt="{{ album.Album }} album cover" class="album-cover">
      <div class="album-info">
        <h3>{{ album.Album }}</h3>
        <p>{{ album.Artist }}</p>
        {% if album.Year != "" %}
          <p class="album-year">{{ album.Year }}</p>
        {% endif %}
      </div>
    </div>
  {% endfor %}
</div>

<div id="modal" class="modal" onclick="hideEmbed()">
  <div class="modal-content" onclick="event.stopPropagation()">
    <div class="modal-header-container">
      <button class="modal-shuffle-button" onclick="shuffleAlbums()" aria-label="Shuffle Albums">
        <img src="/assets/img/shuffle-light.png" alt="Shuffle" class="modal-shuffle-icon light-mode-only">
        <img src="/assets/img/shuffle-dark.png" alt="Shuffle" class="modal-shuffle-icon dark-mode-only">
      </button>
      <button class="close" onclick="hideEmbed()" aria-label="Close">×</button>
    </div>
    <div id="embed-container"></div>
  </div>
</div>

<style>
.custom-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding: 0;
}

.header-text {
  flex: 1;
}

.header-text h1 {
  margin: 0;
  font-size: 2rem;
}

.header-text p {
  margin: 0.5rem 0 0 0;
  color: var(--global-text-color-light);
}

.header-controls {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.sort-controls {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: var(--global-card-bg-color);
  padding: 0.5rem 1rem;
  border-radius: 12px;
  border: 1px solid transparent;
  transition: all 0.2s ease;
}

.sort-controls:hover {
  border-color: var(--global-text-color-light);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

[data-theme="dark"] .sort-controls:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.sort-label {
  color: var(--global-text-color-light);
  font-size: 0.85rem;
  font-weight: 500;
  white-space: nowrap;
  letter-spacing: 0.3px;
  display: flex;
  align-items: center;
  height: 100%;
}

.sort-select {
  background: transparent;
  color: var(--global-text-color);
  border: none;
  border-radius: 6px;
  padding: 0.4rem 1.75rem 0.4rem 0.6rem;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23666' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 0.5rem center;
  min-width: 100px;
  height: 100%;
  display: flex;
  align-items: center;
}

[data-theme="dark"] .sort-select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%23aaa' d='M6 9L1 4h10z'/%3E%3C/svg%3E");
}

.sort-select:hover {
  background-color: rgba(0, 0, 0, 0.05);
}

[data-theme="dark"] .sort-select:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

.sort-select:focus {
  outline: none;
  background-color: rgba(0, 0, 0, 0.05);
  box-shadow: 0 0 0 2px var(--global-theme-color);
}

[data-theme="dark"] .sort-select:focus {
  background-color: rgba(255, 255, 255, 0.05);
}

.sort-direction-btn {
  background: transparent;
  border: none;
  border-radius: 6px;
  padding: 0.4rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  color: var(--global-text-color-light);
  height: 100%;
  min-width: 28px;
}

.sort-direction-btn:hover {
  background-color: rgba(0, 0, 0, 0.05);
  color: var(--global-text-color);
}

[data-theme="dark"] .sort-direction-btn:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

.sort-direction-btn:focus {
  outline: none;
  background-color: rgba(0, 0, 0, 0.05);
  box-shadow: 0 0 0 2px var(--global-theme-color);
}

[data-theme="dark"] .sort-direction-btn:focus {
  background-color: rgba(255, 255, 255, 0.05);
}

.sort-direction-icon {
  transition: transform 0.2s ease;
}

.sort-direction-btn[data-direction="desc"] .sort-direction-icon {
  transform: rotate(180deg);
}

.shuffle-button {
  background: transparent;
  border: 2px solid transparent;
  border-radius: 16px;
  padding: 1.5rem;
  margin-left: 2rem;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s, border-color 0.2s;
}

.shuffle-button:hover {
  transform: scale(1.1);
  border-color: var(--global-theme-color);
}

[data-theme="dark"] .shuffle-button:hover {
  border-color: var(--global-hover-color);
}

.shuffle-icon {
  width: 48px;
  height: 48px;
  object-fit: contain;
}

.albums-container {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 0.75rem;
  padding: 0.75rem;
  margin: 0 auto;
  max-width: 100%;
}

.album-card {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  text-align: left;
  background: var(--global-card-bg-color);
  padding: 0.5rem;
  border-radius: 8px;
  transition: transform 0.2s;
  cursor: pointer;
}

.album-card:hover {
  transform: translateY(-5px);
}

.album-cover {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  border-radius: 4px;
  margin-bottom: 0.5rem;
}

.album-info {
  padding: 0 0.25rem;
}

.album-info h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 400;
  color: var(--global-text-color);
  line-height: 1.2;
}

.album-info p {
  margin: 0.25rem 0 0;
  color: var(--global-text-color-light);
  font-size: 0.85rem;
  font-weight: 400;
}

.album-year {
  margin-top: 0.15rem !important;
  font-size: 0.75rem !important;
  opacity: 0.8;
}

.modal {
  display: none;
  position: fixed;
  z-index: 1000;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0,0,0,0.7);
  backdrop-filter: blur(5px);
}

.modal-content {
  position: relative;
  background-color: var(--global-card-bg-color);
  margin: 12% auto;
  padding: 0;
  width: 80%;
  max-width: 600px;
  border-radius: 12px;
  overflow: hidden;
}

.modal-header-container {
  height: 50px;
  position: relative;
  background-color: var(--global-card-bg-color);
  padding: 0 20px;
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 1rem;
}

.modal-header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 1rem;
}

.modal-shuffle-button {
  background: transparent;
  border: 2px solid transparent;
  border-radius: 8px;
  padding: 0.5rem;
  margin: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s, border-color 0.2s;
}

.modal-shuffle-button:hover {
  transform: scale(1.1);
  border-color: var(--global-theme-color);
}

[data-theme="dark"] .modal-shuffle-button:hover {
  border-color: var(--global-hover-color);
}

.modal-shuffle-icon {
  width: 24px;
  height: 24px;
  object-fit: contain;
}

.close {
  background: transparent;
  border: 2px solid transparent;
  border-radius: 8px;
  padding: 0.5rem;
  margin: 0;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s, border-color 0.2s;
  font-size: 24px;
  line-height: 1;
  color: var(--global-text-color);
  width: 24px;
  height: 24px;
}

.close:hover {
  transform: scale(1.1);
  border-color: var(--global-theme-color);
}

[data-theme="dark"] .close:hover {
  border-color: var(--global-hover-color);
}

#embed-container {
  margin: 0;
  padding: 0 20px 20px 20px;
}

#embed-container iframe {
  display: block;
  margin: 0;
  padding: 0;
  width: 100%;
}

@media (max-width: 2000px) {
  .albums-container {
    grid-template-columns: repeat(5, minmax(0, 1fr));
  }
}

@media (max-width: 1600px) {
  .albums-container {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 1200px) {
  .albums-container {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 800px) {
  .albums-container {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 500px) {
  .albums-container {
    grid-template-columns: 1fr;
    padding: 0.5rem;
  }
  .post-content {
    max-width: 100% !important;
  }
  .custom-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 1rem;
  }
  .header-controls {
    width: 100%;
    justify-content: space-between;
    flex-wrap: wrap;
  }
  .sort-controls {
    flex: 1;
    min-width: 0;
    padding: 0.4rem 0.75rem;
    gap: 0.5rem;
  }
  .sort-label {
    font-size: 0.8rem;
  }
  .sort-select {
    flex: 1;
    min-width: 80px;
    font-size: 0.85rem;
    padding: 0.35rem 1.5rem 0.35rem 0.5rem;
  }
  .sort-direction-btn {
    min-width: 24px;
    padding: 0.35rem;
  }
}

/* Light/dark mode image switching */
.light-mode-only {
  display: none;
}

.dark-mode-only {
  display: none;
}

[data-theme="light"] .light-mode-only {
  display: block;
}

[data-theme="dark"] .dark-mode-only {
  display: block;
}
</style>

<script>
// Store all album URLs in an array
const albumUrls = [
{% for album in site.data.albumsilike %}
  {% if album.SpotifyUrl != "" %}
    "{{ album.SpotifyUrl }}",
  {% endif %}
{% endfor %}
];

// Get all album cards
function getAllAlbumCards() {
  return Array.from(document.querySelectorAll('.album-card'));
}

// Get sort direction (asc or desc)
function getSortDirection() {
  const btn = document.getElementById('sort-direction');
  return btn.getAttribute('data-direction') || 'asc';
}

// Toggle sort direction
function toggleSortDirection() {
  const btn = document.getElementById('sort-direction');
  const currentDir = getSortDirection();
  const newDir = currentDir === 'asc' ? 'desc' : 'asc';
  btn.setAttribute('data-direction', newDir);
  sortAlbums();
}

// Sort albums based on selected criteria
function sortAlbums() {
  const sortBy = document.getElementById('sort-select').value;
  const sortDir = getSortDirection();
  const container = document.getElementById('albums-container');
  const cards = getAllAlbumCards();
  const multiplier = sortDir === 'asc' ? 1 : -1;
  
  cards.sort((a, b) => {
    let comparison = 0;
    
    switch(sortBy) {
      case 'artist':
        // Remove "The " and "A " for sorting
        const aArtist = (a.dataset.artist || '').replace(/^(The |A )/i, '').toLowerCase();
        const bArtist = (b.dataset.artist || '').replace(/^(The |A )/i, '').toLowerCase();
        if (aArtist < bArtist) comparison = -1;
        else if (aArtist > bArtist) comparison = 1;
        else comparison = 0;
        break;
      case 'album':
        const aAlbum = (a.dataset.album || '').toLowerCase();
        const bAlbum = (b.dataset.album || '').toLowerCase();
        if (aAlbum < bAlbum) comparison = -1;
        else if (aAlbum > bAlbum) comparison = 1;
        else comparison = 0;
        break;
      case 'year':
        // Sort by year, then by artist if year is missing or equal
        const aYear = parseInt(a.dataset.year) || 0;
        const bYear = parseInt(b.dataset.year) || 0;
        if (aYear !== bYear) {
          comparison = aYear - bYear; // Will be multiplied by direction
        } else {
          // If years are equal or both missing, sort by artist
          const aArtistYear = (a.dataset.artist || '').replace(/^(The |A )/i, '').toLowerCase();
          const bArtistYear = (b.dataset.artist || '').replace(/^(The |A )/i, '').toLowerCase();
          if (aArtistYear < bArtistYear) comparison = -1;
          else if (aArtistYear > bArtistYear) comparison = 1;
          else comparison = 0;
        }
        break;
      default:
        comparison = 0;
    }
    
    return comparison * multiplier;
  });
  
  // Re-append sorted cards
  cards.forEach(card => container.appendChild(card));
}

function shuffleAlbums() {
  if (albumUrls.length > 0) {
    const randomIndex = Math.floor(Math.random() * albumUrls.length);
    showEmbed(albumUrls[randomIndex]);
  }
}

function showEmbed(url) {
  const modal = document.getElementById('modal');
  const embedContainer = document.getElementById('embed-container');
  const urlParts = url.split('/');
  const type = urlParts[urlParts.length - 2]; // Get 'album' or 'playlist' from URL
  const id = urlParts[urlParts.length - 1].split('?')[0];
  
  embedContainer.innerHTML = `<iframe style="border-radius:12px" src="https://open.spotify.com/embed/${type}/${id}?utm_source=generator" width="100%" height="352" frameBorder="0" allowfullscreen="" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy"></iframe>`;
  modal.style.display = 'block';
  document.body.style.overflow = 'hidden';
}

function hideEmbed() {
  const modal = document.getElementById('modal');
  const embedContainer = document.getElementById('embed-container');
  modal.style.display = 'none';
  embedContainer.innerHTML = '';
  document.body.style.overflow = 'auto';
}

// Close modal when pressing escape key
document.addEventListener('keydown', function(event) {
  if (event.key === 'Escape') {
    hideEmbed();
  }
});

// Initialize sorting on page load (default to artist, ascending)
document.addEventListener('DOMContentLoaded', function() {
  const sortDirBtn = document.getElementById('sort-direction');
  if (sortDirBtn && !sortDirBtn.getAttribute('data-direction')) {
    sortDirBtn.setAttribute('data-direction', 'asc');
  }
  sortAlbums();
});
</script> 