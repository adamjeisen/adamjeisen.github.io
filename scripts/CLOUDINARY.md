# Cloudinary: delivery audit, lockdown runbook, usage report

Cloud name: `dpxqdgavv`. Free plan, 25 credits / rolling 30 days
(1 credit = 1 GB bandwidth = 1 GB storage = 1,000 transformations).

## 1. Audit (state before this change)

The only Cloudinary images on the site are on `/feelings/`. There are 4,133 photos in `_data/feelings.json`, 8 of them hidden.
They were all uploaded by `scripts/admin_server.py`, which stores Cloudinary's `secure_url`. That is the
untransformed original, `https://res.cloudinary.com/dpxqdgavv/image/upload/v<ver>/things-i-saw/<id>.jpg`,
and is typically about 4000×3000 px.

| Where | What was requested | Transformation | Generated |
|---|---|---|---|
| `_pages/feelings.md` grid `<img src>` | transformed | `w_400,h_400,c_fill,g_auto,q_auto,f_auto` (unsigned, on-the-fly) | build time (Liquid `replace` on the stored URL) |
| `_pages/feelings.md` `<a href>`: PhotoSwipe lightbox and the `target=_blank` fallback | **untransformed original** | none | build time (stored URL used verbatim) |
| `scripts/admin_server.py` admin UI photo cards | transformed | `w_280,h_220,c_fill` (unsigned, on-the-fly) | runtime, in the browser (JS `replace`), served from localhost |
| `scripts/admin_server.py` upload, delete, backfill | Admin/Upload API only, no delivery | none | runtime (local admin server) |

Nothing else references Cloudinary: no other `_data` files, layouts, includes, posts or JS.
Album covers and other images are local files under `assets/`.

Every lightbox open, and every scraper following the `<a href>`, pulled the full-size original. That
matches the observed ~720 KB/request.

## 2. What changed

- `_config.yml` → `feelings_images`:
  - `thumb_transform: w_400,h_400,c_fill,g_auto,q_auto,f_auto`. This is the same string as before, so the
    thumbnails Cloudinary has already derived stay valid and nothing is re-generated. Under strict mode
    it must be marked *allowed for strict* (see the setup script). To use the named transformation
    instead, set it to `t_feelings_thumb`. Every thumbnail would then be re-derived once, on first
    request, at roughly 1 credit per 1,000 images per output format.
  - `large_transform: t_feelings_large`: used by the lightbox and the click-through link.
  - `large_max_px: 1600` **must equal** the limit in the `t_feelings_large` definition. The template
    uses it to scale `data-pswp-width/height`, keeping the aspect ratio and long side ≤ 1600 px.
- `_pages/feelings.md`: **the page never links to an untransformed original any more.** This was checked
  by rendering the page with Liquid 4.0.4: 8,250 Cloudinary URLs, 0 untransformed.
- `scripts/admin_server.py`: admin thumbnails use the same approved thumbnail transformation.
- `robots.txt`: disallows AI-training and dataset crawlers (Reflectionbot, GPTBot, CCBot, ClaudeBot,
  Bytespider, Google-Extended, …). Normal search engines are unchanged. This only affects discovery
  *through adamjeisen.com*. It does nothing about image URLs already harvested from
  `res.cloudinary.com`, and only compliant bots obey it.
- `_config.yml` `exclude`: `scripts/`, `pyproject.toml`, `uv.lock` and `requirements.txt` are no longer
  published to the live site. Before this change, `scripts/*.py` was being served publicly.

### Named transformations to create

Create these in the console under Transformations → Named transformations, or run
`scripts/cloudinary_setup_transforms.py --apply`, which also sets the strict flag:

| Name (delivered as) | Definition | Allowed for strict |
|---|---|---|
| `feelings_large` (`t_feelings_large`) | `c_limit,w_1600,h_1600,f_auto,q_auto` | **yes** |
| `feelings_thumb` (`t_feelings_thumb`) | `c_fill,g_auto,w_400,h_400,f_auto,q_auto` | **yes** |

