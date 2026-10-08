"""Build the interactive music report from a Spotify data export.

Usage:
    python build_report.py --data ../Data --out output/report.html
"""
import argparse
import time
from pathlib import Path

from spotify_analysis.enrich import load_cache
from spotify_analysis.load import load_account, load_streams
from spotify_analysis.report import build_report


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=here.parent / "Data",
                    help="folder containing 'Spotify Extended Streaming History' (default: ../Data)")
    ap.add_argument("--out", type=Path, default=here / "output" / "report.html", help="output HTML file")
    ap.add_argument("--cache", type=Path, default=here / "cache" / "musicbrainz.json",
                    help="enrichment cache written by enrich.py (optional)")
    args = ap.parse_args()

    t0 = time.time()
    df = load_streams(args.data)
    acct = load_account(args.data)
    print(f"Loaded {len(df):,} music plays ({df['minutes'].sum() / 60:,.0f} h) in {time.time() - t0:.1f}s")

    cache = load_cache(args.cache)
    print("Using enrichment cache" if cache else "No enrichment cache: genre and suggestion sections will be limited "
          "(run enrich.py)")
    page = build_report(df, acct, cache)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB) in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
