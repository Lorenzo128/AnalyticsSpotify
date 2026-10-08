"""Turn the loaded frames into the numbers each report section needs.

Every public function takes the music frame from `load.load_streams` (and the
account dict where relevant) and returns plain Python data: lists, dicts and
small DataFrames, plus an `insights` list of short sentences.
"""
import pandas as pd

from .load import COUNTRY_NAMES

HOME_COUNTRIES = ["CH", "IT", "FR"]
SESSION_GAP_MIN = 30
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

REASON_START_LABELS = {
    "trackdone": "Previous track ended", "clickrow": "Picked a track", "fwdbtn": "Skipped forward to it",
    "playbtn": "Pressed play", "backbtn": "Went back to it", "appload": "App opened",
    "remote": "Remote / Connect", "trackerror": "Error recovery",
}
REASON_END_LABELS = {
    "trackdone": "Played to the end", "fwdbtn": "Skipped forward", "endplay": "Stopped playback",
    "unexpected-exit-while-paused": "App closed while paused", "backbtn": "Went back",
    "logout": "Logged out / switched device", "remote": "Remote / Connect",
    "unexpected-exit": "App crashed / killed", "trackerror": "Playback error",
}


def hours(minutes):
    return minutes / 60


def fmt_int(n):
    return f"{int(round(n)):,}"


def fmt_hours(h):
    return f"{h:,.0f} h" if h >= 10 else f"{h:,.1f} h"


def fmt_date(d):
    return pd.Timestamp(d).strftime("%-d %b %Y")


def main_years(df):
    """Years with a meaningful amount of data (drops e.g. a handful of plays at signup)."""
    counts = df["year"].value_counts()
    return sorted(int(y) for y in counts[counts >= 0.01 * len(df)].index)


def year_label(df, year):
    """'2026 (to Sep)' for the partial last year, '2020 (from Jan 17)' for a partial first."""
    sub = df[df["year"] == year]
    first, last = sub["ts_local"].min(), sub["ts_local"].max()
    if last.month < 12 and year == df["year"].max():
        return f"{year} (to {last:%b})"
    if first.month > 1 or first.day > 20:
        return f"{year} (from {first:%b})"
    return str(year)


def _streaks(dates):
    """Return (length, start, end) of the longest run of consecutive dates."""
    d = pd.Series(sorted(set(dates)))
    if d.empty:
        return 0, None, None
    run_id = (d.diff().dt.days != 1).cumsum()
    runs = d.groupby(run_id).agg(["min", "max", "count"])
    best = runs.loc[runs["count"].idxmax()]
    return int(best["count"]), best["min"], best["max"]


# 1. Overview ------------------------------------------------------------------

def overview(df):
    streams = df[df["is_stream"]]
    daily = df.groupby("date")["minutes"].sum()
    active_days = len(daily)
    busiest_day = daily.idxmax()
    top_artist = df.groupby("artist")["minutes"].sum().idxmax()
    top_track = streams.groupby(["track", "artist"]).size().idxmax()
    total_h = hours(df["minutes"].sum())
    span_days = (df["date"].max() - df["date"].min()).days + 1
    main_start = df[df["year"].isin(main_years(df))]["date"].min()

    kpis = [
        {"label": "Hours of music", "value": fmt_int(total_h), "hero": True,
         "note": f"{total_h / 24:,.0f} full days"},
        {"label": "Streams (30 s+)", "value": fmt_int(len(streams)), "note": f"{fmt_int(len(df))} plays in total"},
        {"label": "Different tracks", "value": fmt_int(df["track_uri"].nunique())},
        {"label": "Different artists", "value": fmt_int(df["artist"].nunique())},
        {"label": "Different albums", "value": fmt_int(df[["album", "artist"]].drop_duplicates().shape[0])},
        {"label": "Days with music", "value": fmt_int(active_days),
         "note": f"{active_days / max(1, (df['date'].max() - main_start).days + 1):.0%} of days since {main_start:%b %Y}"},
        {"label": "Average per listening day", "value": f"{daily.mean():.0f} min",
         "note": f"median {daily.median():.0f} min"},
        {"label": "Busiest day", "value": fmt_hours(hours(daily.max())), "note": fmt_date(busiest_day)},
    ]
    insights = [
        f"Your history covers {fmt_date(df['date'].min())} to {fmt_date(df['date'].max())} "
        f"({span_days / 365.25:.1f} years), and {total_h:,.0f} hours of it is music.",
        f"Your most listened artist overall is **{top_artist}**. Your most streamed track is "
        f"**{top_track[0]}** by {top_track[1]}, with {streams.groupby(['track', 'artist']).size().max():,} streams.",
    ]
    return {"kpis": kpis, "insights": insights}


