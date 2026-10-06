"""Assemble metrics and charts into one self-contained interactive HTML page."""
import html
import json
import numbers
import re

import pandas as pd
import plotly.io as pio
from plotly.offline import get_plotlyjs

from . import charts as C
from . import metrics as M


def esc(s):
    return html.escape(str(s), quote=True)


def rich(text):
    """Escape a metrics insight, then turn **bold** markers into <b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text))


class Page:
    """Collects figures and renders HTML fragments."""

    def __init__(self):
        self.figs = {}

    def chart(self, fig, title, sub=None, wide=False):
        fid = f"fig{len(self.figs)}"
        self.figs[fid] = json.loads(pio.to_json(fig, validate=False))
        sub_html = f'<p class="sub">{esc(sub)}</p>' if sub else ""
        return (f'<figure class="card{" wide" if wide else ""}"><figcaption><h3>{esc(title)}</h3>{sub_html}'
                f'</figcaption><div class="chart" id="{fid}" role="img" aria-label="{esc(title)}"></div>'
                f'<button class="datatoggle" data-for="{fid}" type="button">Show data</button>'
                f'<div class="datatable" id="{fid}-table" hidden></div></figure>')


def insights(items):
    if not items:
        return ""
    return '<ul class="insights">' + "".join(f"<li>{rich(i)}</li>" for i in items) + "</ul>"


def tiles(kpis):
    out = []
    for k in kpis:
        note = f'<div class="note">{esc(k["note"])}</div>' if k.get("note") else ""
        out.append(f'<div class="tile{" hero" if k.get("hero") else ""}"><div class="label">{esc(k["label"])}</div>'
                   f'<div class="value">{esc(k["value"])}</div>{note}</div>')
    return '<div class="tiles">' + "".join(out) + "</div>"


def cell(v):
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, numbers.Integral) or (isinstance(v, float) and v.is_integer()):
        return f"{int(v):,}"
    return str(v)


def table(title, headers, rows, sub=None, wide=False, num_cols=()):
    """rows: list of lists of values; numbers are formatted, everything is escaped here."""
    th = "".join(f'<th{" class=num" if i in num_cols else ""}>{esc(h)}</th>' for i, h in enumerate(headers))
    body = "".join("<tr>" + "".join(f'<td{" class=num" if i in num_cols else ""}>{esc(cell(c))}</td>'
                                    for i, c in enumerate(r)) + "</tr>" for r in rows)
    sub_html = f'<p class="sub">{esc(sub)}</p>' if sub else ""
    return (f'<div class="card{" wide" if wide else ""}"><h3>{esc(title)}</h3>{sub_html}'
            f'<div class="tablewrap"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></div></div>')


def section(sid, title, lede, *parts):
    return (f'<section id="{sid}"><header class="sechead"><h2>{esc(title)}</h2><p class="lede">{esc(lede)}</p></header>'
            + "".join(p for p in parts if p) + "</section>")


def grid(*parts):
    return '<div class="grid">' + "".join(p for p in parts if p) + "</div>"


def pct(x):
    return f"{x:.0%}"


def h1(x):
    return f"{x:,.1f}"


# Sections ----------------------------------------------------------------------

def build_sections(df, acct, page):
    secs = []
    years = M.main_years(df)

    o = M.overview(df)
    secs.append(("overview", "Overview", section(
        "overview", "Overview", "Your whole music history in a few numbers.",
        tiles(o["kpis"]), insights(o["insights"]))))

    t = M.timeline(df)
    secs.append(("time", "Over time", section(
        "time", "Listening over time", "How much music you played each month and year.",
        insights(t["insights"]),
        grid(page.chart(C.monthly_hours(t["monthly"]), "Hours per month", wide=True),
             page.chart(C.yearly_hours(t["yearly"]), "Hours per year",
                        "Partial years are labelled. Hover a bar for streams and minutes per listening day."),
             page.chart(C.cumulative(t["cumulative"], t["milestones"]), "Running total",
                        "Hours of music played since the history began, with each 1,000 h milestone marked.")))))

    tc = M.top_charts(df)
    secs.append(("top", "Top charts", section(
        "top", "Top charts", "Your most played artists, tracks and albums, all time or for one year.",
        insights(tc["insights"]),
        '<div class="card wide" id="topcharts"><div class="controls">'
        '<div class="seg" data-group="kind" role="group" aria-label="Category">'
        '<button data-v="artists" aria-pressed="true">Artists</button><button data-v="tracks">Tracks</button>'
        '<button data-v="albums">Albums</button></div>'
        '<div class="seg" data-group="metric" role="group" aria-label="Measure">'
        '<button data-v="hours" aria-pressed="true">Hours</button><button data-v="streams">Streams</button></div>'
        '<div class="seg" data-group="period" role="group" aria-label="Period">'
        + "".join(f'<button data-v="{esc(k)}"{" aria-pressed=true" if k == "all" else ""}>{esc(v)}</button>'
                  for k, v in tc["labels"].items())
        + '</div></div><ol class="toplist" id="toplist"></ol></div>')))

    te = M.taste_evolution(df)
    top5_rows = [[f"#{r + 1}"] + [esc_name(te["top5"][y], r) for y in te["years"]] for r in range(5)]
    secs.append(("taste", "Taste", section(
        "taste", "Taste evolution", "How your favourite artists rose and fell from year to year.",
        insights(te["insights"]),
        grid(page.chart(C.bump(te["years"], te["bump"], 40), "Rank of your 8 biggest artists, year by year",
                        "Ranked by hours that year. A missing point means the artist fell outside your top 40.",
                        wide=True),
             table("Top 5 artists of each year", ["Rank"] + [M.year_label(df, y) for y in te["years"]],
                   top5_rows, wide=True),
             page.chart(C.bars([str(y) for y in te["concentration"].index], te["concentration"].values,
                               hover="%{y:.0%}", tickformat=".0%", height=260),
                        "Share of listening from your top 10 artists", "Higher means more focused on a few favourites."),
             page.chart(C.bars([str(y) for y in te["unique_artists"].index], te["unique_artists"].values,
                               hover="%{y:,} artists", height=260),
                        "Different artists played per year"),
             table("Longest same-artist streaks", ["Artist", "Days in a row", "From", "To"],
                   [[r.artist, r.days, M.fmt_date(r.start), M.fmt_date(r.end)] for r in te["artist_streaks"].itertuples()],
                   sub="Consecutive days with at least one stream of the artist.", num_cols=(1,), wide=True)))))

    r = M.rhythm(df)
    secs.append(("rhythm", "Rhythm", section(
        "rhythm", "Daily rhythm", "When you listen, in local time wherever you were.",
        insights(r["insights"]),
        grid(page.chart(C.heatmap(r["heat"], M.WEEKDAYS), "Average minutes per week, by day and hour", wide=True),
             page.chart(C.bars(M.MONTHS, r["by_month"].values.round(1), hover="%{y:,.1f} h", height=260),
                        "Average hours per calendar month", "Complete years only."),
             page.chart(C.bars(M.WEEKDAYS, r["by_weekday"].values.round(0), hover="%{y:.0f} min", height=260),
                        "Average minutes per day of the week", "Days without music count as zero.")))))

    d = M.discovery(df)
    ns = d["new_share"].drop(d["first_year"], errors="ignore")
    secs.append(("discovery", "Discovery", section(
        "discovery", "Discovery & loyalty", "New music you found, the artists you kept, and the ones you left behind.",
        insights(d["insights"]),
        grid(page.chart(C.monthly_hours(d["new_artists_m"]).update_traces(
                            hovertemplate="%{x|%B %Y}<br>%{y} new artists<extra></extra>").update_yaxes(title="New artists"),
                        "New artists per month", f"The first 30-second stream of each artist. {d['first_year']} is high "
                        "because everything is new at the start of the history.", wide=True),
             page.chart(C.bars([str(y) for y in ns.index], ns.values, hover="%{y:.0%}", tickformat=".0%", height=260),
                        "Time spent on artists discovered that year"),
             table("One-week obsessions", ["Track", "Artist", "Week of", "Streams"],
                   [[o.track, o.artist, M.fmt_date(o.week), o.plays] for o in d["obsessions"].itertuples()],
                   sub="The most streams of a single track in one week (each track listed once).", num_cols=(3,)),
             table(f"Always there: artists in all {d['loyal_years']} years", ["Artist", "Hours"],
                   [[a, h1(v)] for a, v in d["loyal"]["hours"].items()], num_cols=(1,)),
             table("Forgotten favourites", ["Artist", f"Hours {d['first_year']}–{d['early_end_year']}",
                                            "Hours last 12 months", "Last played"],
                   [[a, h1(row.early), h1(row.recent), M.fmt_date(row.last_played)]
                    for a, row in d["forgotten"].iterrows()],
                   sub="Big in your early years, nearly silent in the last 12 months.", num_cols=(1, 2))))))

    b = M.behaviour(df)
    rates = b["rates"].rename(columns={"skip": "Skipped", "shuffle": "Shuffle on", "offline": "Offline",
                                       "incognito": "Private session"})
    secs.append(("behaviour", "Behaviour", section(
        "behaviour", "Listening behaviour", "How you play music: skips, shuffle, and how tracks start and end.",
        insights(b["insights"]),
        grid(page.chart(C.multi_lines(rates[["Skipped", "Shuffle on", "Offline"]], pct=True),
                        "Share of plays per year", wide=True),
             page.chart(C.bars(b["starts"].index.tolist(), b["starts"].values, horizontal=True, hover="%{y:.1%}",
                               tickformat=".0%", height=300), "How tracks started"),
             page.chart(C.bars(b["ends"].index.tolist(), b["ends"].values, horizontal=True, hover="%{y:.1%}",
                               tickformat=".0%", height=300), "How tracks ended"),
             table("Most skipped artists", ["Artist", "Plays", "Skipped"],
                   [[a, f"{row.plays:,}", pct(row.skip)] for a, row in b["most_skipped"].iterrows()],
                   sub=f"Artists with at least {b['min_streams']} plays.", num_cols=(1, 2)),
             table("Least skipped artists", ["Artist", "Plays", "Skipped"],
                   [[a, f"{row.plays:,}", pct(row.skip)] for a, row in b["least_skipped"].iterrows()],
                   sub=f"Artists with at least {b['min_streams']} plays.", num_cols=(1, 2)),
             table("Tracks you skip the most", ["Track", "Artist", "Plays", "Skipped"],
                   [[tr, ar, row.plays, pct(row.skip)] for (tr, ar), row in b["skipped_tracks"].iterrows()],
                   sub="Tracks with at least 25 plays.", num_cols=(2, 3), wide=True)))))

    p = M.places(df)
    ch = p["country_hours"].head(12)
    trips = p["trips"]
    secs.append(("places", "Places", section(
        "places", "Where & how", "Countries you listened from, and the devices you used.",
        insights(p["insights"]),
        grid(page.chart(C.stacked(p["by_country_m"], ytitle="Hours per month", suffix=" h"),
                        "Hours per month by country", wide=True),
             page.chart(C.stacked(p["devices"], pct=True, hover_fmt=".0%", height=300).update_xaxes(type="category"),
                        "Devices: share of listening time per year"),
             page.chart(C.bars([M.COUNTRY_NAMES.get(c, c) for c in ch.index], ch.values.round(1), horizontal=True,
                               hover="%{y:,.1f} h", height=300, text=[f"{v:,.0f} h" if v >= 1 else f"{v:.1f} h" for v in ch.values]),
                        "Hours by country (top 12)"),
             table("Music abroad", ["Country", "First", "Last", "Days", "Hours", "Offline", "Most played there"],
                   [[t.country, M.fmt_date(t.first), M.fmt_date(t.last), t.days, h1(t.hours), pct(t.offline), t.top]
                    for t in trips.itertuples()],
                   sub="Every country outside Switzerland, Italy and France, most recent first.",
                   num_cols=(3, 4, 5), wide=True)))))

    s = M.sessions(df)
    dist = pd.DataFrame({"Share of sessions": s["dist"] / s["dist"].sum(), "Share of listening time": s["time_share"]})
    secs.append(("sessions", "Sessions", section(
        "sessions", "Sessions", f"A session is continuous listening; a new one starts after {M.SESSION_GAP_MIN} minutes of silence.",
        insights(s["insights"]),
        grid(page.chart(C.grouped(dist), "Session length"),
             page.chart(C.bars([str(y) for y in s["per_year"].index], s["per_year"].values.round(0),
                               hover="%{y:.0f} min", height=300), "Median session length per year (minutes)"),
             table("Longest sessions", ["Started", "Length", "Streams", "Mostly"],
                   [[r_.start.strftime("%-d %b %Y, %H:%M"), M.fmt_hours(r_.minutes / 60), int(r_.tracks), r_.top_artist]
                    for r_ in s["longest"].itertuples()], num_cols=(1, 2), wide=True)))))

    lib = M.library(df, acct)
    lib_parts = [insights(lib["insights"])]
    if lib.get("has_liked"):
        lib_parts.append(tiles([
            {"label": "Liked songs", "value": f"{lib['liked_count']:,}"},
            {"label": "Never streamed", "value": f"{lib['never']:,}"},
            {"label": "Streams that are liked songs", "value": pct(lib["liked_share"])},
        ]))
        la = lib["liked_artists"]
        parts = [page.chart(C.bars(la.index.tolist(), la.values, horizontal=True, hover="%{y} liked songs", height=340),
                            "Artists with the most liked songs")]
        if "added_q" in lib and len(lib["added_q"]):
            aq = lib["added_q"]
            parts.append(page.chart(C.bars([f"{d_.year} Q{d_.quarter}" for d_ in aq.index], aq.values,
                                           hover="%{y} tracks", height=340), "Tracks added to your playlists, per quarter"))
        parts += [
            table("Most played songs you haven't liked", ["Track", "Artist", "Streams"],
                  [[row.track, row.artist, row.plays] for row in lib["not_liked"].itertuples()], num_cols=(2,)),
            table("Most played liked songs", ["Track", "Artist", "Streams"],
                  [[row.track, row.artist, row.plays] for row in lib["liked_top"].itertuples()], num_cols=(2,)),
        ]
        if "playlists" in lib:
            parts.append(table("Your playlists", ["Playlist", "Tracks", "Last modified", "Top artist", "Streamed"],
                               [[row.name, row.tracks, row.last_modified, row.top_artist, pct(row.played)]
                                for row in lib["playlists"].itertuples()],
                               sub="'Streamed' is the share of the playlist's tracks you've streamed at least once.",
                               num_cols=(1, 4), wide=True))
        lib_parts.append(grid(*parts))
    secs.append(("library", "Library", section(
        "library", "Library & playlists", "Your liked songs and playlists, compared with what you actually play.", *lib_parts)))

    sq = M.search(df, acct)
    if not sq["empty"]:
        secs.append(("search", "Search", section(
            "search", "Search", "What you looked for, and what you clicked.",
            insights(sq["insights"]),
            grid(page.chart(C.bars(sq["per_week"].index, sq["per_week"].values, hover="%{y} searches", height=260)
                            .update_traces(hovertemplate="Week of %{x|%-d %b}<br>%{y} searches<extra></extra>"),
                            "Searches per week"),
                 table("Most repeated searches", ["You typed", "Times", "Clicked result"],
                       [[row.example, row.times, row.result or "–"] for row in sq["top"].itertuples()],
                       num_cols=(1,))))))

    w = M.wrapped(df, acct)
    w_parts = [insights(w["insights"])]
    cards = []
    if w.get("has_wrapped"):
        cards += [
            table("Wrapped 2025 vs. your raw history", ["", "Spotify Wrapped", "Your history"],
                  [list(row) for row in w["compare"]],
                  sub="Wrapped counts until about mid-November and includes podcasts. The history numbers are music only.",
                  wide=True),
            table("Wrapped 2025 top tracks", ["Track", "Artist", "Wrapped plays", "History streams"],
                  [[t_["track"], t_["artist"], t_["wrapped"], t_["history"]] for t_ in w["top_tracks"]],
                  num_cols=(2, 3)),
            '<div class="card"><h3>Wrapped 2025 extras</h3>' + tiles(
                [{"label": k, "value": v} for k, v in w["fun"]]) + "</div>",
        ]
    if "capsule" in w:
        cards.append(table("Sound Capsule: recent weeks", ["Week of", "Capsule hours", "History hours",
                                                          "Capsule top artist", "History top artist"],
                           [[M.fmt_date(c_.week), h1(c_.capsule_h), h1(c_.history_h), c_.capsule_top, c_.history_top]
                            for c_ in w["capsule"].itertuples()],
                           sub="Capsule hours may include podcasts; history hours are music only and stop at the export date.",
                           num_cols=(1, 2), wide=True))
        hl = [highlight_text(h_) for h_ in w.get("highlights", [])]
        hl = [h_ for h_ in hl if h_]
        if hl:
            cards.append('<div class="card wide"><h3>Sound Capsule highlights</h3><ul class="highlights">'
                         + "".join(f"<li>{h_}</li>" for h_ in hl) + "</ul></div>")
    if "marquee" in w:
        mq = w["marquee"]
        order = ["Super Listeners", "Moderate listeners", "Light listeners", "Previously Active Listeners"]
        rows = [[seg, len(mq[seg]), ", ".join(mq[seg][:12]) + ("…" if len(mq[seg]) > 12 else "")]
                for seg in order if seg in mq]
        cards.append(table("How artists see you (Marquee segments)", ["Segment", "Artists", "Examples"], rows,
                           sub="Spotify's listener tier for you, per artist, as used for artist promotions.",
                           num_cols=(1,), wide=True))
    w_parts.append(grid(*cards))
    secs.append(("wrapped", "Wrapped", section(
        "wrapped", "Wrapped & Sound Capsule", "Spotify's own summaries, checked against your raw history.", *w_parts)))

    return secs, tc


def esc_name(series, i):
    if i >= len(series):
        return ""
    return f"{series.index[i]} ({series.iloc[i] / 60:,.0f} h)"


def highlight_text(h):
    kind = h.get("highlightType")
    date = esc(M.fmt_date(h.get("date")))
    if kind == "PROPORTION_LISTENING_ENTITY":
        x = h.get("proportionListeningHighlight", {})
        return f"<b>{esc(x.get('entity', '').strip())}</b> made up {x.get('listeningPercentage', 0):.0f}% of your listening in the week of {date}."
    if kind == "UNLIKE_COMBINATION":
        x = h.get("unlikeCombinationHighlight", {})
        return f"An unusual mix in the week of {date}: <b>{esc(x.get('firstEntity'))}</b> and <b>{esc(x.get('secondEntity'))}</b>."
    if kind == "FIRST_TO_DISCOVER":
        x = h.get("firstToDiscoverHighlight", {})
        return (f"You were listener #{x.get('position', 0):,} in {esc(x.get('country', ''))} to discover "
                f"<b>{esc(x.get('entity'))}</b> (week of {date}).")
    if kind == "MILESTONE":
        x = h.get("multiEntityMilestoneHighlight", {})
        if not x.get("entities") or not x.get("milestoneListeningSeconds"):
            return ""
        ents = ", ".join(esc(e) for e in x.get("entities", [])[:3])
        return f"Week of {date}: {x.get('milestoneListeningSeconds', 0) / 3600:.1f} h of music, led by {ents}."
    return ""


# Page --------------------------------------------------------------------------

CSS = """
:root{
  --plane:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,0.10); --accent:#2a78d6; --accent-wash:rgba(42,120,214,0.10);
  --bar:#2a78d6; color-scheme:light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --plane:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
    --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10); --accent:#3987e5; --accent-wash:rgba(57,135,229,0.16);
    --bar:#3987e5; color-scheme:dark;
  }
}
:root[data-theme="dark"]{
  --plane:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,0.10); --accent:#3987e5; --accent-wash:rgba(57,135,229,0.16);
  --bar:#3987e5; color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1120px;margin:0 auto;padding-inline:clamp(16px,4vw,40px);padding-block:0 64px}
