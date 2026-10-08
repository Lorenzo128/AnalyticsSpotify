"""Multi-dimensional analyses: artist communities, skip model, retention, genres, suggestions.

Like `metrics.py`, each public function returns plain data plus an `insights`
list. Functions that need the MusicBrainz/ListenBrainz cache accept `cache=None`
and degrade gracefully when enrichment hasn't been run.
"""
import math
from urllib.parse import quote

import numpy as np
import pandas as pd

from .enrich import norm
from .metrics import assign_sessions, main_years

MAX_GROUPS = 7  # categorical slots used for named groups; the rest folds into "Other"


def artist_hours(df):
    return df.groupby("artist")["minutes"].sum().div(60).sort_values(ascending=False)


def top_track_per_artist(df):
    s = df[df["is_stream"]].groupby(["artist", "track"]).size().reset_index(name="n")
    return s.sort_values("n", ascending=False).drop_duplicates("artist").set_index("artist")["track"]


def artist_mbids(cache):
    return {a: v["mbid"] for a, v in (cache or {}).get("artists", {}).items() if v.get("mbid")}


def spotify_search_url(query):
    return "https://open.spotify.com/search/" + quote(query, safe="")


def artist_genres(cache, top=3):
    """artist name -> {genre: weight} (weights sum to 1), from the top MusicBrainz genres."""
    out = {}
    if not cache:
        return out
    for artist, v in cache.get("artists", {}).items():
        info = cache.get("mbids", {}).get(v.get("mbid") or "", {})
        g = sorted(info.get("genres", {}).items(), key=lambda kv: -kv[1])[:top]
        total = sum(c for _, c in g)
        if total:
            out[artist] = {name: c / total for name, c in g}
    return out


def mbid_genres(cache, mbid, top=3):
    g = (cache or {}).get("mbids", {}).get(mbid, {}).get("genres", {})
    return [name for name, _ in sorted(g.items(), key=lambda kv: -kv[1])[:top]]


# 1. Artist communities ---------------------------------------------------------