# 2. Listening over time --------------------------------------------------------

def timeline(df):
    years = main_years(df)
    monthly = df.groupby("month")["minutes"].sum().div(60)
    full_range = pd.date_range(df[df["year"].isin(years)]["month"].min(), df["month"].max(), freq="MS")
    monthly = monthly.reindex(full_range, fill_value=0)
    yearly = (df[df["year"].isin(years)].groupby("year")
              .agg(minutes=("minutes", "sum"), streams=("is_stream", "sum"), days=("date", "nunique")))
    yearly["hours"] = yearly["minutes"] / 60
    yearly["per_day"] = yearly["minutes"] / yearly["days"]
    yearly["label"] = [year_label(df, y) for y in yearly.index]
    before = df[~df["year"].isin(years)]["minutes"].sum()
    cumulative = (df[df["year"].isin(years)].set_index("ts_local")["minutes"].resample("W").sum().cumsum()
                  .add(before).div(60))

    dates = pd.Series(sorted(df["date"].unique()))
    gaps = dates.diff().dt.days
    gap_i = gaps.idxmax()
    gap = {"days": int(gaps.max()), "from": dates[gap_i - 1], "to": dates[gap_i]}

    peak_month = monthly.idxmax()
    complete = yearly[~yearly["label"].str.contains(r"\(")]
    best_year = complete["hours"].idxmax() if len(complete) else yearly["hours"].idxmax()
    milestones = {}
    for target in (1000, 2000, 3000, 4000, 5000):
        hit = cumulative[cumulative >= target]
        if len(hit):
            milestones[target] = hit.index[0]

    insights = [
        f"Your biggest full year was **{best_year}**, with {yearly.loc[best_year, 'hours']:,.0f} h "
        f"({yearly.loc[best_year, 'per_day']:.0f} min on each day you listened).",
        f"Your peak month was **{peak_month:%B %Y}**, with {monthly.max():,.0f} h of music.",
    ]
    if gap["days"] > 60:
        insights.append(
            f"There is a {gap['days']}-day gap with no music between {fmt_date(gap['from'])} and "
            f"{fmt_date(gap['to'])}, so the yearly charts start in {years[0]}.")
    if milestones:
        last = max(milestones)
        insights.append(f"You passed {last:,} hours of music on {fmt_date(milestones[last])}.")
    return {"monthly": monthly, "yearly": yearly, "cumulative": cumulative,
            "milestones": milestones, "insights": insights}


# 3. Top charts -----------------------------------------------------------------

def _top_table(sub, keys, n):
    g = sub.groupby(keys).agg(minutes=("minutes", "sum"), streams=("is_stream", "sum"))
    top = pd.concat([g.nlargest(n, "minutes"), g.nlargest(n, "streams")])
    top = top[~top.index.duplicated()].reset_index()
    rows = []
    for r in top.itertuples(index=False):
        d = r._asdict()
        name = d[keys[0]]
        sub_label = d[keys[1]] if len(keys) > 1 else ""
        rows.append({"name": name, "sub": sub_label, "hours": round(d["minutes"] / 60, 1),
                     "streams": int(d["streams"])})
    return rows


def top_charts(df, n=25):
    periods = {"all": df}
    for y in main_years(df):
        periods[str(y)] = df[df["year"] == y]
    data = {}
    for key, sub in periods.items():
        data[key] = {
            "artists": _top_table(sub, ["artist"], n),
            "tracks": _top_table(sub, ["track", "artist"], n),
            "albums": _top_table(sub, ["album", "artist"], n),
        }
    labels = {"all": "All time", **{str(y): year_label(df, y) for y in main_years(df)}}
    by_year = df[df["year"].isin(main_years(df))].groupby(["year", "artist"])["minutes"].sum()
    tops = by_year.groupby(level=0).idxmax()
    changes = [f"{y}: **{a}**" for (y, a) in tops.tolist()]
    insights = ["Your #1 artist each year: " + " · ".join(changes) + "."]
    return {"data": data, "labels": labels, "insights": insights}


