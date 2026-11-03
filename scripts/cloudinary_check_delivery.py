#!/usr/bin/env python3
"""Check what res.cloudinary.com actually serves for the /feelings/ photos.

Needs no credentials. Run it BEFORE and AFTER each console security change
(Strict transformations, Restricted media type "Uploaded", ...) to confirm:
  * originals are blocked (once "Uploaded" is restricted), and
  * every URL the site uses still returns 200, with and without a Referer.

    python scripts/cloudinary_check_delivery.py               # 3 sample photos
    python scripts/cloudinary_check_delivery.py --n 5 --get   # use GET instead of HEAD

Uses HEAD by default so no image bytes are downloaded. Note that a request for a
derived image that does not exist yet makes Cloudinary generate it (1 transformation
each), so keep --n small.
"""

from __future__ import annotations

import argparse
import json
import random

import requests

from cloudinary_common import FEELINGS_JSON, feelings_image_config

BROWSER_ACCEPT = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"


def sample_urls(n: int, seed: int) -> list[str]:
    with open(FEELINGS_JSON) as f:
        data = json.load(f)
    urls = [p["url"] for m in data for e in m["events"] for p in e["photos"] if not p.get("hidden")]
    random.Random(seed).shuffle(urls)
    return urls[:n]


def probe(url: str, referer: str | None, use_get: bool) -> str:
    headers = {"Accept": BROWSER_ACCEPT, "User-Agent": "adamjeisen-site-delivery-check"}
    if referer:
        headers["Referer"] = referer
    try:
        if use_get:
            r = requests.get(url, headers=headers, timeout=30, stream=True)
            r.close()
        else:
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
    ap.add_argument("--get", action="store_true", help="use GET (streamed, body not read) instead of HEAD")
    ap.add_argument("--referer", default="https://adamjeisen.com/feelings/")
    args = ap.parse_args()

    fi = feelings_image_config()
    variants = {
        "original (should be BLOCKED once 'Uploaded' is restricted)": "",
        f"grid thumb  {fi['thumb_transform']}": fi["thumb_transform"] + "/",
        f"lightbox    {fi['large_transform']}": fi["large_transform"] + "/",
        "t_feelings_thumb (named alt.)": "t_feelings_thumb/",
        "unapproved  w_401 (should be BLOCKED under strict)": "w_401/",
    }
    for url in sample_urls(args.n, args.seed):
        print(url)
        for label, prefix in variants.items():
            u = url.replace("/upload/", "/upload/" + prefix, 1)
            for ref_label, ref in (("site ref", args.referer), ("no ref  ", None)):
                print(f"  {label:<58} [{ref_label}] {probe(u, ref, args.get)}")
        print()


if __name__ == "__main__":
    main()