def artist_communities(df, cache=None, n_artists=250, k_neighbors=6):
    """Cluster artists by how often they share a listening session."""
    import networkx as nx
    from scipy.sparse import csr_matrix

    sub = assign_sessions(df)
    sub = sub[sub["is_stream"]]
    hours = artist_hours(sub)
    counts = sub.groupby("artist").size()
    top = [a for a in hours.index if counts[a] >= 15][:n_artists]
    pairs = sub[sub["artist"].isin(top)][["session", "artist"]].drop_duplicates()
    a_idx = {a: i for i, a in enumerate(top)}
    s_codes, _ = pd.factorize(pairs["session"])
    m = csr_matrix((np.ones(len(pairs)), (s_codes, pairs["artist"].map(a_idx).values)))
    co = (m.T @ m).toarray()
    n = np.diag(co).astype(float)
    sim = co / np.sqrt(np.outer(n, n))
    np.fill_diagonal(sim, 0)

    g = nx.Graph()
    g.add_nodes_from(range(len(top)))
    for i in range(len(top)):
        for j in np.argsort(-sim[i])[:k_neighbors]:
            if co[i, j] >= 3 and sim[i, j] > 0:
                g.add_edge(i, int(j), weight=float(sim[i, j]))
    comms = nx.community.louvain_communities(g, weight="weight", resolution=1.0, seed=42)
    comms = sorted(comms, key=lambda c: -sum(hours[top[i]] for i in c))

    genres = artist_genres(cache)
    groups = []
    for ci, c in enumerate(comms):
        members = sorted((top[i] for i in c), key=lambda a: -hours[a])
        gw = {}
        for a in members:
            for gname, w in genres.get(a, {}).items():
                gw[gname] = gw.get(gname, 0) + w * hours[a]
        top_genres = [k for k, _ in sorted(gw.items(), key=lambda kv: -kv[1])[:2]]
        groups.append({"id": ci, "members": members, "hours": sum(hours[a] for a in members),
                       "genres": top_genres, "label": " · ".join(members[:3])})
    named = [grp for grp in groups if len(grp["members"]) >= 5][:MAX_GROUPS]
    for new_id, grp in enumerate(named):
        grp["id"] = new_id
    for grp in groups:
        if grp not in named:
            grp["id"] = MAX_GROUPS
    group_of = {}
    for grp in groups:
        for a in grp["members"]:
            group_of[a] = grp["id"] if grp["id"] < MAX_GROUPS else MAX_GROUPS

    # Lay out the main connected network only; small islands would squash it into a corner.
    main = max(nx.connected_components(g), key=len)
    core = g.subgraph(main)
    pos = nx.kamada_kawai_layout(core)
    pos = nx.spring_layout(core, pos=pos, weight="weight", seed=7, iterations=60,
                           k=2.2 / math.sqrt(max(1, len(main))))
    keep = sorted(main)
    nodes = pd.DataFrame({
        "artist": [top[i] for i in keep], "x": [pos[i][0] for i in keep], "y": [pos[i][1] for i in keep],
        "hours": [hours[top[i]] for i in keep], "group": [group_of[top[i]] for i in keep],
    })
    edges = [(pos[u][0], pos[u][1], pos[v][0], pos[v][1]) for u, v in core.edges()]
    scene_of_artist = {a: group_of[a] for a in top}

    # Bridges: artists that connect different scenes (high betweenness, neighbours in several groups).
    btw = nx.betweenness_centrality(g, weight=None, seed=42, k=min(150, len(top)))
    bridges = []
    for i, b in sorted(btw.items(), key=lambda kv: -kv[1]):
        neigh = {group_of[top[j]] for j in g.neighbors(i)} - {group_of[top[i]]}
        if neigh:
            bridges.append({"artist": top[i], "links": sorted(neigh)})
        if len(bridges) == 8:
            break

    sub_top = sub.assign(group=sub["artist"].map(group_of)).dropna(subset=["group"])
    yearly = (sub_top.groupby(["year", "group"])["minutes"].sum().unstack(fill_value=0))
    yearly = yearly.div(yearly.sum(axis=1), axis=0)

    names = {grp["id"]: scene_name(grp) for grp in named}
    names[MAX_GROUPS] = "Other scenes"
    yearly = yearly.reindex(columns=sorted(yearly.columns))
    yearly = yearly.rename(columns=names)
    first, last = yearly.index[0], yearly.index[-1]
    change = (yearly.loc[last] - yearly.loc[first]).drop("Other scenes", errors="ignore")
    covered = sum(grp["hours"] for grp in groups) / artist_hours(df).sum()
    insights = [
        f"Your top {len(top)} artists ({covered:.0%} of your listening) form **{len(named)} main scenes**: groups of "
        f"artists you play in the same sessions. The biggest is **{names[0]}**.",
        f"Biggest rise since {first}: **{change.idxmax()}** ({change.max():+.0%} of listening). "
        f"Biggest fall: **{change.idxmin()}** ({change.min():+.0%}).",
    ]
    if bridges:
        insights.append("Artists that connect your scenes: " + ", ".join(f"**{b['artist']}**" for b in bridges[:4]) + ".")
    return {"nodes": nodes, "edges": edges, "groups": named, "names": names, "yearly": yearly,
            "scene_of": scene_of_artist, "n_off_map": len(top) - len(main),
            "bridges": bridges, "insights": insights}


def scene_name(group):
    g = f" ({', '.join(group['genres'])})" if group["genres"] else ""
    return f"{', '.join(group['members'][:2])}{g}"


# 2. Skip model -----------------------------------------------------------------

FEATURE_LABELS = {
    "reason_start": "How the track started", "prev_skipped": "Previous track was skipped",
    "track_prev_plays": "Times you'd played the track", "artist_prev_plays": "Times you'd played the artist",
    "track_age_days": "Days since you first heard the track", "pos_in_session": "Position in session",
    "session_min": "Minutes into the session", "hour": "Hour of day", "weekend": "Weekend",
    "device": "Device", "shuffle": "Shuffle", "offline": "Offline", "abroad": "Abroad", "year": "Year",
}
START_SHORT = {"trackdone": "Autoplay", "clickrow": "You picked it", "fwdbtn": "Skipped to it",
               "playbtn": "Pressed play", "backbtn": "Went back to it"}


def _bucket(series, edges, labels):
    return pd.cut(series, bins=edges, labels=labels, right=False)


