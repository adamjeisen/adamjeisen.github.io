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
    <p class="page-description">some albums that I have enjoyed listening to over the years! (current list count: {{ site.data.albumsilike | size }})</p>
  </div>
  <button class="shuffle-button" onclick="shuffleAlbums()" aria-label="Shuffle Albums">
    <img src="/assets/img/shuffle-light.png" alt="Shuffle" class="shuffle-icon light-mode-only">
    <img src="/assets/img/shuffle-dark.png" alt="Shuffle" class="shuffle-icon dark-mode-only">
  </button>
</div>

<div class="albums-container">
  {% assign albums = site.data.albumsilike %}
  {% assign sorted_albums = '' | split: '' %}
  {% for album in albums %}
    {% assign artist_name = album.Artist | remove_first: 'The ' | remove_first: 'A ' | downcase %}
    {% assign album_name = album.Album | downcase %}
    {% assign album_hash = '' | split: '' %}
    {% assign album_hash = album_hash | push: artist_name | push: album_name | push: album %}
    {% assign sorted_albums = sorted_albums | push: album_hash %}
  {% endfor %}
  {% assign sorted_albums = sorted_albums | sort %}
  {% for album_hash in sorted_albums %}
    {% assign album = album_hash[2] %}
    <div class="album-card" onclick="showEmbed('{{ album.SpotifyUrl }}')">
      {% assign image_filename = album.Artist | append: ' - ' | append: album.Album | replace: ':', '_' | replace: '?', '' | replace: "'", '' | replace: '.', '' | replace: '%', '' | replace: '•', '' | replace: '/', '_' %}
      <img src="/assets/img/albums I like/{{ image_filename }}.jpg" onerror="this.onerror=null; this.src='/assets/img/albums I like/{{ image_filename }}.png'" alt="{{ album.Album }} album cover" class="album-cover">
      <div class="album-info">
        <h3>{{ album.Album }}</h3>
        <p>{{ album.Artist }}</p>
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
{% for album_hash in sorted_albums %}
  {% assign album = album_hash[2] %}
  {% if album.SpotifyUrl != "" %}
    "{{ album.SpotifyUrl }}",
  {% endif %}
{% endfor %}
];

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
</script> 