.top{padding-block:48px 24px}
.top h1{font-size:clamp(28px,4.5vw,44px);line-height:1.1;margin:0 0 8px;letter-spacing:-0.02em}
.top p{margin:0;color:var(--ink2);max-width:62ch}
.themebtn{float:right;font:inherit;font-size:13px;color:var(--ink2);background:var(--surface);border:1px solid var(--border);
  border-radius:999px;padding:4px 12px;cursor:pointer}
nav.toc{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:color-mix(in srgb,var(--plane) 92%,transparent);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);border-bottom:1px solid var(--border);margin-inline:calc(-1*clamp(16px,4vw,40px));
  padding:8px clamp(16px,4vw,40px);display:flex;gap:4px;overflow-x:auto;scrollbar-width:none}
nav.toc a{color:var(--ink2);text-decoration:none;font-size:13px;padding:5px 10px;border-radius:999px;white-space:nowrap}
nav.toc a:hover{background:var(--accent-wash);color:var(--ink)}
nav.toc a.on{background:var(--ink);color:var(--plane)}
section{padding-top:48px;scroll-margin-top:56px}
.sechead h2{font-size:24px;margin:0 0 4px;letter-spacing:-0.01em}
.lede{margin:0 0 16px;color:var(--ink2)}
.insights{margin:0 0 20px;padding:0;list-style:none;display:grid;gap:8px}
.insights li{padding:10px 14px;border-left:3px solid var(--accent);background:var(--surface);border-radius:0 8px 8px 0;color:var(--ink2)}
.insights b{color:var(--ink)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:16px 16px 12px;min-width:0;margin:0}
.card.wide{grid-column:1/-1}
.card h3{font-size:15px;margin:0 0 2px}
.sub{margin:0 0 8px;color:var(--muted);font-size:13px}
figcaption{margin-bottom:6px}
.chart{width:100%;min-height:200px}
.datatoggle{font:inherit;font-size:12px;color:var(--muted);background:none;border:0;padding:4px 0;cursor:pointer}
.datatoggle:hover{color:var(--ink)}
.datatable{max-height:320px;overflow:auto;margin-top:4px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.card .tile{border:0;padding:8px 0;background:none}
.tile .label{font-size:13px;color:var(--ink2)}
.tile .value{font-size:26px;font-weight:600;letter-spacing:-0.01em;line-height:1.2}
.tile .note{font-size:12px;color:var(--muted)}
.tile.hero{grid-column:span 2}
.tile.hero .value{font-size:clamp(44px,7vw,64px);line-height:1.05}
.tablewrap{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:13px}
th{font-weight:600;color:var(--ink2);text-align:left;border-bottom:1px solid var(--axis);padding:6px 10px 6px 0;white-space:nowrap}
td{border-bottom:1px solid var(--grid);padding:6px 10px 6px 0;vertical-align:top}
.num{text-align:right;font-variant-numeric:tabular-nums}
.controls{display:flex;flex-wrap:wrap;gap:8px 16px;margin-bottom:12px}
.seg{display:flex;flex-wrap:wrap;gap:4px}
.seg button{font:inherit;font-size:13px;border:1px solid var(--border);background:transparent;color:var(--ink2);
  padding:4px 12px;border-radius:999px;cursor:pointer}
.seg button:hover{background:var(--accent-wash)}
.seg button[aria-pressed="true"]{background:var(--ink);color:var(--plane);border-color:var(--ink)}
.toplist{list-style:none;margin:0;padding:0;display:grid;gap:2px}
.toplist li{display:grid;grid-template-columns:2.2em minmax(0,1fr) minmax(60px,34%) 5.5em;gap:10px;align-items:center;
  padding:5px 4px;border-radius:6px}
.toplist li:hover{background:var(--accent-wash)}
.toplist .rk{color:var(--muted);font-variant-numeric:tabular-nums;text-align:right}
.toplist .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.toplist .nm small{color:var(--muted);margin-left:6px}
.toplist .bar{height:10px;border-radius:0 4px 4px 0;background:var(--bar);min-width:2px}
.toplist .val{text-align:right;font-variant-numeric:tabular-nums;color:var(--ink2)}
.highlights{margin:0;padding-left:18px;color:var(--ink2)}
.highlights li{margin:4px 0}
.highlights b{color:var(--ink)}
footer{margin-top:56px;color:var(--muted);font-size:13px}
@media (max-width:760px){
  .grid{grid-template-columns:minmax(0,1fr)}
  .tile.hero{grid-column:1/-1}
  .toplist li{grid-template-columns:2em minmax(0,1fr) 4.5em}
  .toplist .bar{display:none}
}
"""

JS = r"""
const FIGS = JSON.parse(document.getElementById('figs-data').textContent);
const TOP = JSON.parse(document.getElementById('top-data').textContent);
const PAL = JSON.parse(document.getElementById('pal-data').textContent);
const CHROME = {
  light:{surface:'#fcfcfb', ink:'#0b0b0b', ink2:'#52514e', muted:'#898781', grid:'#e1e0d9', axis:'#c3c2b7'},
  dark:{surface:'#1a1a19', ink:'#ffffff', ink2:'#c3c2b7', muted:'#898781', grid:'#2c2c2a', axis:'#383835'}
};
const FONT = 'system-ui,-apple-system,"Segoe UI",sans-serif';
const root = document.documentElement;

function isDark(){
  const t = root.getAttribute('data-theme');
  if (t) return t === 'dark';
  return window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
}

function themed(fig, dark, el){
  let s = JSON.stringify(fig.data);
  if (dark) for (const [k, v] of Object.entries(PAL.darkMap)) s = s.split(k).join(v);
  const data = JSON.parse(s);
  const T = dark ? CHROME.dark : CHROME.light;
  data.forEach(t => {
    if (t.colorscale) {
      t.colorscale = dark ? PAL.seqDark : PAL.seqLight;
      if (t.colorbar) t.colorbar = Object.assign({}, t.colorbar, {tickfont:{color:T.muted}, title:Object.assign({}, t.colorbar.title, {font:{color:T.ink2}})});
    }
    if (t.textposition === 'outside') t.textfont = {color:T.ink2, size:11};
    if (t.mode && t.mode.includes('text')) t.textfont = {color:T.ink2, size:11};
  });
  const L = JSON.parse(JSON.stringify(fig.layout));
  delete L.template;
  Object.assign(L, {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:FONT, color:T.ink2, size:12},
    hoverlabel:{bgcolor:T.surface, bordercolor:T.axis, font:{family:FONT, color:T.ink, size:12}},
    legend:Object.assign({}, L.legend || {}, {font:{color:T.ink2, size:12}, bgcolor:'rgba(0,0,0,0)'}),
    autosize:true
  });
  for (const k of Object.keys(L)) {
    if (/^[xy]axis\d*$/.test(k)) {
      const ttl = typeof L[k].title === 'string' ? {text:L[k].title} : (L[k].title || {});
      L[k] = Object.assign({}, L[k], {gridcolor:T.grid, linecolor:T.axis, zerolinecolor:T.axis, showline:k.startsWith('x'),
        tickfont:{color:T.muted, size:11}, title:Object.assign({}, ttl, {font:{color:T.muted, size:12}})});
    }
  }
  // Cap bar thickness at ~24px by widening the gap between categories.
  const bars = data.filter(t => t.type === 'bar');
  if (bars.length && el) {
    const horiz = bars[0].orientation === 'h';
    const n = Math.max(...bars.map(t => ((horiz ? t.y : t.x) || []).length));
    const groups = L.barmode === 'group' ? bars.length : 1;
    const size = (horiz ? (L.height || 300) - 60 : el.clientWidth - 90);
    const gap = 1 - (24 * groups * n) / Math.max(1, size);
    L.bargap = Math.min(0.8, Math.max(L.bargap != null ? L.bargap : 0.2, gap));
  }
  if (!L.xaxis) L.xaxis = {gridcolor:T.grid, linecolor:T.axis, tickfont:{color:T.muted}};
  if (!L.yaxis) L.yaxis = {gridcolor:T.grid, linecolor:T.axis, tickfont:{color:T.muted}};
  return {data, layout:L};
}

