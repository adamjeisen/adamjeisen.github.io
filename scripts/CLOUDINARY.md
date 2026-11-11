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

**Every image URL on the page is now a signed, transformed URL.** The untransformed original is never
requested.

Signed URLs were chosen because they pass every security setting Cloudinary offers: Strict
transformations, and restricted media types such as "Uploaded". (Named transformations were dropped:
they add nothing once URLs are signed, and the docs say `f_auto` can't be used inside a named
transformation.)

**What the console settings actually do (measured on this account, 2026-11-11).** The design first
assumed, from the security FAQ, that ticking **Uploaded** blocks *every* unsigned `/image/upload/`
URL, originals included. That is **wrong**. After it was ticked and saved, originals and unsigned
thumbnails that had already been generated still returned 200, on CDN cache misses (`server-timing`
`desc=miss`), so the answer came from Cloudinary itself. They were still 200 ten minutes later. The
console's own description matches this: restricted types are "restricted from use with dynamic URLs.
Images of restricted services can only be *created* explicitly using the authenticated API or signed
URLs." In practice:

| Request | Strict transformations on | + "Uploaded" restricted |
|---|---|---|
| Signed URL (site `thumb_url` / `large_url`) | 200 | 200 |
| Signed URL, transformation never generated before | 200 (created) | 200 (created) |
| Fake signature, transformation never generated before | 401 | 401 |
| Unsigned transformation never generated before (e.g. `w_401`) | 401 | 401 |
| Unsigned transformation that already exists (e.g. old unsigned thumbnails) | 200 | 200 |
| **Untransformed original** `/image/upload/v…/<id>.jpg` | **200** | **200** |

So the current setup stops anyone **creating** new images (no transformation-quota abuse) and the
site no longer links to originals. It does **not** stop anyone who already has an original's URL
from downloading it at full size. Crawlers had harvested those URLs; that was the bandwidth problem.

Blocking originals would mean moving the photos to the **`private`** delivery type, where originals
need a signed URL. That needs a type change on all 4,134 assets, re-signing every URL for the new
type, a redeploy, and making the admin server upload as `private`. It probably also means
regenerating the derived images, roughly 4.1k transformations (~4.1 credits) for thumbnails plus
more for lightbox images as they are opened (an estimate). The exact API call and whether derived
images carry over are unverified; test on one photo first. **Decision (2026-11-11): not doing this
now.** Watch usage instead (§5) and convert only if bandwidth on originals climbs again.

- `_config.yml` → `feelings_images` (the single source of truth):
  - `thumb_transform: w_400,h_400,c_fill,g_auto,q_auto,f_auto`. This is the grid thumbnail. It is the
    same string as before, so already-generated thumbnails should be reused.
  - `large_transform: c_limit,w_2560,h_2560,q_auto,f_auto`. This is the lightbox and click-through
    image. It caps the long side at 2560 px and never upscales.
  - `large_max_px: 2560` must match the `w_`/`h_` values above; the scripts refuse to run otherwise.
    The template uses it to compute the lightbox dimensions.
- `_data/feelings.json`: each photo gets `thumb_url` and `large_url`, the signed URLs, written by
  `scripts/cloudinary_sign_urls.py`. A signature is computed with the API secret, but the signature
  itself is not secret. It authorises only that exact transformation of that image, so it is safe to
  commit and publish. Changing a transformation string means re-running the script.
- `_pages/feelings.md`: uses the signed URLs. It falls back to unsigned transformed URLs for unsigned
  photos. With Strict transformations on, that fallback only works if the image was already generated,
  so `--check` must pass before every deploy. The page was checked by rendering it with
  Liquid 4.0.4: 8,250 Cloudinary URLs, 0 originals, all lightbox dimensions correct, both with signed
  data and with unsigned fallback data.
- `scripts/admin_server.py`: new uploads are signed automatically. Admin thumbnails use the signed URL.
- `robots.txt`: disallows AI-training and dataset crawlers (Reflectionbot, GPTBot, CCBot, ClaudeBot,
  Bytespider, Google-Extended, …). Normal search engines are unchanged. This only affects discovery
  *through adamjeisen.com*, not URLs already harvested from `res.cloudinary.com`.
- `_config.yml` `exclude`: `scripts/` and the Python project files are no longer published to the
  live site.

Measured sizes (3 large photos, 3–6k px, Nov 2026; a small sample):

| Version | Average size |
|---|---|
| original (what the lightbox used to load) | ~3.5 MB |
| `c_limit` 2560 (now used) | ~550 KB |
| `c_limit` 2048 | ~420 KB |
| `c_limit` 1600 | ~280 KB |
| thumbnail | ~30 KB |

## 3. Rollout order

Credentials come from the environment in every step that needs them: `CLOUDINARY_URL`, or
`CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET`.

1. Sign the existing photos, then commit the updated `_data/feelings.json`:
   ```bash
   python scripts/cloudinary_sign_urls.py
   ```
   ```bash
   python scripts/cloudinary_sign_urls.py --check
   ```
2. Merge to `master` and let the deploy finish. On `/feelings/`, check that thumbnails load, the
   lightbox opens, and the image URLs contain `s--…--`.
3. Run `python scripts/cloudinary_check_delivery.py` for a baseline. Every probe should return 200 at
   this point.