def skip_model(df):
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score

    d = assign_sessions(df)
    d["track_prev_plays"] = d.groupby("track_uri").cumcount()
    d["artist_prev_plays"] = d.groupby("artist").cumcount()
    d["track_age_days"] = (d["ts_utc"] - d.groupby("track_uri")["ts_utc"].transform("min")).dt.total_seconds() / 86400
    d["pos_in_session"] = d.groupby("session").cumcount()
    d["session_min"] = d.groupby("session")["minutes"].cumsum() - d["minutes"]
    d["prev_skipped"] = d.groupby("session")["skipped"].shift(fill_value=False).astype(int)
    d["weekend"] = (d["weekday"] >= 5).astype(int)
    d["abroad"] = (~d["country"].isin(["CH", "IT", "FR"])).astype(int)
    for c in ("shuffle", "offline"):
        d[c] = d[c].astype(int)
    cats = ["reason_start", "device"]
    for c in cats:
        d[c] = d[c].fillna("unknown").astype("category")
    feats = list(FEATURE_LABELS)
    X = d[feats].copy()
    for c in cats:
        X[c] = X[c].cat.codes
    y = d["skipped"].astype(int)

    years = sorted(d["year"].unique())
    test_mask = d["year"].isin(years[-2:])
    model = HistGradientBoostingClassifier(max_iter=250, learning_rate=0.08, max_leaf_nodes=31,
                                           categorical_features=[feats.index(c) for c in cats], random_state=0)
    model.fit(X[~test_mask], y[~test_mask])
    auc = roc_auc_score(y[test_mask], model.predict_proba(X[test_mask])[:, 1])
    samp = X[test_mask].sample(min(15000, int(test_mask.sum())), random_state=0)
    imp = permutation_importance(model, samp, y.loc[samp.index], scoring="roc_auc", n_repeats=3, random_state=0)
    importance = (pd.Series(imp.importances_mean, index=[FEATURE_LABELS[f] for f in feats])
                  .clip(lower=0).sort_values(ascending=False))

    fam = _bucket(d["track_prev_plays"], [0, 1, 2, 5, 10, 25, 1e9], ["First time", "2nd", "3rd–5th", "6th–10th", "11th–25th", "26th +"])
    by_familiarity = d.groupby(fam, observed=False)["skipped"].mean()
    pos = _bucket(d["pos_in_session"], [0, 1, 5, 10, 20, 50, 1e9], ["1st", "2–5", "6–10", "11–20", "21–50", "51 +"])
    by_position = d.groupby(pos, observed=False)["skipped"].mean()
    start = d["reason_start"].astype(str).map(START_SHORT).fillna("Other")
    grid = (d.assign(start=start, fam=fam).groupby(["start", "fam"], observed=False)["skipped"]
            .agg(["mean", "size"]))
    grid.loc[grid["size"] < 50, "mean"] = np.nan
    grid = grid["mean"].unstack().reindex(["You picked it", "Pressed play", "Autoplay", "Skipped to it", "Went back to it"])
    after_skip = d.loc[d["prev_skipped"] == 1, "skipped"].mean()
    after_play = d.loc[(d["prev_skipped"] == 0) & (d["pos_in_session"] > 0), "skipped"].mean()

    insights = [
        f"A model trained on {years[0]}–{years[-3]} predicts your {years[-2]}–{years[-1]} skips with an "
        f"AUC of **{auc:.2f}** (0.5 = coin flip, 1 = perfect). The strongest signals are "
        f"**{importance.index[0].lower()}**, {importance.index[1].lower()} and {importance.index[2].lower()}.",
        f"Skips come in chains: right after a skip you skip the next track **{after_skip:.0%}** of the time, "
        f"compared with {after_play:.0%} after a track you let play.",
    ]
    f0, fn = by_familiarity.iloc[0], by_familiarity.iloc[-1]
    verdict = ("Familiarity barely changes it" if abs(f0 - fn) < 0.03 else
               "Familiar tracks survive better" if fn < f0 else "You tire of tracks you know")
    insights.append(f"{verdict}: you skip {f0:.0%} of tracks the first time you hear them and {fn:.0%} of tracks "
                    f"you've already played 25+ times. How a track starts matters far more: "
                    f"{grid.loc['Autoplay'].mean():.0%} skipped after autoplay, compared with "
                    f"{grid.loc['Skipped to it'].mean():.0%} when you arrived by skipping.")
    return {"auc": auc, "importance": importance, "by_familiarity": by_familiarity,
            "by_position": by_position, "grid": grid, "insights": insights}


# 3. Retention ------------------------------------------------------------------

