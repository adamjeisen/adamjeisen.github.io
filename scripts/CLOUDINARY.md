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

Cloudinary's docs settled the design. On *Restricted media types* the security FAQ
(`developer_onboarding_faq_account_security`) says: "if you select any of these features or delivery
types, then those types of URLs can be delivered only as signed URLs or if they are pre-generated as
eager transformations." Ticking **Uploaded** therefore blocks *every* unsigned `/image/upload/` URL,
thumbnails and lightbox images included, not just originals. Marking transformations "allowed for
strict" is not enough to survive that setting. Signed URLs satisfy both Strict transformations and
the restricted "Uploaded" type. (Named transformations were dropped: they add nothing once URLs are
signed, and the docs say `f_auto` can't be used inside a named transformation.)

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
  photos, which only works until "Uploaded" is restricted. The page was checked by rendering it with
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
5. Restricted media types → **tick Uploaded** (and **Fetched URL**). Run the checker with `--seed 2`.
   Expected: the SITE rows return 200 with and without a Referer; originals and unsigned thumbnails
   are blocked. If any SITE row fails, untick "Uploaded" right away.
6. Before every deploy, `cloudinary_sign_urls.py --check` must pass. The admin server signs new
   uploads, but a failed signing logs a warning and leaves that photo unsigned, so it would be broken
   on the site once "Uploaded" is restricted.

Email to Cloudinary support (draft):

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

What a per-date `usage(date=…)` call returns (that day only, cumulative, or a rolling 30-day total) is
**unverified**. `inspect` dumps the raw responses and prints a diagnostic (the sum of the per-date
values versus the current total). `daily` refuses to run without an explicit `--semantics`, so no daily
numbers are reported until you have confirmed which it is. If it turns out to be `rolling30`, single
days cannot be recovered from the API. The script says so and reports the window's net change instead.

Spike days are flagged when the value exceeds median + 3 × 1.4826 × MAD, a robust z-score above 3; set
the multiplier with `--k`. The top 5 days are always listed. Output CSVs and raw JSON are git-ignored.

Date format: the official usage doc says `date` is `yyyy-mm-dd`. The Python SDK, however, encodes a
`datetime.date` as `dd-mm-yyyy` (and sends a string unchanged). The script sends the documented form
by default. `inspect --show <date>` prints the response for both forms, and `daily` refuses to run
unless each response's `date_requested` echoes the requested date. Use `--date-form sdk` to switch.
