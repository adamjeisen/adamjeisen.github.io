#!/usr/bin/env python3
"""Per-day Cloudinary bandwidth / request report.

Two steps, on purpose. The meaning of `cloudinary.api.usage(date=...)` has NOT been
verified for this account: a per-date call could return that day's usage, a
cumulative-to-date figure, or the rolling 30-day total as of that date. Daily
numbers are only computed after you have looked at the raw responses and told the
script which one it is.

STEP 1 - inspect (prints raw JSON + a diagnostic; writes nothing derived):

    python scripts/cloudinary_usage.py inspect                 # last 30 days + current
    python scripts/cloudinary_usage.py inspect --show 2026-10-20

  How to read the diagnostic it prints ("current" = usage() with no date, which the
  free plan reports as the rolling 30-day total; it should match the console's
  ~13.81 GB / ~19.14K requests):
    * per_day:    each date's bandwidth is small, varies a lot day to day, and the
                  SUM over the last 30 dates ~= current.
    * rolling30:  each date's bandwidth is itself on the order of current (GBs),
                  changes smoothly, and the most recent date ~= current.
    * cumulative: values only ever increase within a period (then drop to ~0 at a
                  reset), and the latest value ~= current.
  Also check that `date_requested` echoes the date you asked for, and note the
  units of bandwidth.usage (expected: bytes) and whether `credits_usage` fields exist.

STEP 2 - daily report, once the semantics are confirmed:

    python scripts/cloudinary_usage.py daily --semantics per_day --out cloudinary_daily_usage.csv

  --semantics per_day     day value = the value returned for that date.
  --semantics cumulative  day value = value(d) - value(d-1); a negative difference is
                          treated as a period reset and the day value is value(d).
  --semantics rolling30   individual days are NOT recoverable from a rolling window:
                          value(d) - value(d-1) = day(d) - day(d-30). The CSV then
                          reports the rolling value and this net change, and the
                          "spikes" are days where the window gained the most. The
                          console's own daily chart is the better source in that case.

Notes:
  * Date format: the official docs say `date` is "yyyy-mm-dd", but the Python SDK
    encodes a datetime.date object as dd-mm-yyyy (and sends a string unchanged).
    This script sends the documented "yyyy-mm-dd" string by default; `inspect --show`
    prints the response for BOTH forms so you can see which one the API honours, and
    `daily` refuses to run unless every response's date_requested echoes the date
    that was asked for (--date-form sdk switches to the SDK's encoding).
  * GB here means 10^9 bytes. If the response has bandwidth.credits_usage, that is
    Cloudinary's own credit figure and is reported alongside.
  * One Admin API call per date (rate limit: 500/hour on the free plan).
  * The most recent day may be incomplete ("numbers are updated periodically").
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import statistics
import sys
from typing import Any

from cloudinary_common import configure_cloudinary

GB = 1e9


# ---------------------------------------------------------------- fetching ---

DATE_FORM = "iso"  # "iso": send "yyyy-mm-dd" (official docs); "sdk": send a date object (SDK -> dd-mm-yyyy)


def fetch(api, date: dt.date | None, form: str | None = None) -> dict:
    if date is None:
        return dict(api.usage())
    form = form or DATE_FORM
    return dict(api.usage(date=date.isoformat() if form == "iso" else date))


def echoes(date: dt.date, date_requested) -> bool:
    """True if the response's date_requested refers to `date`."""
    s = str(date_requested or "")
    return s.startswith(date.isoformat()) or s.startswith(date.strftime("%d-%m-%Y"))


def dates_back(days: int, end: dt.date) -> list[dt.date]:
    """`days` consecutive dates ending at `end` (inclusive), oldest first."""
    return [end - dt.timedelta(days=i) for i in range(days - 1, -1, -1)]


def get(d: dict, *path: str) -> Any:
    for k in path:
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def metrics(r: dict) -> dict:
    """Pull the fields we care about; None where absent (never guessed)."""
    return {
        "date_requested": r.get("date_requested"),
        "last_updated": r.get("last_updated"),
        "bandwidth_bytes": get(r, "bandwidth", "usage"),
        "bandwidth_credits": get(r, "bandwidth", "credits_usage"),
        "requests": r.get("requests"),
        "transformations": get(r, "transformations", "usage"),
        "credits_usage": get(r, "credits", "usage"),
    }


# ----------------------------------------------------------------- inspect ---