def _kaplan_meier(durations, events):
    t = np.asarray(durations, float)
    e = np.asarray(events, bool)
    times = np.sort(np.unique(t[e]))
    s, curve = 1.0, [(0.0, 1.0)]
    for ti in times:
        at_risk = (t >= ti).sum()
        d = ((t == ti) & e).sum()
        if at_risk:
            s *= 1 - d / at_risk
            curve.append((ti, s))
    return pd.Series([v for _, v in curve], index=[k for k, _ in curve])


def retention(df, horizon=24):
    sub = df[df["year"].isin(main_years(df)) & df["is_stream"]].copy()
    first = sub.groupby("artist")["ts_local"].min()
    sub["first"] = sub["artist"].map(first)
    early = sub[(sub["ts_local"] - sub["first"]).dt.days <= 30].groupby("artist").size()
    engaged = early[early >= 3].index  # artists you actually got into, not one autoplayed song
    first_e = first[engaged]
    history_start = sub["ts_local"].min() + pd.Timedelta(days=60)
    first_e = first_e[first_e >= history_start]  # skip artists that only look "new" because history begins

    end = sub["ts_local"].max()
    last_full = end.to_period("M") - 1
    active = sub[sub["artist"].isin(first_e.index)].assign(m=lambda x: x["ts_local"].dt.to_period("M"))
    active = active[["artist", "m"]].drop_duplicates()
    active["k"] = (active["m"] - active["artist"].map(first_e).dt.to_period("M")).apply(lambda p: p.n)
    cohort = first_e.dt.to_period("Y")
    sizes = cohort.value_counts().sort_index()
    mat = pd.DataFrame(index=[str(q) for q in sizes.index], columns=range(1, horizon + 1), dtype=float)
    for q in sizes.index:
        arts = cohort[cohort == q].index
        a = active[active["artist"].isin(arts)]
        for k in range(1, horizon + 1):
            if (q.asfreq("M", "end") + k) > last_full:  # not every artist of the cohort has had k months yet
                continue
            mat.loc[str(q), k] = a.loc[a["k"] == k, "artist"].nunique() / len(arts)
    mat = mat[sizes.values >= 8] if (sizes >= 8).any() else mat
    mat = mat.dropna(how="all")

    last = sub[sub["artist"].isin(first_e.index)].groupby("artist")["ts_local"].max()
    life = (last - first_e).dt.days
    ended = last < end - pd.Timedelta(days=90)
    first_reason = (sub[sub["artist"].isin(first_e.index)].sort_values("ts_local")
                    .drop_duplicates("artist").set_index("artist")["reason_start"])
    chose = first_reason.isin(["clickrow", "playbtn", "backbtn"])
    curves = {"All discoveries": _kaplan_meier(life, ended[life.index])}
    if chose.sum() >= 20 and (~chose).sum() >= 20:
        curves["You picked the first track"] = _kaplan_meier(life[chose], ended[life.index][chose])
        curves["First track was autoplayed / shuffled"] = _kaplan_meier(life[~chose], ended[life.index][~chose])

    def median(curve):
        below = curve[curve <= 0.5]
        return below.index[0] if len(below) else None

    hours_first60 = sub[sub["artist"].isin(first_e.index) & ((sub["ts_local"] - sub["first"]).dt.days <= 60)]
    h60 = hours_first60.groupby("artist")["minutes"].sum() / 60
    flash = (pd.DataFrame({"first": first_e, "last": last, "h60": h60}).dropna()
             .query("h60 >= 2").assign(days=lambda x: (x["last"] - x["first"]).dt.days)
             .query("days <= 180").sort_values("h60", ascending=False).head(8))
    monthly = (sub[sub["artist"].isin(first_e.index)].assign(m=lambda x: x["ts_local"].dt.to_period("M"))
               .groupby(["artist", "m"])["minutes"].sum())
    peak = monthly.groupby(level=0).idxmax().map(lambda t: t[1])
    tot = monthly.groupby(level=0).sum() / 60
    slow = (pd.DataFrame({"first": first_e.dt.to_period("M"), "peak": peak, "hours": tot}).dropna()
            .assign(lag=lambda x: (x["peak"] - x["first"]).apply(lambda p: p.n))
            .query("lag >= 6 and hours >= 5").sort_values("hours", ascending=False).head(8))

    med = median(curves["All discoveries"])
    m3 = mat[3].dropna().mean() if 3 in mat else float("nan")
    m12 = mat[12].dropna().mean() if 12 in mat else float("nan")
    insights = [
        f"You really got into **{len(first_e):,} new artists** (3+ streams in their first month). "
        f"On average {m3:.0%} were still in your rotation 3 months later and {m12:.0%} after a year.",
    ]
    if med is not None:
        insights.append(f"Half of your discoveries are gone after about **{med / 30.4:.0f} months** (Kaplan–Meier median "
                        f"of the time from first to last stream).")
    if len(curves) == 3:
        m_c, m_a = median(curves["You picked the first track"]), median(curves["First track was autoplayed / shuffled"])
        if m_c and m_a:
            insights.append(f"Artists you found by choosing a track yourself last a median **{m_c / 30.4:.0f} months**, "
                            f"compared with {m_a / 30.4:.0f} for artists you met through autoplay or shuffle.")
    return {"matrix": mat, "sizes": sizes, "curves": curves, "flash": flash, "slow": slow,
            "insights": insights}


