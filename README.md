# Spotify music listening report

**[View the report →](https://claude.ai/artifact/XUXUHdgvDyUryEMZruRzYV)** (private link: sign in to claude.ai to open it)

Turns a Spotify data export into a single interactive HTML report about your **music** listening.
Podcasts, audiobooks, video and technical logs are left out.

The report covers:

1. **Overview**: total hours, streams, unique tracks/artists/albums, busiest day
2. **Listening over time**: hours per month and year, running total and milestones
3. **Top charts**: top artists, tracks and albums by hours or streams, all time or per year
4. **Taste evolution**: rank chart of your biggest artists, top 5 per year, focus vs variety, same-artist streaks
5. **Daily rhythm**: day × hour heatmap in local time, months of the year, days of the week
6. **Discovery & loyalty**: new artists per month, one-week obsessions, artists present every year, forgotten favourites
7. **Listening behaviour**: skip, shuffle and offline rates, how tracks start and end, most and least skipped
8. **Where & how**: countries over time, music abroad, devices
9. **Sessions**: session lengths and the longest sessions
10. **Library & playlists**: liked songs compared with what you actually play, playlists
11. **Search**: repeated searches and what you clicked
12. **Wrapped & Sound Capsule**: Spotify's summaries checked against the raw history

Deep dive (multi-dimensional analysis):

13. **Your music scenes**: artists you play in the same sessions form a co-listening network. Louvain community detection splits it into "scenes", shown as an interactive map plus each scene's share per year, and betweenness centrality finds the "bridge" artists that connect scenes
14. **What makes you skip**: a gradient-boosting model predicts skips from context (how the track started, position in the session, the previous skip, familiarity, device and more). It's tested on the latest two years, explained with permutation importance, and broken down by start × familiarity
15. **Artist retention**: cohort heatmap (of the artists you got into each year, how many you still play N months later), Kaplan–Meier survival curves (chosen vs autoplayed discoveries), slow burners
16. **Genres & origins** *(needs enrichment)*: genre mix and diversity per year, and artists' countries of origin
17. **Suggestions** *(needs enrichment)*: artists you've never played that ListenBrainz links to your favourites, balanced across your scenes; "out of your bubble" picks in genres you rarely play; genre keywords and "This Is" searches that open Spotify search directly

## 1. Get your data

Request your data at <https://www.spotify.com/account/privacy/>. Tick both:

- **Account data**: library, playlists, searches, Wrapped (a few days)
- **Extended streaming history**: every play since the account was created (up to 30 days)

Unzip both into `Data/`, so you get:

```
Data/
├── Spotify Account Data/
└── Spotify Extended Streaming History/
```

Only the extended streaming history is required. Each account-data section is skipped if its file is missing.

## 2. Build the report

Requires Python 3.9+.

```bash
cd Analysis
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python build_report.py            # reads ../Data, writes output/report.html
open output/report.html
```

Options: `--data PATH` (export folder), `--out PATH` (HTML file to write) and `--cache PATH` (enrichment cache).

### Optional: genres and suggestions

```bash
.venv/bin/python enrich.py      # one-off, ~20–30 min; re-runs only fetch what's missing
.venv/bin/python build_report.py
```

`enrich.py` looks up the artists you've streamed at least 20 times on [MusicBrainz](https://musicbrainz.org) (artist id, genres, country), using one of their tracks to pick the right artist. It then asks [ListenBrainz](https://listenbrainz.org) for similar artists. Only artist and track names are sent. The answers are cached in `Analysis/cache/musicbrainz.json`, which is git-ignored, so the report build itself stays offline. Without the cache, the genre and suggestion sections are skipped.

The report is a single file and works offline: plotly.js is embedded, so it doesn't need a CDN. It follows your system's light or dark theme, and the button in the top-right corner switches theme manually.

## Project layout

```
Analysis/
├── build_report.py            # CLI entry point: builds the report
├── enrich.py                  # optional: fetch genres and similar artists (cached)
├── requirements.txt
└── spotify_analysis/
    ├── load.py                # read the export, keep music only, local time, drop personal fields
    ├── metrics.py             # one function per report section → tables and insight sentences
    ├── deep.py                # scenes, skip model, retention, genres, suggestions
    ├── enrich.py              # MusicBrainz / ListenBrainz client with on-disk cache
    ├── charts.py              # Plotly figures and the colour palette
    └── report.py              # HTML page, CSS and JS (theme, data tables, top-chart widget)
```

## Definitions

- **Stream**: a play of at least 30 seconds, which is Spotify's own rule. **Hours** count every play.
- **Skip**: Spotify marked the play as skipped, or it ended with the forward button.
- **Local time**: the UTC timestamp converted to the time zone of the country it was played from (`COUNTRY_TZ` in `load.py`).
- **Session**: plays separated by less than 30 minutes of silence.
- The first year with almost no data (e.g. a handful of plays at signup) is left out of the per-year charts.

## Privacy

`Data/` and `Analysis/cache/` are in `.gitignore`, so your raw export and the lookup cache are never committed.
The generated report (`Analysis/output/report.html`) **is** committed in this repo. Keep the repo private, or add
`Analysis/output/` back to `.gitignore` if you fork it to publish your own code.
The loader drops IP addresses, the podcast and audiobook fields, and never reads identity, payment or follower files.
The report still shows track and artist names and the countries you played from, so treat it as personal.