4. Console → Settings → Security → **Strict transformations: on**. Leave *Allowed strict referral
   domains* empty; it isn't needed, because signed URLs pass. Run the checker with `--seed 1`.
   Expected: the SITE rows return 200, `w_401` is blocked, and originals still return 200 (strict
   mode doesn't cover originals).
5. Restricted image types → **tick Uploaded** (and **Fetched URL**). Run the checker with `--seed 2`.
   Expected, as measured: the SITE rows return 200 with and without a Referer, and `w_401` stays
   blocked. Originals and existing unsigned thumbnails **still return 200**: this setting does not block
   them (see §2). Ticking it is harmless and blocks *creating* images from unsigned URLs, which Strict
   transformations already does. If any SITE row fails, untick "Uploaded" right away.

   Status (2026-11-11): steps 1–5 done. Strict on; Uploaded and Fetched URL ticked; all SITE probes 200;
   a fake signature on a never-generated transformation returned 401 and the real signature 200.
6. Retiring the API key that signed the URLs: Cloudinary's docs don't say whether signed delivery URLs
   are checked against any active key's secret or only one key's secret (unverified). Before deleting
   the key that was used for signing, **deactivate** it in the console, then run the checker with a new
   `--seed`. If the SITE rows still return 200, delete the key. If they fail, reactivate the key and
   re-sign with a key you will keep.
7. Before every deploy, `cloudinary_sign_urls.py --check` must pass. The admin server signs new
   uploads, but a failed signing logs a warning and leaves that photo unsigned. With Strict
   transformations on, an unsigned new photo's thumbnail and lightbox image can't be generated, so
   that photo would be broken on the site.

Email to Cloudinary support (sent via the support portal on 2026-11-11, based on this draft):

> Hi, my free account (cloud `dpxqdgavv`) went over its credit limit because of crawler traffic, not
> my site: about 95% of the last 30 days' bandwidth had a referrer of res.cloudinary.com or none, with
> user agents like Reflectionbot and headless Chrome from Singapore datacenters. I've since switched
> the site to signed, size-limited URLs, enabled strict transformations and restricted the upload
> delivery type. Could you give me a grace period past Nov 17 while the 30-day window rolls over? Could you
> also set up a referral-domain allowlist for adamjeisen.com on this account? Thanks, Adam

## 4. Daily usage report

`scripts/cloudinary_usage.py` (credentials from the environment, as above):

```bash
python scripts/cloudinary_usage.py inspect
```

```bash
python scripts/cloudinary_usage.py daily --semantics per_day --out cloudinary_daily_usage.csv
```

**Confirmed 2026-11-11: a per-date `usage(date=…)` call returns that day's usage (`per_day`).**
The 30 per-date bandwidth values (2026-10-12 … 11-10) summed to 22.11 GiB, against a current total of
22.40 GiB (ratio 0.99). The latest single day was 0.056 GB, so it isn't a rolling 30-day total, and 15 of
29 days were lower than the day before, so it isn't cumulative. Each `date_requested` echoed the
requested `yyyy-mm-dd` date. Also confirmed: bandwidth credits = bytes / 2^30 (GiB), and
`credits.usage` = bandwidth + storage + transformations credits (22.40 + 11.92 + 1.18 = 35.50).

How this was established: `inspect` dumps the raw responses and prints a diagnostic (the sum of the per-date
values versus the current total). `daily` refuses to run without an explicit `--semantics`, so no daily
numbers are reported until you have confirmed which it is. If it turns out to be `rolling30`, single
days cannot be recovered from the API. The script says so and reports the window's net change instead.

Spike days are flagged when the value exceeds median + 3 × 1.4826 × MAD, a robust z-score above 3; set
the multiplier with `--k`. The top 5 days are always listed. Output CSVs and raw JSON are git-ignored.

Date format: the official usage doc says `date` is `yyyy-mm-dd`. The Python SDK, however, encodes a
`datetime.date` as `dd-mm-yyyy` (and sends a string unchanged). The script sends the documented form
by default. `inspect --show <date>` prints the response for both forms, and `daily` refuses to run
unless each response's `date_requested` echoes the requested date. Use `--date-form sdk` to switch.

## 5. Watching for a return of crawler traffic

Because originals can still be downloaded by anyone who has their URL (§2), watch daily bandwidth.
Credentials are needed:

```bash
python scripts/cloudinary_usage.py daily --semantics per_day --days 14 --out cloudinary_daily_usage.csv
```

Reference points (2026-10-12 … 11-10, after the site stopped linking originals on 11-11, so future
site traffic should be lower than this):

- typical day: median 0.23 GB;
- spike days were 1.0–6.8 GB (Oct 13–14, Nov 2–7). Together those 8 days were 82% of the window's bandwidth;
- after the crawlers stopped: 0.01 GB/day (Nov 8–9) and 0.06 GB (Nov 10).

**Trigger for converting to `private` (§2):** any day above ~0.8 GB (the script's spike threshold for
that window was 0.78 GB), or several days in a row well above the post-Nov-11 baseline. The usage
API doesn't break bandwidth down by URL. To confirm the traffic is for originals, check the
Cloudinary console's reports, if the plan includes them, or probe whether the spike matches harvested
`/image/upload/v…` URLs. Prefer converting after the 30-day window has recovered, because the
conversion itself costs transformation credits.

Projection, not a measurement: with near-zero bandwidth from 11-11 on, usage first drops below 100%
around 2026-11-27, or around 12-04 at 0.23 GB/day. This assumes the 30-day window ends the day before
and that storage (11.92 credits) and transformations (1.18) stay flat. The Nov 2–7 spike leaves the
window in early December.
