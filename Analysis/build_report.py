"""Build the interactive music report from a Spotify data export.

Usage:
    python build_report.py --data ../Data --out output/report.html
"""
import argparse
import time
from pathlib import Path

from spotify_analysis.load import load_account, load_streams
from spotify_analysis.report import build_report


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=here.parent / "Data",
                    help="folder containing 'Spotify Extended Streaming History' (default: ../Data)")
    ap.add_argument("--out", type=Path, default=here / "output" / "report.html", help="output HTML file")
    args = ap.parse_args()

    t0 = time.time()
    df = load_streams(args.data)
    acct = load_account(args.data)
    print(f"Loaded {len(df):,} music plays ({df['minutes'].sum() / 60:,.0f} h) in {time.time() - t0:.1f}s")

    page = build_report(df, acct)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(page, encoding="utf-8")
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1e6:.1f} MB) in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