const CONFIG = {displayModeBar:false, responsive:true};
function renderAll(){
  const dark = isDark();
  for (const id of Object.keys(FIGS)) {
    const el = document.getElementById(id);
    if (!el) continue;
    const f = themed(FIGS[id], dark, el);
    Plotly.react(el, f.data, f.layout, CONFIG);
  }
}

// "Show data": a plain table built from the figure's traces.
function fmt(v, isPct){
  if (typeof v === 'number') return isPct ? (v*100).toFixed(1)+'%' : v.toLocaleString(undefined,{maximumFractionDigits:1});
  if (typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(v)) return v.slice(0,10);
  return v == null ? '–' : String(v);
}
function esc(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function dataTable(fig){
  const tr = fig.data;
  if (tr[0] && tr[0].type === 'heatmap') {
    const t = tr[0];
    let h = '<table><thead><tr><th></th>' + t.x.map(x=>`<th class="num">${esc(x)}</th>`).join('') + '</tr></thead><tbody>';
    t.y.forEach((y,i)=>{ h += `<tr><td>${esc(y)}</td>` + t.z[i].map(v=>`<td class="num">${fmt(v)}</td>`).join('') + '</tr>'; });
    return h + '</tbody></table>';
  }
  const series = tr.filter(t => (t.x || t.y) && !(t.mode === 'markers+text'));
  const horiz = series[0] && series[0].orientation === 'h';
  const valAxis = (horiz ? fig.layout.xaxis : fig.layout.yaxis) || {};
  const isPct = String(valAxis.tickformat || '').includes('%');
  const keys = horiz ? series[0].y : series[0].x;
  let h = '<table><thead><tr><th></th>' + series.map(t=>`<th class="num">${esc(t.name || 'Value')}</th>`).join('') + '</tr></thead><tbody>';
  (keys || []).forEach((k,i)=>{
    h += `<tr><td>${esc(fmt(k))}</td>` + series.map(t=>`<td class="num">${fmt((horiz ? t.x : t.y)[i], isPct)}</td>`).join('') + '</tr>';
  });
  return h + '</tbody></table>';
}
document.querySelectorAll('.datatoggle').forEach(btn => btn.addEventListener('click', () => {
  const box = document.getElementById(btn.dataset.for + '-table');
  if (box.hidden && !box.innerHTML) box.innerHTML = dataTable(FIGS[btn.dataset.for]);
  box.hidden = !box.hidden;
  btn.textContent = box.hidden ? 'Show data' : 'Hide data';
}));

// Top charts widget
const state = {kind:'artists', metric:'hours', period:'all'};
function renderTop(){
  const rows = (TOP[state.period] || {})[state.kind] || [];
  const sorted = rows.slice().sort((a,b)=>b[state.metric]-a[state.metric]).slice(0,25);
  const max = sorted.length ? sorted[0][state.metric] : 1;
  document.getElementById('toplist').innerHTML = sorted.map((r,i)=>{
    const v = state.metric === 'hours' ? r.hours.toLocaleString(undefined,{maximumFractionDigits:1})+' h' : r.streams.toLocaleString();
    const tip = `${r.name}${r.sub ? ' — '+r.sub : ''}: ${r.hours.toLocaleString(undefined,{maximumFractionDigits:1})} h · ${r.streams.toLocaleString()} streams`;
    return `<li title="${esc(tip)}"><span class="rk">${i+1}</span><span class="nm">${esc(r.name)}${r.sub ? `<small>${esc(r.sub)}</small>` : ''}</span>`+
           `<span class="bar" style="width:${(100*r[state.metric]/max).toFixed(1)}%"></span><span class="val">${v}</span></li>`;
  }).join('');
}
document.querySelectorAll('#topcharts .seg').forEach(seg => seg.addEventListener('click', e => {
  const b = e.target.closest('button'); if (!b) return;
  seg.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b ? 'true' : 'false'));
  state[seg.dataset.group] = b.dataset.v; renderTop();
}));