# 4. Taste evolution ------------------------------------------------------------

def taste_evolution(df, n_artists=8, max_rank=40):
    years = main_years(df)
    sub = df[df["year"].isin(years)]
    by_year = sub.groupby(["year", "artist"])["minutes"].sum()
    ranks = by_year.groupby(level=0).rank(ascending=False, method="first")
    top_all = sub.groupby("artist")["minutes"].sum().nlargest(n_artists).index.tolist()
    bump = {a: [(int(ranks.get((y, a))) if (y, a) in ranks.index and ranks[(y, a)] <= max_rank else None)
                for y in years] for a in top_all}

    top5 = {y: by_year.loc[y].nlargest(5) for y in years}
    yearly_minutes = sub.groupby("year")["minutes"].sum()
    concentration = pd.Series({y: by_year.loc[y].nlargest(10).sum() / yearly_minutes[y] for y in years})
    unique_artists = sub.groupby("year")["artist"].nunique()

    streak_rows = []
    for artist, g in sub[sub["is_stream"]].groupby("artist"):
        if len(g) < 30:
            continue
        length, start, end = _streaks(g["date"])
        streak_rows.append({"artist": artist, "days": length, "start": start, "end": end})
    artist_streaks = pd.DataFrame(streak_rows).nlargest(8, "days")

    most_varied = unique_artists.idxmax()
    most_focused = concentration.idxmax()
    insights = [
        f"In **{most_focused}** your listening was most focused: the top 10 artists took "
        f"{concentration.max():.0%} of your time. In {concentration.idxmin()} they took only {concentration.min():.0%}.",
        f"You explored the most artists in **{most_varied}** ({unique_artists.max():,} different artists).",
    ]
    if len(artist_streaks):
        s = artist_streaks.iloc[0]
        insights.append(f"Your longest run of consecutive days with the same artist is **{s['days']} days** "
                        f"of {s['artist']} ({fmt_date(s['start'])} – {fmt_date(s['end'])}).")
    return {"years": years, "bump": bump, "top5": top5, "concentration": concentration,
            "unique_artists": unique_artists, "artist_streaks": artist_streaks, "insights": insights}


# 5. Daily rhythm ---------------------------------------------------------------

def rhythm(df):
    years = main_years(df)
    sub = df[df["year"].isin(years)]
    heat = (sub.groupby(["weekday", "hour"])["minutes"].sum().div(60)
            .unstack(fill_value=0).reindex(index=range(7), columns=range(24), fill_value=0))
    n_weeks = max(1, (sub["date"].max() - sub["date"].min()).days / 7)
    heat_avg = heat * 60 / n_weeks  # average minutes per week in each slot

    by_hour = sub.groupby("hour")["minutes"].sum().reindex(range(24), fill_value=0)
    hour_share = by_hour / by_hour.sum()
    # Average hours per calendar month, using only complete years.
    complete_years = [y for y in years if "(" not in year_label(df, y)]
    cm = sub[sub["year"].isin(complete_years)]
    by_month = cm.groupby(cm["ts_local"].dt.month)["minutes"].sum().div(60 * max(1, len(complete_years)))
    by_month = by_month.reindex(range(1, 13), fill_value=0)
    days = sub.groupby("date")["minutes"].sum().reset_index()
    days["weekday"] = days["date"].dt.weekday
    all_days = pd.DataFrame({"date": pd.date_range(sub["date"].min(), sub["date"].max())})
    all_days = all_days.merge(days, on="date", how="left").fillna({"minutes": 0})
    all_days["weekday"] = all_days["date"].dt.weekday
    by_weekday = all_days.groupby("weekday")["minutes"].mean()

    night = hour_share.loc[[0, 1, 2, 3, 4]].sum()
    morning = hour_share.loc[range(6, 12)].sum()
    peak_slot = heat.stack().idxmax()
    weekend = by_weekday.loc[[5, 6]].mean()
    weekday = by_weekday.loc[range(5)].mean()
    insights = [
        f"Your busiest hour of the week is **{WEEKDAYS[peak_slot[0]]} at {peak_slot[1]:02d}:00**.",
        f"{night:.1%} of your listening happens between midnight and 5 am, and {morning:.0%} in the morning (6–12).",
        f"You average {weekday:.0f} min a day on weekdays and {weekend:.0f} min on weekends.",
        f"Your strongest month of the year is **{MONTHS[by_month.idxmax() - 1]}** and your quietest is "
        f"{MONTHS[by_month.idxmin() - 1]} (averaged over {complete_years[0]}–{complete_years[-1]}).",
    ]
    return {"heat": heat_avg, "by_hour": by_hour.div(60), "by_month": by_month,
            "by_weekday": by_weekday, "insights": insights}


