#!/usr/bin/env python3
"""Create the named transformations used by /feelings/ and mark everything the
site requests as "allowed for strict transformations".

Dry run by default (prints what it would do); pass --apply to make changes.

    python scripts/cloudinary_setup_transforms.py            # dry run
    python scripts/cloudinary_setup_transforms.py --apply

What it does (with --apply):
  1. Creates named transformations `feelings_thumb` and `feelings_large`
     (delivered as t_feelings_thumb / t_feelings_large) unless they already exist.
     Existing ones are NOT overwritten; their current definition is printed so
     you can compare.
  2. Sets allowed_for_strict=True on both named transformations.
  3. Sets allowed_for_strict=True on the inline grid-thumbnail transformation
     from _config.yml (feelings_images.thumb_transform), if it is not a t_ name.
  4. Reads each one back and prints the allowed_for_strict flag it now has.

You can do the same thing by hand in the console (Media Library -> Transformations
/ Named transformations: create, then tick "Allowed for strict transformations").
"""

from __future__ import annotations

import argparse
import json
import sys

from cloudinary_common import configure_cloudinary, feelings_image_config, named_transform_definitions


def get_transformation(api, ident: str):
    from cloudinary.exceptions import NotFound

    try:
        return api.transformation(ident)
    except NotFound:
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually create/update (default: dry run)")
    args = ap.parse_args()

    fi = feelings_image_config()
    defs = named_transform_definitions(fi["large_max_px"])

    # Sanity: the template must reference transformations this script manages.
    expected_large = "t_" + "feelings_large"
    if fi["large_transform"] != expected_large:
        print(f"WARNING: _config.yml large_transform is {fi['large_transform']!r}, "
              f"expected {expected_large!r}; large_max_px may not match its definition.")

    print("Named transformations the site needs:")
    for name, d in defs.items():
        print(f"  t_{name:<16} = {d}")
    inline = [fi["thumb_transform"]] if not fi["thumb_transform"].startswith("t_") else []
    if inline:
        print("Inline transformation the site requests (must be allowed for strict):")
        print(f"  {inline[0]}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to create/update these in Cloudinary.")
        return

    cloudinary = configure_cloudinary()
    import cloudinary.api as api  # noqa: F811

    for name, definition in defs.items():
        existing = get_transformation(api, name)
        if existing is None:
            print(f"Creating named transformation {name!r}: {definition}")
            api.create_transformation(name, definition)
        else:
            print(f"Named transformation {name!r} already exists; not overwriting. Current info:")
            print("  " + json.dumps(existing.get("info"), default=str))
        api.update_transformation(name, allowed_for_strict=True)

    for t in inline:
        if get_transformation(api, t) is None:
            print(f"WARNING: inline transformation {t!r} not found in this account's "
                  "transformation list; it will be created on first request, but cannot be "
                  "pre-approved until then. Either switch thumb_transform to t_feelings_thumb "
                  "or re-run this after the page has loaded once.")
            continue
        api.update_transformation(t, allowed_for_strict=True)

    print("\nRead-back:")
    ok = True
    for ident in list(defs) + inline:
        info = get_transformation(api, ident)
        flag = None if info is None else info.get("allowed_for_strict")
        ok &= flag is True
        print(f"  {ident:<45} allowed_for_strict={flag}")
    if not ok:
        sys.exit("Some transformations are not allowed for strict mode. Do NOT enable "
                 "Strict transformations until this is fixed.")
    print("All set. Run scripts/cloudinary_check_delivery.py before and after changing console settings.")


if __name__ == "__main__":
    main()