# 4. Genres & origins -----------------------------------------------------------

def genres(df, cache):
    if not cache:
        return None
    ag = artist_genres(cache)
    sub = df[df["year"].isin(main_years(df))]
    ah = sub.groupby(["year", "artist"])["minutes"].sum().div(60).reset_index()
    rows = [(r.year, g, r.minutes * w) for r in ah.itertuples() for g, w in ag.get(r.artist, {}).items()]
    if not rows:
        return None
    gy = pd.DataFrame(rows, columns=["year", "genre", "hours"]).groupby(["year", "genre"])["hours"].sum().unstack(fill_value=0)
    total = gy.sum().sort_values(ascending=False)
    coverage = sub[sub["artist"].isin(ag)]["minutes"].sum() / sub["minutes"].sum()
    top = total.index[:MAX_GROUPS].tolist()
    share = gy.div(gy.sum(axis=1), axis=0)
    yearly = share[top].copy()
    yearly["Other genres"] = 1 - yearly.sum(axis=1)
    p = share.clip(lower=1e-12)
    diversity = np.exp(-(p * np.log(p)).sum(axis=1))  # effective number of genres

    mb = cache.get("mbids", {})
    origin = {a: mb.get(v.get("mbid") or "", {}).get("country") for a, v in cache.get("artists", {}).items()}
    oy = (sub.assign(origin=sub["artist"].map(origin)).dropna(subset=["origin"])
          .groupby(["year", "origin"])["minutes"].sum().unstack(fill_value=0))
    oshare = oy.div(oy.sum(axis=1), axis=0)
    otop = oy.sum().sort_values(ascending=False).index[:4].tolist()
    origins = oshare[otop].copy()
    origins["Elsewhere"] = 1 - origins.sum(axis=1)

    rising = (share.iloc[-1] - share.iloc[:-1].mean()).sort_values()
    insights = [
        f"MusicBrainz has genres for artists covering **{coverage:.0%}** of your listening. "
        f"Your top genres: " + ", ".join(f"**{g}**" for g in top[:4]) + ".",
        f"You listened most widely in **{diversity.idxmax()}** (about {diversity.max():.0f} genres' worth) and "
        f"most narrowly in {diversity.idxmin()} ({diversity.min():.0f}).",
        f"Rising in {share.index[-1]} compared with earlier years: **{rising.index[-1]}**. Fading: **{rising.index[0]}**.",
    ]
    if "IT" in oshare:
        it = oshare["IT"]
        insights.append(f"Italian artists make up {it.iloc[0]:.0%} of your {it.index[0]} listening and "
                        f"{it.iloc[-1]:.0%} in {it.index[-1]}.")
    return {"total": total, "yearly": yearly, "diversity": diversity, "origins": origins,
            "your_share": total / total.sum(), "insights": insights}


# 5. Suggestions ----------------------------------------------------------------

def _placeholder(r):
    """MusicBrainz special-purpose artists such as [unknown] or Various Artists."""
    name = r.get("name") or ""
    return name.startswith("[") or name.lower() in {"various artists", "anonymous"} or \
        "special purpose" in (r.get("comment") or "").lower()