# 6. Discovery & loyalty --------------------------------------------------------

def discovery(df):
    years = main_years(df)
    sub = df[df["year"].isin(years)]
    streams = sub[sub["is_stream"]]
    first_artist = streams.groupby("artist")["ts_local"].min()
    first_track = streams.groupby("track_uri")["ts_local"].min()
    new_artists_m = first_artist.dt.to_period("M").dt.to_timestamp().value_counts().sort_index()
    new_tracks_m = first_track.dt.to_period("M").dt.to_timestamp().value_counts().sort_index()
    rng = pd.date_range(sub["month"].min(), sub["month"].max(), freq="MS")
    new_artists_m = new_artists_m.reindex(rng, fill_value=0)
    new_tracks_m = new_tracks_m.reindex(rng, fill_value=0)

    # Share of each year's minutes spent on artists first heard that same year.
    first_year = first_artist.dt.year
    s2 = streams.assign(first_year=streams["artist"].map(first_year))
    new_share = (s2[s2["first_year"] == s2["year"]].groupby("year")["minutes"].sum()
                 / s2.groupby("year")["minutes"].sum()).reindex(years)

    days_len, days_start, days_end = _streaks(sub["date"])

    artist_years = streams.groupby("artist")["year"].nunique()
    artist_hours = streams.groupby("artist")["minutes"].sum().div(60)
    loyal = (pd.DataFrame({"years": artist_years, "hours": artist_hours})
             .query("years == @artist_years.max()").nlargest(12, "hours"))

    last_12 = sub["ts_local"].max() - pd.DateOffset(months=12)
    early_end = pd.Timestamp(f"{years[0] + 2}-12-31 23:59")
    early = streams[streams["ts_local"] <= early_end].groupby("artist")["minutes"].sum().div(60)
    recent = streams[streams["ts_local"] > last_12].groupby("artist")["minutes"].sum().div(60)
    forgotten = (pd.DataFrame({"early": early, "recent": recent}).fillna(0)
                 .query("recent < 0.25 and early >= 2").nlargest(10, "early"))
    forgotten["last_played"] = streams[streams["artist"].isin(forgotten.index)].groupby("artist")["date"].max()

    week = streams["ts_local"].dt.to_period("W").dt.start_time
    tw = streams.assign(week=week).groupby(["week", "track", "artist"]).size().rename("plays").reset_index()
    obsessions = (tw.sort_values("plays", ascending=False)
                  .drop_duplicates(subset=["track", "artist"]).head(10))

    plays_per_track = streams.groupby("track_uri").size()
    one_offs = (plays_per_track == 1).mean()
    heavy = int((plays_per_track >= 50).sum())

    insights = [
        f"You've streamed **{len(first_artist):,} artists** and **{len(first_track):,} tracks**. "
        f"{one_offs:.0%} of those tracks were played only once, and {heavy:,} tracks got 50 or more plays.",
        f"Your longest streak of consecutive days with music is **{days_len} days** "
        f"({fmt_date(days_start)} – {fmt_date(days_end)}).",
    ]
    ns = new_share.drop(years[0], errors="ignore")
    if len(ns):
        insights.append(
            f"Leaving out {years[0]} (when everything was new to the history), the share of time on newly discovered "
            f"artists ranged from {ns.min():.0%} ({ns.idxmin()}) to {ns.max():.0%} ({ns.idxmax()}).")
    if len(obsessions):
        o = obsessions.iloc[0]
        insights.append(f"Your biggest one-week obsession was **{o['track']}** by {o['artist']}: "
                        f"{o['plays']} streams in the week of {fmt_date(o['week'])}.")
    return {"new_artists_m": new_artists_m, "new_tracks_m": new_tracks_m, "new_share": new_share,
            "loyal": loyal, "loyal_years": int(artist_years.max()), "forgotten": forgotten,
            "obsessions": obsessions, "first_year": years[0], "early_end_year": years[0] + 2,
            "insights": insights}


