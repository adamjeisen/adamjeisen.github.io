"""Shared helpers for the Cloudinary maintenance scripts (and admin_server.py).

Credentials are read from the environment only (never hard-code or commit them):
  * CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>   (read by the SDK itself), or
  * CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET.
A local, git-ignored .env file (repo root or scripts/) is loaded if python-dotenv is installed.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "_config.yml"
FEELINGS_JSON = REPO_ROOT / "_data" / "feelings.json"

# https://res.cloudinary.com/<cloud>/image/upload/v<version>/<public_id>.<ext>
# (exactly what the upload API's secure_url looks like; no transformation, no signature)
_UPLOAD_URL = re.compile(
    r"^https://res\.cloudinary\.com/(?P<cloud>[^/]+)/image/upload/"
    r"v(?P<version>\d+)/(?P<public_id>.+)\.(?P<ext>[A-Za-z0-9]+)$"
)


def load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for p in (REPO_ROOT / ".env", REPO_ROOT / "scripts" / ".env"):
        if p.exists():
            load_dotenv(p, override=False)


def configure_cloudinary():
    """Configure and return the cloudinary module, or exit with a clear message."""
    load_dotenv_if_available()
    import cloudinary

    if os.getenv("CLOUDINARY_URL"):
        cloudinary.reset_config()  # the SDK parses CLOUDINARY_URL from the environment
    else:
        name = os.getenv("CLOUDINARY_CLOUD_NAME")
        key = os.getenv("CLOUDINARY_API_KEY")
        secret = os.getenv("CLOUDINARY_API_SECRET")
        if not (name and key and secret):
            sys.exit(
                "Cloudinary credentials not found. Set CLOUDINARY_URL, or "
                "CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET "
                "(e.g. in a git-ignored .env)."
            )
        cloudinary.config(cloud_name=name, api_key=key, api_secret=secret, secure=True)
    cfg = cloudinary.config()
    if not (cfg.cloud_name and cfg.api_key and cfg.api_secret):
        sys.exit("Cloudinary config incomplete after reading the environment.")
    return cloudinary


def feelings_image_config() -> dict:
    """Read and validate the `feelings_images` block from _config.yml."""
    import yaml

    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    fi = dict(cfg.get("feelings_images") or {})
    missing = [k for k in ("thumb_transform", "large_transform", "large_max_px") if k not in fi]
    if missing:
        sys.exit(f"_config.yml feelings_images is missing: {missing}")
    fi["large_max_px"] = int(fi["large_max_px"])
    parts = set(fi["large_transform"].split(","))
    n = fi["large_max_px"]
    if not {"c_limit", f"w_{n}", f"h_{n}"} <= parts:
        sys.exit(
            f"_config.yml: large_transform {fi['large_transform']!r} must contain c_limit, "
            f"w_{n} and h_{n} (large_max_px = {n}); the page's lightbox dimensions assume it."
        )
    return fi


def parse_upload_url(url: str) -> dict:
    m = _UPLOAD_URL.match(url)
    if not m:
        raise ValueError(f"not a plain Cloudinary upload URL: {url}")
    return m.groupdict()


def signed_url(url: str, transformation: str) -> str:
    """Signed delivery URL for `transformation` applied to the original at `url`.

    Requires cloudinary to be configured with the API secret. The signature covers
    "<transformation>/<public_id>.<ext>" (the version is not part of it), so it only
    changes if the transformation string or the secret changes.
    """
    import cloudinary.utils

    p = parse_upload_url(url)
    out, _ = cloudinary.utils.cloudinary_url(
        p["public_id"],
        resource_type="image",
        type="upload",
        format=p["ext"],
        version=p["version"],
        raw_transformation=transformation,
        sign_url=True,
        secure=True,
    )
    return out


def signed_photo_urls(url: str, fi: dict) -> dict:
    """{'thumb_url': ..., 'large_url': ...} for one photo's original URL."""
    return {
        "thumb_url": signed_url(url, fi["thumb_transform"]),
        "large_url": signed_url(url, fi["large_transform"]),
    }


def transform_of(delivery_url: str) -> str | None:
    """Transformation component of a signed delivery URL, or None if unsigned/unparseable."""
    m = re.search(r"/image/upload/s--[A-Za-z0-9_-]+--/(.+?)/v\d+/", delivery_url or "")
    return m.group(1) if m else None


def iter_photos(data: list):
    for m in data:
        for e in m.get("events", []):
            for p in e.get("photos", []):
                yield m, e, p


def read_feelings() -> list:
    with open(FEELINGS_JSON, encoding="utf-8") as f:
        return json.load(f)


def write_feelings(data: list) -> None:
    """Same on-disk format as admin_server.write_tis_json (indent=2, trailing newline)."""
    tmp = FEELINGS_JSON.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, FEELINGS_JSON)