def similar_candidates(df, cache, n_seeds=150):
    """Artists recommended by your most-played artists that you've never played."""
    hours = artist_hours(df)
    mbids = artist_mbids(cache)
    known = {norm(a) for a in df["artist"].unique()}
    seeds = [a for a in hours.index if a in mbids][:n_seeds]
    score, because, info = {}, {}, {}
    for seed in seeds:
        w = np.log1p(hours[seed])
        for r in cache.get("similar", {}).get(mbids[seed], []):
            if norm(r["name"]) in known or _placeholder(r):
                continue
            m = r["mbid"]
            score[m] = score.get(m, 0) + w * r["score"] / 100
            because.setdefault(m, []).append((seed, w * r["score"] / 100))
            info[m] = r
    if not score:
        return pd.DataFrame(columns=["mbid", "name", "score", "seeds", "because", "comment"])
    rows = [{"mbid": m, "name": info[m]["name"], "score": s, "seeds": len(because[m]),
             "because": [b for b, _ in sorted(because[m], key=lambda x: -x[1])[:3]],
             "comment": info[m].get("comment", "")}
            for m, s in score.items()]
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


def suggestions(df, cache, genre_data=None, forgotten=None, scenes=None, per_scene=4):
    if not cache or not cache.get("similar"):
        return None
    cands = similar_candidates(df, cache)
    if cands.empty:
        return None
    your_share = genre_data["your_share"] if genre_data else pd.Series(dtype=float)
    cands["genres"] = cands["mbid"].map(lambda m: mbid_genres(cache, m))
    cands["fam"] = cands["genres"].map(
        lambda gs: max((your_share.get(g, 0) for g in gs), default=None) if gs else None)

    # Balance across your scenes: each candidate belongs to the scene of the artist that recommends it most.
    by_scene = []
    if scenes is not None:
        scene_of = scenes["scene_of"]
        cands["scene"] = cands["because"].map(lambda b: scene_of.get(b[0]) if b else None)
        for gid, name in scenes["names"].items():
            if name == "Other scenes":
                continue
            pick = cands[cands["scene"] == gid].head(per_scene)
            if len(pick):
                by_scene.append((name, pick))
    else:
        by_scene = [("Close to home", cands.head(per_scene * 4))]
    chosen = pd.concat([p for _, p in by_scene]) if by_scene else cands.head(0)

    # Out of the bubble: still recommended by your artists, but in genres you barely play.
    pool = cands[~cands["mbid"].isin(chosen["mbid"])].dropna(subset=["fam"])
    bubble, per_genre = [], {}
    for r in pool[pool["fam"] < 0.01].sort_values("score", ascending=False).itertuples():
        main = r.genres[0]
        if per_genre.get(main, 0) < 2:  # keep the bubble-breakers varied
            per_genre[main] = per_genre.get(main, 0) + 1
            bubble.append(r.Index)
        if len(bubble) == 12:
            break
    bubble = pool.loc[bubble]

    # Genre keywords: genres around the (scene-balanced) recommendations that you rarely play.
    gw = {}
    if scenes is not None:
        top_by_scene = cands.dropna(subset=["scene"]).groupby("scene", group_keys=False).head(25)
    else:
        top_by_scene = cands.head(150)
    for r in top_by_scene.itertuples():
        rank_w = r.score / top_by_scene.loc[top_by_scene["scene"] == r.scene, "score"].max() \
            if scenes is not None else r.score
        for g in r.genres:
            gw[g] = gw.get(g, 0) + rank_w
    keywords = []
    if gw:
        kw = pd.DataFrame({"weight": pd.Series(gw)})
        kw["yours"] = [your_share.get(g, 0) for g in kw.index]
        kw = kw[kw["yours"] < 0.02].sort_values("weight", ascending=False).head(18)
        keywords = [{"q": g, "url": spotify_search_url(g), "note": f"{row.yours:.1%} of your listening"}
                    for g, row in kw.iterrows()]

    revisit = []
    if forgotten is not None and len(forgotten):
        revisit = [{"q": f"This Is {a}", "url": spotify_search_url(f"This Is {a}"),
                    "note": f"{row.early:.0f} h back then, {row.recent * 60:.0f} min in the last year"}
                   for a, row in forgotten.head(8).iterrows()]

    def as_cards(frame):
        return [{"name": r.name, "url": spotify_search_url(r.name), "genres": r.genres,
                 "because": r.because, "comment": r.comment} for r in frame.itertuples()]

    insights = [
        "These come from **ListenBrainz**, an open music database built from what its listeners play together, "
        "not from Spotify's recommendations. Every artist here is one you've **never played**. Click a name to "
        "search it on Spotify.",
        "Recommendations are balanced across your scenes, so your Italian side and your international side "
        "each get their own picks.",
    ]
    return {"by_scene": [(name, as_cards(p)) for name, p in by_scene], "bubble": as_cards(bubble),
            "keywords": keywords, "revisit": revisit, "insights": insights}
