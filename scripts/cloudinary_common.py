"""Shared helpers for the Cloudinary maintenance scripts.

Credentials are read from the environment only (never hard-code or commit them):
  * CLOUDINARY_URL=cloudinary://<api_key>:<api_secret>@<cloud_name>   (read by the SDK itself), or
  * CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET.
A local, git-ignored .env file (repo root or scripts/) is loaded if python-dotenv is installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "_config.yml"
FEELINGS_JSON = REPO_ROOT / "_data" / "feelings.json"

# Name (without the "t_" delivery prefix) -> definition. The large definition's
# limit is filled in from _config.yml so the template and Cloudinary can't drift.
THUMB_NAME = "feelings_thumb"
LARGE_NAME = "feelings_large"


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
        # The SDK parses CLOUDINARY_URL from the environment on import/reset.
        cloudinary.reset_config()
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
    """Read the `feelings_images` block from _config.yml."""
    import yaml

    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    fi = cfg.get("feelings_images") or {}
    missing = [k for k in ("thumb_transform", "large_transform", "large_max_px") if k not in fi]
    if missing:
        sys.exit(f"_config.yml feelings_images is missing: {missing}")
    fi["large_max_px"] = int(fi["large_max_px"])
    return fi


def named_transform_definitions(large_max_px: int) -> dict[str, str]:
    """The named transformations the site relies on (name -> definition)."""
    return {
        # Same geometry/quality as the grid thumbnails the site has always used.
        THUMB_NAME: "c_fill,g_auto,w_400,h_400,f_auto,q_auto",
        # Lightbox / click-through: never upscales (c_limit), long side <= large_max_px.
        LARGE_NAME: f"c_limit,w_{large_max_px},h_{large_max_px},f_auto,q_auto",
    }