// Theme toggle: auto -> light -> dark
const themeBtn = document.getElementById('themebtn');
function labelTheme(){ const t = root.getAttribute('data-theme'); themeBtn.textContent = 'Theme: ' + (t ? t[0].toUpperCase()+t.slice(1) : 'Auto'); }
themeBtn.addEventListener('click', () => {
  const t = root.getAttribute('data-theme');
  const next = !t ? 'light' : t === 'light' ? 'dark' : null;
  if (next) root.setAttribute('data-theme', next); else root.removeAttribute('data-theme');
  try { next ? localStorage.setItem('theme', next) : localStorage.removeItem('theme'); } catch (e) {}
});
try { const saved = localStorage.getItem('theme'); if (saved && !root.hasAttribute('data-theme')) root.setAttribute('data-theme', saved); } catch (e) {}
new MutationObserver(() => { labelTheme(); renderAll(); }).observe(root, {attributes:true, attributeFilter:['data-theme']});
if (window.matchMedia) matchMedia('(prefers-color-scheme: dark)').addEventListener('change', renderAll);
let resizeTimer;
window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(renderAll, 200); });

// Highlight the current section in the nav
const links = [...document.querySelectorAll('nav.toc a')];
const io = new IntersectionObserver(entries => entries.forEach(en => {
  if (en.isIntersecting) links.forEach(a => a.classList.toggle('on', a.getAttribute('href') === '#' + en.target.id));
}), {rootMargin:'-45% 0px -50% 0px'});
document.querySelectorAll('section').forEach(s => io.observe(s));