def cmd_inspect(api, args) -> None:
    if args.show:
        for s in args.show:
            d = dt.date.fromisoformat(s)
            for form, desc in (("iso", f'date="{d.isoformat()}" (documented form)'),
                               ("sdk", f"date=datetime.date -> /usage/{d.strftime('%d-%m-%Y')}")):
                print(f"===== usage({desc}) =====")
                try:
                    print(json.dumps(fetch(api, d, form), indent=2, default=str))
                except Exception as e:  # show the API's answer verbatim
                    print(f"ERROR: {e!r}")
        return

    end = dt.date.today() - dt.timedelta(days=1)
    dates = dates_back(args.days, end)
    current = fetch(api, None)
    raw = {"current": current}
    print("===== usage() with no date (current) =====")
    print(json.dumps(current, indent=2, default=str))

    rows = []
    for d in dates:
        r = fetch(api, d)
        raw[d.isoformat()] = r
        rows.append((d, metrics(r)))
    print(f"\n===== usage(date=...) for {dates[0]} .. {dates[-1]} (one raw sample) =====")
    print(json.dumps(raw[dates[-1].isoformat()], indent=2, default=str))

    if args.raw_out:
        with open(args.raw_out, "w") as f:
            json.dump(raw, f, indent=2, default=str)
        print(f"\nAll raw responses written to {args.raw_out}")

    cur = metrics(current)
    print("\n===== per-date key fields (raw values, no interpretation) =====")
    print(f"{'date':<11} {'date_requested':<22} {'bandwidth_bytes':>16} {'requests':>10} "
          f"{'bw_credits':>10} {'last_updated'}")
    for d, m in rows:
        print(f"{d.isoformat():<11} {str(m['date_requested']):<22} {str(m['bandwidth_bytes']):>16} "
              f"{str(m['requests']):>10} {str(m['bandwidth_credits']):>10} {m['last_updated']}")
    print(f"{'current':<11} {str(cur['date_requested']):<22} {str(cur['bandwidth_bytes']):>16} "
          f"{str(cur['requests']):>10} {str(cur['bandwidth_credits']):>10} {cur['last_updated']}")

    print("\n===== diagnostic =====")
    bw = [m["bandwidth_bytes"] for _, m in rows]
    if any(v is None for v in bw) or cur["bandwidth_bytes"] is None:
        print("bandwidth.usage missing in some responses; inspect the raw JSON above.")
        return
    c = cur["bandwidth_bytes"]
    s = sum(bw)
    diffs = [b - a for a, b in zip(bw, bw[1:])]
    print(f"current (no date) bandwidth          : {c / GB:10.3f} GB")
    print(f"SUM of the {len(bw)} per-date values      : {s / GB:10.3f} GB   (ratio to current {s / c if c else float('nan'):.2f})")
    print(f"latest per-date value ({dates[-1]})  : {bw[-1] / GB:10.3f} GB   (ratio to current {bw[-1] / c if c else float('nan'):.2f})")
    print(f"median per-date value                : {statistics.median(bw) / GB:10.3f} GB")
    print(f"day-over-day decreases               : {sum(x < 0 for x in diffs)} of {len(diffs)}")
    mism = [(d, m["date_requested"]) for d, m in rows if not echoes(d, m["date_requested"])]
    if mism:
        print(f"WARNING: date_requested does not echo the requested date for {len(mism)} calls, e.g. {mism[:3]}")
    print("\nInterpretation guide: SUM ~= current -> per_day; latest ~= current and values"
          " smooth -> rolling30; monotone increases with occasional drops -> cumulative."
          " Do not run `daily` until you are sure.")


# ------------------------------------------------------------------- daily ---

def robust_spikes(values: list[float], k: float) -> tuple[float, float, list[int]]:
    """Indices with value > median + k * 1.4826 * MAD (MAD scaled to ~sigma)."""
    med = statistics.median(values)
    mad = statistics.median([abs(v - med) for v in values])
    thr = med + k * 1.4826 * mad
    if mad == 0:
        print("  note: MAD = 0 (over half the days identical); threshold = median, so any day above it is flagged")
    return med, thr, [i for i, v in enumerate(values) if v > thr]