# 7. Listening behaviour --------------------------------------------------------

def behaviour(df, min_streams=150):
    years = main_years(df)
    sub = df[df["year"].isin(years)]
    rates = sub.groupby("year").agg(skip=("skipped", "mean"), shuffle=("shuffle", "mean"),
                                    offline=("offline", "mean"), incognito=("incognito", "mean"))
    starts = sub["reason_start"].map(REASON_START_LABELS).fillna("Other").value_counts(normalize=True)
    ends = sub["reason_end"].map(REASON_END_LABELS).fillna("Other").value_counts(normalize=True)

    per_artist = sub.groupby("artist").agg(plays=("skipped", "size"), skip=("skipped", "mean"))
    eligible = per_artist[per_artist["plays"] >= min_streams]
    most_skipped = eligible.nlargest(10, "skip")
    least_skipped = eligible.nsmallest(10, "skip")
    per_track = sub.groupby(["track", "artist"]).agg(plays=("skipped", "size"), skip=("skipped", "mean"))
    skipped_tracks = per_track[per_track["plays"] >= 25].nlargest(10, "skip")

    quick = (sub["ms_played"] < 10_000).mean()
    shuffled = sub[sub["shuffle"]]["skipped"].mean()
    ordered = sub[~sub["shuffle"]]["skipped"].mean()
    insights = [
        f"You skip **{sub['skipped'].mean():.0%}** of the tracks you start, and "
        f"{quick:.0%} of plays last less than 10 seconds.",
        f"On shuffle you skip {shuffled:.0%} of tracks, compared with {ordered:.0%} when you play in order.",
        f"Your skip rate went from {rates['skip'].iloc[0]:.0%} in {years[0]} to "
        f"{rates['skip'].iloc[-1]:.0%} in {years[-1]}, and your shuffle use from "
        f"{rates['shuffle'].iloc[0]:.0%} to {rates['shuffle'].iloc[-1]:.0%}.",
        f"{sub['offline'].mean():.1%} of plays were offline (downloaded music) and "
        f"{sub['incognito'].mean():.1%} were in a private session.",
    ]
    return {"rates": rates, "starts": starts, "ends": ends, "most_skipped": most_skipped,
            "least_skipped": least_skipped, "skipped_tracks": skipped_tracks,
            "min_streams": min_streams, "insights": insights}


# 8. Where & how ----------------------------------------------------------------

def places(df):
    years = main_years(df)
    sub = df[df["year"].isin(years)]
    keep = ["iPhone", "Mac", "Chromecast / TV", "Speakers / hi-fi"]
    dev = sub["device"].where(sub["device"].isin(keep), "Other")
    devices = (sub.assign(device=dev).groupby(["year", "device"])["minutes"].sum()
               .unstack(fill_value=0))
    devices = devices[[c for c in keep + ["Other"] if c in devices.columns]]
    devices = devices.div(devices.sum(axis=1), axis=0)

    region = sub["country"].where(sub["country"].isin(HOME_COUNTRIES), "Abroad")
    by_country_m = (sub.assign(region=region).groupby(["month", "region"])["minutes"].sum().div(60)
                    .unstack(fill_value=0))
    by_country_m = by_country_m[[c for c in HOME_COUNTRIES + ["Abroad"] if c in by_country_m.columns]]
    by_country_m.columns = [COUNTRY_NAMES.get(c, c) for c in by_country_m.columns]
    rng = pd.date_range(by_country_m.index.min(), by_country_m.index.max(), freq="MS")
    by_country_m = by_country_m.reindex(rng, fill_value=0)

    country_hours = sub.groupby("country")["minutes"].sum().div(60).sort_values(ascending=False)
    trips = []
    for code, g in sub[~sub["country"].isin(HOME_COUNTRIES)].groupby("country"):
        top = g[g["is_stream"]].groupby(["track", "artist"]).size()
        top_track = top.idxmax() if len(top) else None
        trips.append({
            "country": COUNTRY_NAMES.get(code, code), "first": g["date"].min(), "last": g["date"].max(),
            "days": g["date"].nunique(), "hours": g["minutes"].sum() / 60,
            "offline": g["offline"].mean(), "top": f"{top_track[0]} — {top_track[1]}" if top_track else "–",
        })
    trips = pd.DataFrame(trips).sort_values("first", ascending=False)

    # Country mix in the first and last year: where "home" was, and how it changed.
    mix = sub.groupby(["year", "country"])["minutes"].sum().unstack(fill_value=0)
    mix = mix.div(mix.sum(axis=1), axis=0)

    def describe(year):
        top = mix.loc[year].nlargest(2)
        top = top[top >= 0.1]
        return " and ".join(f"{COUNTRY_NAMES.get(c, c)} {v:.0%}" for c, v in top.items())

    moves = f"in {years[0]} it was {describe(years[0])}; in {years[-1]} it's {describe(years[-1])}"
    abroad_offline = sub[~sub["country"].isin(HOME_COUNTRIES)]["offline"].mean()
    home_offline = sub[sub["country"].isin(HOME_COUNTRIES)]["offline"].mean()
    top_device = sub.groupby("device")["minutes"].sum().idxmax()
    insights = [
        f"You've played music from **{sub['country'].nunique()} countries**. "
        f"Where you listen has changed: {moves}.",
        f"**{top_device}** is your main device, with {sub.groupby('device')['minutes'].sum().max() / sub['minutes'].sum():.0%} of listening time.",
        f"Abroad, {abroad_offline:.0%} of plays were offline, compared with {home_offline:.0%} at home.",
    ]
    return {"devices": devices, "by_country_m": by_country_m, "country_hours": country_hours,
            "trips": trips, "insights": insights}


