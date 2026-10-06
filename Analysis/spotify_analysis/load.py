"""Load a Spotify data export into tidy pandas frames.

Only music is kept: podcast, audiobook and video rows are dropped, and so are
personal fields (IP address, username, email, birthdate, follow lists) so they
can never leak into a generated report.
"""
import json
from pathlib import Path

import pandas as pd

STREAMING_DIR = "Spotify Extended Streaming History"
ACCOUNT_DIR = "Spotify Account Data"

# Spotify counts a "stream" once at least 30 seconds were played.
STREAM_MIN_MS = 30_000

# Timestamps are UTC; convert each play to the local time of the country it was
# played from. Unknown countries fall back to DEFAULT_TZ.
DEFAULT_TZ = "Europe/Zurich"
COUNTRY_TZ = {
    "CH": "Europe/Zurich", "IT": "Europe/Rome", "FR": "Europe/Paris",
    "DE": "Europe/Berlin", "AT": "Europe/Vienna", "BE": "Europe/Brussels",
    "NL": "Europe/Amsterdam", "ES": "Europe/Madrid", "PT": "Europe/Lisbon",
    "GB": "Europe/London", "EE": "Europe/Tallinn", "TR": "Europe/Istanbul",
    "MA": "Africa/Casablanca", "IL": "Asia/Jerusalem", "JP": "Asia/Tokyo",
    "SG": "Asia/Singapore", "KH": "Asia/Phnom_Penh", "VN": "Asia/Ho_Chi_Minh",
    "TH": "Asia/Bangkok", "LA": "Asia/Vientiane", "US": "America/New_York",
    "CA": "America/Toronto",
}

COUNTRY_NAMES = {
    "CH": "Switzerland", "IT": "Italy", "FR": "France", "DE": "Germany",
    "AT": "Austria", "BE": "Belgium", "NL": "Netherlands", "ES": "Spain",
    "PT": "Portugal", "GB": "United Kingdom", "EE": "Estonia", "TR": "Turkey",
    "MA": "Morocco", "IL": "Israel", "JP": "Japan", "SG": "Singapore",
    "KH": "Cambodia", "VN": "Vietnam", "TH": "Thailand", "LA": "Laos",
    "US": "United States", "CA": "Canada",
}

_DROP_COLUMNS = [
    "ip_addr", "episode_name", "episode_show_name", "spotify_episode_uri",
    "audiobook_title", "audiobook_uri", "audiobook_chapter_uri",
    "audiobook_chapter_title", "offline_timestamp",
]

_RENAME = {
    "master_metadata_track_name": "track",
    "master_metadata_album_artist_name": "artist",
    "master_metadata_album_album_name": "album",
    "spotify_track_uri": "track_uri",
    "conn_country": "country",
    "incognito_mode": "incognito",
}


def normalise_platform(raw):
    """Collapse Spotify's many platform strings into a readable device family."""
    p = (raw or "").lower()
    if "ps4" in p or "playstation" in p:
        return "PlayStation"
    if "cast" in p or "freebox" in p or "chromecast" in p:
        return "Chromecast / TV"
    if "denon" in p or "smsc" in p or "speaker" in p or "sonos" in p:
        return "Speakers / hi-fi"
    if p.startswith("ios") or "iphone" in p or "ipad" in p:
        return "iPhone"
    if p.startswith("osx") or p.startswith("os x") or "mac" in p:
        return "Mac"
    if "android" in p:
        return "Android"
    if "windows" in p:
        return "Windows"
    if "web" in p:
        return "Web player"
    return "Other / unknown"