Also mark the existing inline transformation `w_400,h_400,c_fill,g_auto,q_auto,f_auto` as
**allowed for strict**. You can do this in Transformations → Transformation log, or the script does it.

`c_limit` never upscales: the long side becomes min(original, 1600). The 1600 px limit is a trade-off,
since a full-screen lightbox on a 2× display could use more. To change it, edit `large_max_px` *and*
the named transformation together.

## 3. Rollout order (console steps for Adam)

1. Merge this branch to `master` and let the deploy finish. Check `/feelings/`: thumbnails load,
   clicking opens the lightbox, and the image URL contains `t_feelings_large`.
2. Set credentials in the environment and run `python scripts/cloudinary_setup_transforms.py --apply`.
   It must end with "All set".
3. Run `python scripts/cloudinary_check_delivery.py` to get a baseline. Each probe prints the status,
   content type and size; note the size of `t_feelings_large` versus the original.
4. Settings → Security → **Strict transformations: enable**. Run the checker again, with a new seed
   so it probes photos nobody has viewed yet: `--seed 1`. Expected results:
   - the site's thumbnail and `t_feelings_large` return 200;
   - `w_401` is blocked;
   - originals still return 200, because strict mode does not block originals.

   Adding `adamjeisen.com` / `www.adamjeisen.com` to *Allowed strict referral domains* is **not
   required** for the site, because everything it requests is pre-approved. Adding them would also let
   anyone who spoofs that Referer generate arbitrary transformations, so leave the list empty unless
   something breaks.
5. Settings → Security → Restricted media types → **tick "Uploaded"**. Run the checker again with
   another new seed (`--seed 2`). Expected: originals are blocked, and the site variants still return
   200 both *with and without* a Referer.

   **I could not confirm from Cloudinary's docs**, because cloudinary.com was unreachable from the
   environment that made this change, whether restricting "Uploaded" also blocks *on-the-fly creation*
   of derived images for not-yet-viewed photos. That is why step 5 uses a fresh seed. If the site
   variants fail, untick "Uploaded" immediately. The fallback would be to pre-generate the derived
   images with `explicit`/eager, which costs about 1 credit per 1,000 images, or to move to signed URLs.
6. Restricted media types → also tick **Fetched URL**, and any other delivery types you don't use.
   The site uses none of them.

Email to Cloudinary support (draft):

> Hi, my free account (cloud `dpxqdgavv`) went over its credit limit because of crawler traffic, not
> my site: about 95% of the last 30 days' bandwidth had a referrer of res.cloudinary.com or none, with
> user agents like Reflectionbot and headless Chrome from Singapore datacenters. I've since switched
> the site to named transformations, enabled strict transformations and restricted delivery of
> originals. Could you give me a grace period past Nov 17 while the 30-day window rolls over? Could you
> also set up a referral-domain allowlist for adamjeisen.com on this account? Thanks, Adam

## 4. Daily usage report

`scripts/cloudinary_usage.py`, which reads credentials from `CLOUDINARY_URL` or the
`CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET` variables:

```bash
python scripts/cloudinary_usage.py inspect
```

```bash
python scripts/cloudinary_usage.py daily --semantics per_day --out cloudinary_daily_usage.csv
```

What a per-date `usage(date=…)` call returns (that day only, cumulative, or a rolling 30-day total) is
**unverified**. `inspect` dumps the raw responses and prints a diagnostic (the sum of the per-date
values versus the current total). `daily` refuses to run without an explicit `--semantics`, so no daily
numbers are reported until you have confirmed which it is. If it turns out to be `rolling30`, single
days cannot be recovered from the API. The script says so and reports the window's net change instead.

Spike days are flagged when the value exceeds median + 3 × 1.4826 × MAD, a robust z-score above 3; set
the multiplier with `--k`. The top 5 days are always listed. Output CSVs and raw JSON are git-ignored.

Implementation note: the SDK puts the date into the request path. It encodes a `datetime.date` as
`dd-mm-yyyy` (`/usage/05-10-2026`), but sends a string such as `"2026-10-05"` unchanged. The script
therefore passes `date` objects.
