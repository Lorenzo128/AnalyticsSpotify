"""Optional enrichment from public music databases, cached on disk.

* MusicBrainz (https://musicbrainz.org): artist id, country of origin and genres.
* ListenBrainz (https://listenbrainz.org): artists that listeners play together.

Only artist and track names are sent. Requests are rate limited (MusicBrainz
allows about one per second) and every answer is cached in a JSON file, so a
re-run only fetches what is missing and the report build never needs network.
"""
import json
import re
import socket
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = "AnalyticsSpotify/0.2 ( https://github.com/Lorenzo128/AnalyticsSpotify )"
MB_URL = "https://musicbrainz.org/ws/2/"
LB_SIMILAR_URL = "https://labs.api.listenbrainz.org/similar-artists/json"
LB_ALGORITHM = "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30"


def norm(name):
    """Lower-case, accent-free, punctuation-free form used to compare artist names."""
    s = str(name).replace("×", " x ")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _clean_title(title):
    """'Song (feat. X) - Remastered 2011' -> 'Song', for a more forgiving search."""
    t = re.split(r"\s[-–]\s", str(title))[0]
    return re.sub(r"\s*[(\[].*?[)\]]", "", t).strip() or str(title)


def _quote(s):
    return '"' + re.sub(r'(["\\])', r"\\\1", str(s)) + '"'


class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.data = {"artists": {}, "mbids": {}, "similar": {}}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(self.path)


class Client:
    def __init__(self, min_interval=1.1):
        self.min_interval = min_interval
        self._last = 0.0

    def get(self, url, params):
        full = url + "?" + urllib.parse.urlencode(params)
        for attempt in range(4):
            wait = self.min_interval - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return None
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, json.JSONDecodeError):
                time.sleep(2 * (attempt + 1))
        return None


def _find_mbid(client, artist, track):
    """Find the MusicBrainz id of `artist`, using one of their tracks to disambiguate."""
    want = norm(artist)
    q = f"recording:{_quote(_clean_title(track))} AND artist:{_quote(artist)}"
    res = client.get(MB_URL + "recording/", {"query": q, "fmt": "json", "limit": 10}) or {}
    for rec in res.get("recordings", []):
        for credit in rec.get("artist-credit", []):
            a = credit.get("artist", {}) if isinstance(credit, dict) else {}
            if a.get("id") and norm(a.get("name", "")) == want:
                return a["id"]
    res = client.get(MB_URL + "artist/", {"query": f"artist:{_quote(artist)}", "fmt": "json", "limit": 5}) or {}
    exact = [a for a in res.get("artists", []) if norm(a.get("name", "")) == want]
    if exact:
        return max(exact, key=lambda a: a.get("score", 0))["id"]
    return None


def _lookup(client, mbid):
    d = client.get(MB_URL + f"artist/{mbid}", {"inc": "genres", "fmt": "json"}) or {}
    return {
        "name": d.get("name"),
        "country": d.get("country"),
        "type": d.get("type"),
        "begin": (d.get("life-span") or {}).get("begin"),
        "disambiguation": d.get("disambiguation", ""),
        "genres": {g["name"]: g.get("count", 1) for g in d.get("genres", [])},
    }


def enrich_artists(cache, client, artists, progress=print):
    """artists: list of (artist name, representative track). Fills cache['artists'] and ['mbids']."""
    todo = [(a, t) for a, t in artists if a not in cache.data["artists"]]
    for i, (artist, track) in enumerate(todo, 1):
        mbid = _find_mbid(client, artist, track)
        cache.data["artists"][artist] = {"mbid": mbid}
        if mbid and mbid not in cache.data["mbids"]:
            cache.data["mbids"][mbid] = _lookup(client, mbid)
        if i % 20 == 0 or i == len(todo):
            cache.save()
            progress(f"  artists {i}/{len(todo)}")


def enrich_similar(cache, client, mbids, progress=print):
    todo = [m for m in mbids if m not in cache.data["similar"]]
    for i, mbid in enumerate(todo, 1):
        res = client.get(LB_SIMILAR_URL, {"artist_mbids": mbid, "algorithm": LB_ALGORITHM})
        rows = res if isinstance(res, list) else []
        cache.data["similar"][mbid] = [
            {"mbid": r.get("artist_mbid"), "name": r.get("name"), "score": r.get("score", 0),
             "comment": r.get("comment", "")}
            for r in rows if r.get("artist_mbid")]
        if i % 20 == 0 or i == len(todo):
            cache.save()
            progress(f"  similar {i}/{len(todo)}")


def enrich_mbids(cache, client, mbids, progress=print):
    todo = [m for m in mbids if m not in cache.data["mbids"]]
    for i, mbid in enumerate(todo, 1):
        cache.data["mbids"][mbid] = _lookup(client, mbid)
        if i % 20 == 0 or i == len(todo):
            cache.save()
            progress(f"  candidates {i}/{len(todo)}")


def load_cache(path):
    """Return the cache dict, or None when no enrichment has been run."""
    path = Path(path)
    if not path.exists():
        return None
    return Cache(path).data
