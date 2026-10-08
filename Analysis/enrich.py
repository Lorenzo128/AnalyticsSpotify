"""Fetch genres, artist origins and similar artists from MusicBrainz / ListenBrainz.

Run this once (it takes ~20 minutes, mostly waiting on MusicBrainz's one-request-
per-second limit); results are cached, so later runs only fetch what's new.

Usage:
    python enrich.py --data ../Data
"""
import argparse
from pathlib import Path

from spotify_analysis.deep import artist_hours, artist_mbids, similar_candidates, top_track_per_artist
from spotify_analysis.enrich import Cache, Client, enrich_artists, enrich_mbids, enrich_similar
from spotify_analysis.load import load_streams


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=here.parent / "Data")
    ap.add_argument("--cache", type=Path, default=here / "cache" / "musicbrainz.json")
    ap.add_argument("--min-streams", type=int, default=20, help="enrich artists with at least this many streams")
    ap.add_argument("--seeds", type=int, default=150, help="top artists to fetch similar artists for")
    ap.add_argument("--candidates", type=int, default=150, help="suggested artists to fetch genres for")
    args = ap.parse_args()

    df = load_streams(args.data)
    cache, mb = Cache(args.cache), Client(min_interval=1.1)

    streams = df[df["is_stream"]].groupby("artist").size()
    tracks = top_track_per_artist(df)
    wanted = [a for a in artist_hours(df).index if streams.get(a, 0) >= args.min_streams]
    print(f"1/3 MusicBrainz: {len(wanted)} artists with ≥{args.min_streams} streams")
    enrich_artists(cache, mb, [(a, tracks.get(a, "")) for a in wanted])

    mbids = artist_mbids(cache.data)
    seeds = [mbids[a] for a in artist_hours(df).index if a in mbids][:args.seeds]
    print(f"2/3 ListenBrainz: similar artists for your top {len(seeds)} artists")
    enrich_similar(cache, Client(min_interval=0.5), seeds)

    cands = similar_candidates(df, cache.data, n_seeds=args.seeds)
    # The overall top picks plus each seed's own top picks, so every scene gets genre labels.
    per_seed = cands.assign(seed=cands["because"].str[0]).groupby("seed").head(3)
    wanted_mbids = list(dict.fromkeys(cands.head(args.candidates)["mbid"].tolist() + per_seed["mbid"].tolist()))
    print(f"3/3 MusicBrainz: genres for {len(wanted_mbids)} suggested artists")
    enrich_mbids(cache, mb, wanted_mbids)

    cache.save()
    found = sum(1 for a in wanted if cache.data["artists"].get(a, {}).get("mbid"))
    print(f"Done. Matched {found}/{len(wanted)} artists. Cache: {args.cache}")


if __name__ == "__main__":
    main()