# 9. Sessions -------------------------------------------------------------------

def assign_sessions(df):
    """Return a copy of the main-years plays, time-sorted, with a `session` id column."""
    sub = df[df["year"].isin(main_years(df))].sort_values("ts_utc").copy()
    start = sub["ts_utc"] - pd.to_timedelta(sub["ms_played"], unit="ms")
    gap_min = (start - sub["ts_utc"].shift()).dt.total_seconds().div(60)
    sub["session"] = (gap_min.isna() | (gap_min > SESSION_GAP_MIN)).cumsum()
    return sub


def sessions(df):
    sub = assign_sessions(df)
    sub["start_local"] = sub["ts_local"]
    s = sub.groupby("session").agg(start=("start_local", "min"), end=("end_local", "max"),
                                   minutes=("minutes", "sum"), tracks=("is_stream", "sum"),
                                   year=("year", "first"))
    s = s[s["minutes"] >= 1]
    s["wall"] = (s["end"] - s["start"]).dt.total_seconds() / 60
    top_artist = sub.groupby(["session", "artist"])["minutes"].sum()
    top_artist = top_artist.loc[top_artist.groupby(level=0).idxmax()].reset_index(level=1)["artist"]
    s["top_artist"] = top_artist

    bins = [0, 15, 30, 60, 120, 240, 1e9]
    labels = ["< 15 min", "15–30 min", "30–60 min", "1–2 h", "2–4 h", "4 h +"]
    s["bucket"] = pd.cut(s["minutes"], bins=bins, labels=labels, right=False)
    dist = s["bucket"].value_counts().reindex(labels)
    time_share = s.groupby("bucket", observed=False)["minutes"].sum().reindex(labels) / s["minutes"].sum()
    per_year = s.groupby("year")["minutes"].median()
    longest = s.nlargest(8, "minutes")
    insights = [
        f"You've had **{len(s):,} listening sessions** (a new session starts after {SESSION_GAP_MIN} minutes of silence). "
        f"The median session lasts {s['minutes'].median():.0f} min.",
        f"Sessions of an hour or more are only {(s['minutes'] >= 60).mean():.0%} of sessions, but they hold "
        f"{s.loc[s['minutes'] >= 60, 'minutes'].sum() / s['minutes'].sum():.0%} of your listening time.",
        f"Your longest session was **{fmt_hours(longest.iloc[0]['minutes'] / 60)}** on "
        f"{fmt_date(longest.iloc[0]['start'])}, mostly {longest.iloc[0]['top_artist']}.",
    ]
    return {"dist": dist, "time_share": time_share, "per_year": per_year, "longest": longest,
            "insights": insights}


# 10. Library & playlists -------------------------------------------------------

