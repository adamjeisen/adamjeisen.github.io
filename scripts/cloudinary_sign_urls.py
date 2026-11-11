#!/usr/bin/env python3
"""Store signed thumbnail + lightbox URLs for every /feelings/ photo.

Why: with "Uploaded" ticked under Restricted media types, Cloudinary only delivers
/image/upload/ URLs that are signed (or pre-generated eagerly). Signed URLs also pass
Strict transformations, so no transformation needs to be allow-listed. The signature
is computed with the API secret, but the signature itself is not secret: it is
safe to commit and publish (it only authorises that exact transformation of that image).

    python scripts/cloudinary_sign_urls.py --check   # no credentials needed
    python scripts/cloudinary_sign_urls.py            # add/refresh thumb_url + large_url

Adds `thumb_url` and `large_url` to each photo in _data/feelings.json, using the
transformation strings in _config.yml (feelings_images). Re-run after changing those
strings. New uploads through scripts/admin_server.py are signed automatically.

--check exits non-zero if any photo (hidden ones included) has a missing signed URL
or one built from a transformation that no longer matches _config.yml. Do not tick
"Uploaded" in the Cloudinary console until --check passes on the deployed data.
"""

from __future__ import annotations

import argparse
import sys

from cloudinary_common import (
    configure_cloudinary,
    feelings_image_config,
    iter_photos,
    read_feelings,
    signed_photo_urls,
    transform_of,
    write_feelings,
)


def problems(data: list, fi: dict) -> list[str]:
    out = []
    want = {"thumb_url": fi["thumb_transform"], "large_url": fi["large_transform"]}
    for m, e, p in iter_photos(data):
        for key, t in want.items():
            got = transform_of(p.get(key, ""))
            if got != t:
                out.append(f"{m.get('id')}/{e.get('id')} {p.get('url')}: {key} "
                           f"{'missing/unsigned' if got is None else f'has {got!r}, want {t!r}'}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only verify; no credentials needed")
    args = ap.parse_args()

    fi = feelings_image_config()
    data = read_feelings()
    n = sum(1 for _ in iter_photos(data))

    if args.check:
        bad = problems(data, fi)
        for b in bad[:20]:
            print(b)
        if bad:
            sys.exit(f"{len(bad)} problem(s) across {n} photos. Run without --check to (re)sign.")
        print(f"OK: all {n} photos have signed thumb_url/large_url matching _config.yml.")
        return

    configure_cloudinary()
    changed = 0
    for _, _, p in iter_photos(data):
        new = signed_photo_urls(p["url"], fi)
        if any(p.get(k) != v for k, v in new.items()):
            p.update(new)
            changed += 1
    if changed:
        write_feelings(data)
    print(f"Signed URLs updated for {changed} of {n} photos.")
    bad = problems(data, fi)
    if bad:
        sys.exit(f"Unexpected: {len(bad)} problem(s) remain, e.g. {bad[0]}")


if __name__ == "__main__":
    main()
