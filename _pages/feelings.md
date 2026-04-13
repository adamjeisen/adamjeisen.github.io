---
layout: page
title: feelings
permalink: /feelings/
nav: true
nav_order: 7
description: my attempts to visually and sonically capture my feelings & experiences
---

<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.min.css">

<style>
.post .post-header {
  display: none !important;
}

.post .post-content {
  max-width: 95% !important;
  margin: 0 auto !important;
  padding: 0 !important;
}

/* Page header */
.tis-page-header {
  margin-bottom: 2.5rem;
}

.tis-page-header h1 {
  font-size: 2rem;
  font-weight: 400;
  letter-spacing: -0.02em;
  margin: 0 0 0.3rem 0;
  color: var(--global-text-color);
}

.tis-page-header .tis-page-desc {
  font-size: 0.9rem;
  color: var(--global-text-color-light);
  margin: 0;
}

/* Jump nav */
.tis-jump-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-bottom: 2.5rem;
}

.tis-jump-nav a {
  font-size: 0.78rem;
  color: var(--global-text-color-light);
  text-decoration: none;
  padding: 0.2rem 0.55rem;
  border: 1px solid var(--global-divider-color);
  border-radius: 20px;
  transition: color 0.15s, border-color 0.15s;
}

.tis-jump-nav a:hover {
  color: var(--global-theme-color);
  border-color: var(--global-theme-color);
}

/* Month section */
.tis-month {
  margin-bottom: 3.5rem;
}

.tis-month-header {
  display: flex;
  align-items: baseline;
  gap: 1.5rem;
  flex-wrap: wrap;
  margin-bottom: 0.6rem;
}

.tis-month-label {
  font-size: 1.35rem;
  font-weight: 500;
  color: var(--global-text-color-light);
  margin: 0;
  white-space: nowrap;
}

.tis-month-desc {
  font-size: 0.9rem;
  font-style: italic;
  color: var(--global-text-color-light);
  margin: 0;
  opacity: 0.8;
}

.tis-playlist-embed {
  margin-top: 0.6rem;
  border-radius: 12px;
  overflow: hidden;
  opacity: 0.85;
  transition: opacity 0.2s;
}

.tis-playlist-embed:hover {
  opacity: 1;
}

.tis-playlist-embed iframe {
  display: block;
  border: none;
  border-radius: 12px;
}

.tis-divider {
  border: none;
  border-top: 1px solid var(--global-divider-color);
  margin: 0 0 1rem 0;
}

/* Event sections */
.tis-event {
  margin-bottom: 1.8rem;
}

.tis-event-title {
  font-size: 0.85rem;
  font-style: italic;
  color: var(--global-text-color-light);
  opacity: 0.75;
  margin: 0 0 0.6rem 0;
  font-weight: 400;
}

/* Photo grid */
.tis-photo-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 4px;
}

.tis-photo-item {
  display: block;
  overflow: hidden;
  border-radius: 8px;
  cursor: pointer;
  text-decoration: none;
}

.tis-photo-img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  display: block;
  border-radius: 8px;
  transition: transform 0.2s ease;
}

.tis-photo-item:hover .tis-photo-img {
  transform: scale(1.03);
}

.tis-caption {
  font-size: 0.75rem;
  color: var(--global-text-color-light);
  text-align: center;
  margin: 0.35rem 0 0 0;
  opacity: 0.8;
  line-height: 1.3;
}

/* PhotoSwipe caption (event title shown in lightbox) */
.pswp__custom-caption {
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 0.85rem;
  text-align: center;
  padding: 0.6rem 1.5rem;
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  pointer-events: none;
}

.pswp__custom-caption:empty {
  display: none;
}