def _read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_streams(data_dir):
    """Return one row per music play, with local-time and derived columns."""
    files = sorted((Path(data_dir) / STREAMING_DIR).glob("Streaming_History_Audio_*.json"))
    if not files:
        raise FileNotFoundError(f"No Streaming_History_Audio_*.json under {Path(data_dir) / STREAMING_DIR}")
    rows = [r for f in files for r in _read_json(f)]
    df = pd.DataFrame(rows)
    df = df[df["spotify_track_uri"].notna()].copy()
    df = df.drop(columns=[c for c in _DROP_COLUMNS if c in df.columns]).rename(columns=_RENAME)

    df["ts_utc"] = pd.to_datetime(df["ts"], utc=True)
    df = df.drop(columns="ts").sort_values("ts_utc").reset_index(drop=True)
    df["country"] = df["country"].fillna("ZZ")
    tz = df["country"].map(COUNTRY_TZ).fillna(DEFAULT_TZ)
    local = pd.Series(index=df.index, dtype="datetime64[ns]")
    for zone, idx in df.groupby(tz).groups.items():
        local.loc[idx] = df.loc[idx, "ts_utc"].dt.tz_convert(zone).dt.tz_localize(None)
    # `ts` marks when the play ended, so the start is a better anchor for clock-time stats.
    df["end_local"] = local
    df["ts_local"] = local - pd.to_timedelta(df["ms_played"], unit="ms")

    df["minutes"] = df["ms_played"] / 60_000
    df["is_stream"] = df["ms_played"] >= STREAM_MIN_MS
    df["skipped"] = df["skipped"].fillna(False).astype(bool) | (df["reason_end"] == "fwdbtn")
    for col in ("shuffle", "offline", "incognito"):
        df[col] = df[col].fillna(False).astype(bool)
    df["device"] = df["platform"].map(normalise_platform)
    df["date"] = df["ts_local"].dt.normalize()
    df["year"] = df["ts_local"].dt.year
    df["month"] = df["ts_local"].dt.to_period("M").dt.to_timestamp()
    df["weekday"] = df["ts_local"].dt.weekday
    df["hour"] = df["ts_local"].dt.hour
    return df


def _final_search_queries(raw):
    """Search history is logged per keystroke; keep only the query a user settled on."""
    q = pd.DataFrame(raw)
    if q.empty:
        return pd.DataFrame(columns=["time", "query", "clicked", "clicked_uri"])
    q["time"] = pd.to_datetime(q["searchTime"].str.replace(r"\[.*\]$", "", regex=True), utc=True)
    q["query"] = q["searchQuery"].fillna("").str.strip()
    q["clicked"] = q["searchInteractionURIs"].map(bool)
    q["clicked_uri"] = q["searchInteractionURIs"].map(lambda u: u[0] if u else None)
    q = q[q["query"] != ""].sort_values("time").reset_index(drop=True)
    # Keystrokes less than a minute apart belong to the same search; keep its last query,
    # plus any intermediate query whose results were clicked.
    burst = (q["time"].diff().dt.total_seconds().fillna(1e9) > 60).cumsum()
    is_last = burst != burst.shift(-1)
    final = q[is_last | q["clicked"]]
    return final[["time", "query", "clicked", "clicked_uri"]].reset_index(drop=True)


def load_account(data_dir):
    """Load the music-related account files. Missing files yield empty values."""
    base = Path(data_dir) / ACCOUNT_DIR

    def opt(name, default):
        path = base / name
        return _read_json(path) if path.exists() else default

    library = opt("YourLibrary.json", {})
    liked = pd.DataFrame(library.get("tracks", []), columns=["artist", "album", "track", "uri"])

    playlists, items = [], []
    for pl_file in sorted(base.glob("Playlist*.json")):
        for pl in _read_json(pl_file).get("playlists", []):
            playlists.append({
                "name": pl.get("name", "").strip() or "(untitled)",
                "last_modified": pl.get("lastModifiedDate"),
                "followers": pl.get("numberOfFollowers", 0),
                "tracks": len(pl.get("items", [])),
            })
            for it in pl.get("items", []):
                t = it.get("track") or {}
                if not t.get("trackUri"):
                    continue  # episodes / local files
                items.append({
                    "playlist": pl.get("name", "").strip() or "(untitled)",
                    "track": t.get("trackName"), "artist": t.get("artistName"),
                    "uri": t.get("trackUri"), "added": it.get("addedDate"),
                })

    return {
        "liked": liked,
        "playlists": pd.DataFrame(playlists),
        "playlist_items": pd.DataFrame(items, columns=["playlist", "track", "artist", "uri", "added"]),
        "searches": _final_search_queries(opt("SearchQueries.json", [])),
        "wrapped": opt("Wrapped2025.json", {}),
        "sound_capsule": opt("YourSoundCapsule.json", {}),
        "marquee": pd.DataFrame(opt("Marquee.json", []), columns=["artistName", "segment"]),
    }