def cmd_daily(api, args) -> None:
    end = dt.date.today() - dt.timedelta(days=1)
    n_fetch = args.days + (1 if args.semantics in ("cumulative", "rolling30") else 0)
    dates = dates_back(n_fetch, end)
    ms = [(d, metrics(fetch(api, d))) for d in dates]
    for d, m in ms:
        if m["bandwidth_bytes"] is None or m["requests"] is None:
            sys.exit(f"{d}: bandwidth.usage or requests missing from the response; run `inspect`.")
        if not echoes(d, m["date_requested"]):
            sys.exit(f"{d}: response date_requested={m['date_requested']!r} does not match the "
                     "requested date, so the date was not honoured. Try --date-form sdk / check `inspect --show`.")

    out_rows = []
    if args.semantics == "per_day":
        for d, m in ms:
            out_rows.append({"date": d.isoformat(),
                             "bandwidth_bytes": m["bandwidth_bytes"],
                             "bandwidth_gb": m["bandwidth_bytes"] / GB,
                             "bandwidth_credits": m["bandwidth_credits"],
                             "requests": m["requests"]})
        value_key, label = "bandwidth_gb", "daily bandwidth (GB)"
    elif args.semantics == "cumulative":
        for (_, p), (d, m) in zip(ms, ms[1:]):
            db = m["bandwidth_bytes"] - p["bandwidth_bytes"]
            dr = m["requests"] - p["requests"]
            reset = db < 0 or dr < 0
            if reset:
                db, dr = m["bandwidth_bytes"], m["requests"]
            out_rows.append({"date": d.isoformat(), "bandwidth_bytes": db, "bandwidth_gb": db / GB,
                             "requests": dr, "period_reset": reset,
                             "cumulative_bandwidth_bytes": m["bandwidth_bytes"],
                             "cumulative_requests": m["requests"]})
        value_key, label = "bandwidth_gb", "daily bandwidth (GB, from differences)"
    else:  # rolling30
        for (_, p), (d, m) in zip(ms, ms[1:]):
            out_rows.append({"date": d.isoformat(),
                             "rolling30_bandwidth_gb": m["bandwidth_bytes"] / GB,
                             "rolling30_requests": m["requests"],
                             "net_change_gb": (m["bandwidth_bytes"] - p["bandwidth_bytes"]) / GB,
                             "net_change_requests": m["requests"] - p["requests"]})
        value_key, label = "net_change_gb", "net change of rolling 30-day bandwidth (GB) = day(d) - day(d-30)"

    with open(args.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        w.writerows(out_rows)

    print(f"Semantics: {args.semantics}   (wrote {len(out_rows)} rows to {args.out})")
    print(f"{'date':<11} " + " ".join(f"{k:>22}" for k in out_rows[0] if k != "date"))
    for r in out_rows:
        print(f"{r['date']:<11} " + " ".join(
            f"{v:>22.3f}" if isinstance(v, float) else f"{str(v):>22}"
            for k, v in r.items() if k != "date"))

    vals = [r[value_key] for r in out_rows]
    med, thr, idx = robust_spikes(vals, args.k)
    print(f"\nSpike rule on {label}: value > median + {args.k} x 1.4826 x MAD")
    print(f"  median = {med:.3f}, threshold = {thr:.3f}")
    if idx:
        for i in sorted(idx, key=lambda i: -vals[i]):
            print(f"  SPIKE {out_rows[i]['date']}: {vals[i]:.3f}")
    else:
        print("  no days above threshold")
    top = sorted(range(len(vals)), key=lambda i: -vals[i])[:5]
    print("Top 5 days: " + ", ".join(f"{out_rows[i]['date']} ({vals[i]:.3f})" for i in top))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("inspect", help="dump raw responses and a semantics diagnostic")
    pi.add_argument("--days", type=int, default=30)
    pi.add_argument("--show", nargs="+", metavar="YYYY-MM-DD", help="only dump raw JSON for these dates")
    pi.add_argument("--raw-out", default="cloudinary_usage_raw.json",
                    help="file for all raw responses (git-ignored; '' to skip)")

    pd = sub.add_parser("daily", help="per-day CSV (requires confirmed --semantics)")
    pd.add_argument("--semantics", required=True, choices=["per_day", "cumulative", "rolling30"],
                    help="what a per-date usage() call returns, as confirmed with `inspect`")
    pd.add_argument("--days", type=int, default=30)
    pd.add_argument("--out", default="cloudinary_daily_usage.csv")
    pd.add_argument("--k", type=float, default=3.0, help="spike threshold in robust SDs (default 3)")
    for sp in (pi, pd):
        sp.add_argument("--date-form", choices=["iso", "sdk"], default="iso",
                        help='iso: send "yyyy-mm-dd" (documented, default); sdk: SDK date encoding (dd-mm-yyyy)')

    args = ap.parse_args()
    global DATE_FORM
    DATE_FORM = args.date_form
    configure_cloudinary()
    import cloudinary.api as api

    (cmd_inspect if args.cmd == "inspect" else cmd_daily)(api, args)


if __name__ == "__main__":
    main()