/* Responsive */
@media (max-width: 768px) {
  .tis-photo-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
@media (max-width: 480px) {
  .tis-photo-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>

{% assign total_photos = 0 %}
{% for month in site.data.feelings %}
  {% for event in month.events %}
    {% for photo in event.photos %}
      {% unless photo.hidden %}
        {% assign total_photos = total_photos | plus: 1 %}
      {% endunless %}
    {% endfor %}
  {% endfor %}
{% endfor %}

<div class="tis-page-header">
  <h1>feelings</h1>
  <p class="tis-page-desc">my attempts to visually and sonically capture my feelings & experiences &mdash; {{ total_photos }} photos across {{ site.data.feelings | size }} months</p>
</div>

{% if site.data.feelings.size > 3 %}
<nav class="tis-jump-nav" aria-label="Jump to month">
  {% for month in site.data.feelings %}
    <a href="#{{ month.id }}">{{ month.month_label }}</a>
  {% endfor %}
</nav>
{% endif %}

{% for month in site.data.feelings %}
<section class="tis-month" id="{{ month.id }}">
  <div class="tis-month-header">
    <h2 class="tis-month-label">{{ month.month_label }}</h2>
    {% if month.description and month.description != "" %}
      <p class="tis-month-desc">{{ month.description }}</p>
    {% endif %}
  </div>
  {% if month.playlist_url and month.playlist_url != "" %}
    {% assign embed_url = month.playlist_url | replace: 'https://open.spotify.com/', 'https://open.spotify.com/embed/' | split: '?' | first %}
    <div class="tis-playlist-embed">
      <iframe src="{{ embed_url }}?utm_source=generator&theme=0" width="100%" height="152" allow="autoplay; clipboard-write; encrypted-media; fullscreen; picture-in-picture" loading="lazy"></iframe>
    </div>
  {% endif %}
  <hr class="tis-divider">

  {% for event in month.events %}
  <div class="tis-event pswp-gallery" id="gallery-{{ month.id }}-{{ event.id }}">
    {% if event.title and event.title != "" %}
      <p class="tis-event-title">{{ event.title }}</p>
    {% endif %}
    <div class="tis-photo-grid">
      {% for photo in event.photos %}
      {% if photo.hidden %}{% continue %}{% endif %}
      {% assign thumb_url = photo.url | replace: '/upload/', '/upload/w_400,h_400,c_fill,g_auto,q_auto,f_auto/' %}
      <a href="{{ photo.url }}"
         data-pswp-width="{{ photo.width }}"
         data-pswp-height="{{ photo.height }}"
         data-event-title="{{ event.title }}"
         data-caption="{{ photo.caption }}"
         class="tis-photo-item tis-{{ photo.orientation }}"
         target="_blank">
        <img
          src="{{ thumb_url }}"
          alt="{{ photo.caption | default: event.title }}"
          loading="lazy"
          class="tis-photo-img">
        {% if photo.caption and photo.caption != "" %}
          <p class="tis-caption">{{ photo.caption }}</p>
        {% endif %}
      </a>
      {% endfor %}
    </div>
  </div>
  {% endfor %}

</section>
{% endfor %}

<script type="module">
import PhotoSwipeLightbox from 'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe-lightbox.esm.min.js';
import PhotoSwipe from 'https://cdn.jsdelivr.net/npm/photoswipe@5.4.4/dist/photoswipe.esm.min.js';

const lightbox = new PhotoSwipeLightbox({
  gallery: '.pswp-gallery',
  children: 'a',
  pswpModule: PhotoSwipe,
});

// Caption support
lightbox.on('uiRegister', function () {
  lightbox.pswp.ui.registerElement({
    name: 'custom-caption',
    order: 9,
    isButton: false,
    appendTo: 'wrapper',
    onInit: (el, pswp) => {
      pswp.on('change', () => {
        const anchor = pswp.currSlide.data.element;
        if (!anchor) { el.innerHTML = ''; return; }
        const parts = [anchor.dataset.eventTitle, anchor.dataset.caption].filter(Boolean);
        el.innerHTML = parts.join(' — ');
      });
    },
  });
});

lightbox.init();
</script>