def library(df, acct):
    liked = acct["liked"]
    streams = df[df["is_stream"]]
    plays = streams.groupby("track_uri").size()
    out = {"has_liked": not liked.empty, "insights": []}
    if not liked.empty:
        liked = liked.assign(plays=liked["uri"].map(plays).fillna(0).astype(int))
        never = int((liked["plays"] == 0).sum())
        liked_artists = liked["artist"].value_counts().head(12)
        meta = streams.drop_duplicates("track_uri").set_index("track_uri")[["track", "artist"]]
        not_liked = plays[~plays.index.isin(liked["uri"])].nlargest(15).to_frame("plays").join(meta)
        liked_share = streams["track_uri"].isin(liked["uri"]).mean()
        out.update({"liked_count": len(liked), "never": never, "liked_artists": liked_artists,
                    "not_liked": not_liked, "liked_share": liked_share,
                    "liked_top": liked.nlargest(10, "plays")})
        out["insights"] += [
            f"You have **{len(liked):,} liked songs** across {liked['artist'].nunique():,} artists. "
            f"{never:,} of them ({never / len(liked):.0%}) never got a 30-second stream in your history.",
            f"{liked_share:.0%} of your streams are liked songs. The most played song you haven't liked is "
            f"**{not_liked.iloc[0]['track']}** by {not_liked.iloc[0]['artist']} ({not_liked.iloc[0]['plays']} streams).",
        ]
    pl, items = acct["playlists"], acct["playlist_items"]
    if not pl.empty:
        rows = []
        for p in pl.itertuples():
            it = items[items["playlist"] == p.name]
            top_artist = it["artist"].value_counts()
            rows.append({"name": p.name, "tracks": p.tracks, "last_modified": p.last_modified,
                         "top_artist": top_artist.index[0] if len(top_artist) else "–",
                         "played": it["uri"].isin(plays.index).mean() if len(it) else 0})
        out["playlists"] = pd.DataFrame(rows).sort_values("tracks", ascending=False)
        added = pd.to_datetime(items["added"], errors="coerce").dt.to_period("Q").dt.start_time
        out["added_q"] = added.value_counts().sort_index()
        biggest = out["playlists"].iloc[0]
        out["insights"].append(f"You own {len(pl)} playlists in this export. The biggest is **{biggest['name']}** "
                               f"with {biggest['tracks']} tracks, and you've streamed {biggest['played']:.0%} of them.")
    return out


# 11. Search --------------------------------------------------------------------

def search(df, acct):
    q = acct["searches"]
    if q.empty:
        return {"empty": True, "insights": []}
    names = df.drop_duplicates("track_uri").set_index("track_uri")
    q = q.assign(result=q["clicked_uri"].map(
        lambda u: f"{names.at[u, 'track']} — {names.at[u, 'artist']}" if u in names.index else None))
    q = q.assign(query_norm=q["query"].str.lower())
    top = q.groupby("query_norm").agg(times=("query", "size"), example=("query", "last"),
                                      result=("result", lambda s: s.dropna().iloc[-1] if s.notna().any() else ""))
    top = top.sort_values("times", ascending=False).head(15)
    per_week = q.set_index("time")["query"].resample("W").size()
    span = f"{q['time'].min():%-d %b} – {q['time'].max():%-d %b %Y}"
    clicked = q["clicked"].mean()
    ai = q["clicked_uri"].fillna("").str.contains("prompt:generate").sum()
    insights = [
        f"Spotify only keeps a short search log: **{len(q):,} searches** between {span}.",
        f"{clicked:.0%} of your searches ended with a click on a result."
        + (f" {ai} {'was an AI playlist prompt' if ai == 1 else 'were AI playlist prompts'}." if ai else ""),
    ]
    return {"empty": False, "top": top, "per_week": per_week, "span": span, "insights": insights}


# 12. Wrapped & Sound Capsule ---------------------------------------------------

