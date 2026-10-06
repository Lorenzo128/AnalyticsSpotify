# Spotify music listening report

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

Options: `--data PATH` (export folder) and `--out PATH` (HTML file to write).

The report is a single file and works offline: plotly.js is embedded, so it doesn't need a CDN. It follows your system's light or dark theme, and the button in the top-right corner switches theme manually.

## Project layout

```
Analysis/
├── build_report.py            # CLI entry point
├── requirements.txt
└── spotify_analysis/
    ├── load.py                # read the export, keep music only, local time, drop personal fields
    ├── metrics.py             # one function per report section → tables and insight sentences
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

`Data/` and `Analysis/output/` are in `.gitignore`, so neither your raw export nor your generated report gets committed.
The loader drops IP addresses, the podcast and audiobook fields, and never reads identity, payment or follower files.
The report still shows track and artist names and the countries you played from, so treat it as personal.