labelTheme(); renderAll(); renderTop();
"""


def _script_json(obj):
    return json.dumps(obj, ensure_ascii=False, default=str).replace("</", "<\\/")


def build_report(df, acct, generated=None):
    page = Page()
    secs, tc = build_sections(df, acct, page)
    start, end = df["date"].min(), df["date"].max()
    nav = "".join(f'<a href="#{sid}">{esc(label)}</a>' for sid, label, _ in secs)
    body = "".join(html_ for _, _, html_ in secs)
    pal = {"darkMap": {**C.COLOR_MAP_DARK, "#fcfcfb": "#1a1a19", "rgba(42,120,214,0.10)": "rgba(57,135,229,0.16)"},
           "seqLight": C._scale(C.SEQ_LIGHT), "seqDark": C._scale(C.SEQ_DARK)}
    generated = generated or pd.Timestamp.now().strftime("%-d %b %Y")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Music Listening Report</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <button class="themebtn" id="themebtn" type="button">Theme: Auto</button>
    <h1>Music listening report</h1>
    <p>Your music streaming history from {esc(M.fmt_date(start))} to {esc(M.fmt_date(end))}. Podcasts, audiobooks
    and video are left out. Times are local to the country each track was played in.</p>
  </div>
  <nav class="toc" aria-label="Sections">{nav}</nav>
  {body}
  <footer>Generated on {esc(generated)} from a Spotify data export. "Stream" means a play of at least 30 seconds,
  which is Spotify's own rule. Hours count every play.</footer>
</div>
<script type="application/json" id="figs-data">{_script_json(page.figs)}</script>
<script type="application/json" id="top-data">{_script_json(tc["data"])}</script>
<script type="application/json" id="pal-data">{_script_json(pal)}</script>
<script>{get_plotlyjs()}</script>
<script>{JS}</script>
</body>
</html>
"""