def wrapped(df, acct):
    w = acct["wrapped"] or {}
    out = {"insights": [], "has_wrapped": bool(w)}
    if w:
        y25 = df[df["year"] == 2025]
        window = y25[y25["ts_local"] < "2025-11-16"]
        party = w.get("party", {})
        pod_min = w.get("topPodcasts", {}).get("totalPodcastMilliseconds", 0) / 60_000
        total_min = w.get("yearlyMetrics", {}).get("totalMsListened", 0) / 60_000
        streak, _, _ = _streaks(window["date"])
        new_2025 = df[df["is_stream"]].groupby("artist")["year"].min().eq(2025).sum()
        top_ms = w.get("topArtists", {}).get("topArtistMsPlayed")
        artist_min = window.groupby("artist")["minutes"].sum()
        match = (artist_min - top_ms / 60_000).abs().idxmin() if top_ms else None
        out["compare"] = [
            ("Minutes listened", f"{total_min:,.0f} (incl. {pod_min:,.0f} podcast)",
             f"{window['minutes'].sum():,.0f} music (Jan 1–Nov 15) · {y25['minutes'].sum():,.0f} full year"),
            ("Different artists", fmt_int(w.get("topArtists", {}).get("numUniqueArtists", 0)), fmt_int(window["artist"].nunique())),
            ("Different tracks", fmt_int(w.get("topTracks", {}).get("numUniqueTracks", 0)), fmt_int(window["track_uri"].nunique())),
            ("Days with listening", fmt_int(party.get("totalNumListeningDays", 0)), fmt_int(window["date"].nunique())),
            ("Longest daily streak", f"{party.get('streakNumListeningDays', 0)} days", f"{streak} days (music only)"),
            ("Artists discovered", fmt_int(party.get("numArtistsDiscovered", 0)), f"{new_2025:,} first streamed in 2025"),
            ("Top artist time", fmt_hours(top_ms / 3.6e6) if top_ms else "–",
             f"{match}: {fmt_hours(artist_min[match] / 60)}" if match else "–"),
        ]
        names = df.drop_duplicates("track_uri").set_index("track_uri")
        counts = window[window["is_stream"]].groupby("track_uri").size()
        out["top_tracks"] = [
            {"track": names.at[t["trackUri"], "track"] if t["trackUri"] in names.index else t["trackUri"],
             "artist": names.at[t["trackUri"], "artist"] if t["trackUri"] in names.index else "",
             "wrapped": t.get("count"), "history": int(counts.get(t["trackUri"], 0))}
            for t in w.get("topTracks", {}).get("topTracks", [])]
        fan = w.get("topArtists", {}).get("topNPercentileFan")
        out["fun"] = [
            ("Top fan of your #1 artist", f"top {fan * 100:.2f}%" if fan else "–"),
            ("Listening age", str(w.get("listeningAge", {}).get("listeningAge", "–"))),
            ("Wrapped club", f"{w.get('clubs', {}).get('userClub', '–').replace('_', ' ').title()} · "
                             f"{w.get('clubs', {}).get('role', '').title()}"),
            ("Explicit tracks", f"{party.get('percentListenedExplicit', 0):.0f}%"),
            ("Genres", fmt_int(w.get("topGenres", {}).get("totalNumGenres", 0))),
            ("Albums listened to in full", fmt_int(w.get("topAlbums", {}).get("numCompletedAlbums", 0))),
        ]
        out["insights"].append(
            f"Wrapped 2025 counts {total_min:,.0f} minutes including podcasts. Your raw history has "
            f"{window['minutes'].sum():,.0f} music minutes for the same Jan 1–Nov 15 window, so the two sources agree.")
        if match:
            out["insights"].append(f"Wrapped only lists artist IDs. Matching its top-artist listening time against your history "
                                   f"points to **{match}** as your 2025 #1.")

    cap = acct["sound_capsule"] or {}
    if cap.get("stats"):
        rows = []
        for st in cap["stats"]:
            start = pd.Timestamp(st["date"])
            wk = df[(df["date"] >= start) & (df["date"] < start + pd.Timedelta(days=7))]
            top_hist = wk.groupby("artist")["minutes"].sum().idxmax() if len(wk) else "–"
            rows.append({"week": start, "capsule_h": st.get("secondsPlayed", 0) / 3600,
                         "history_h": wk["minutes"].sum() / 60,
                         "capsule_top": (st.get("topArtists") or [{"name": "–"}])[0]["name"],
                         "history_top": top_hist})
        out["capsule"] = pd.DataFrame(rows).sort_values("week")
        out["highlights"] = cap.get("highlights", [])
    m = acct["marquee"]
    if not m.empty:
        out["marquee"] = m.groupby("segment")["artistName"].apply(list).to_dict()
    return out
