#!/usr/bin/env python3
"""Check what res.cloudinary.com actually serves for the /feelings/ photos.

Needs no credentials. Run it BEFORE and AFTER each console security change
(Strict transformations, then Restricted media type "Uploaded") to confirm:
  * the site's signed URLs (thumb_url / large_url in _data/feelings.json) return 200,
    with and without a Referer;
  * new unsigned transformations (w_401) are blocked once Strict is on.
Measured 2026-11-11: originals and already-generated unsigned thumbnails stay 200 even
with "Uploaded" restricted (that setting only blocks *creating* images from unsigned
URLs). Those rows are reported for information; see scripts/CLOUDINARY.md section 2.

    python scripts/cloudinary_check_delivery.py               # 3 random photos
    python scripts/cloudinary_check_delivery.py --seed 7      # a different 3

Uses HEAD, so no image bytes are downloaded (Content-Length shows the size).
Each probe of a derived image that doesn't exist yet makes Cloudinary generate it
(1 transformation), so keep --n small. Use a new --seed after each settings change,
so you also test photos whose derived images have never been generated.
"""

from __future__ import annotations

import argparse
import random

import requests

from cloudinary_common import feelings_image_config, iter_photos, read_feelings

BROWSER_ACCEPT = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"


def probe(url: str, referer: str | None) -> str:
    headers = {"Accept": BROWSER_ACCEPT, "User-Agent": "adamjeisen-site-delivery-check"}
    if referer:
        headers["Referer"] = referer
    try:
        r = requests.head(url, headers=headers, timeout=30, allow_redirects=True)
    except requests.RequestException as e:
        return f"ERROR {e.__class__.__name__}"
    h = r.headers
    size = h.get("Content-Length", "?")
    extra = f" x-cld-error={h['x-cld-error']!r}" if "x-cld-error" in h else ""
    return f"{r.status_code} {h.get('Content-Type', '?'):<11} {size:>9} B{extra}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=3, help="number of sample photos (default 3)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--referer", default="https://adamjeisen.com/feelings/")
    args = ap.parse_args()

    fi = feelings_image_config()
    photos = [p for _, _, p in iter_photos(read_feelings()) if not p.get("hidden")]
    random.Random(args.seed).shuffle(photos)

    for p in photos[: args.n]:
        url = p["url"]
        print(url)
        probes = {
            "SITE signed thumb_url        (must be 200)": p.get("thumb_url"),
            "SITE signed large_url        (must be 200)": p.get("large_url"),
            "original                     (info: stays 200, see CLOUDINARY.md)": url,
            "unsigned thumb (exists)      (info: stays 200, see CLOUDINARY.md)":
                url.replace("/upload/", f"/upload/{fi['thumb_transform']}/", 1),
            "unsigned w_401               (blocked once Strict is on)":
                url.replace("/upload/", "/upload/w_401/", 1),
        }
        for label, u in probes.items():
            if not u:
                print(f"  {label:<70} -- not signed yet (run cloudinary_sign_urls.py)")
                continue
            for ref_label, ref in (("site ref", args.referer), ("no ref  ", None)):
                print(f"  {label:<70} [{ref_label}] {probe(u, ref)}")
        print()


if __name__ == "__main__":
    main()
