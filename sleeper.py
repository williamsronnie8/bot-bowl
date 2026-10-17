"""Small helpers for Sleeper's free, read-only data feed.

Documented: state, players, trending, leagues/rosters.
Undocumented (work today, may change): weekly projections and stats.
"""
import json
import time
import urllib.request
from pathlib import Path

BASE = "https://api.sleeper.app/v1/"
CACHE = Path(__file__).parent / ".cache"
SCORING = "pts_half_ppr"
POSITIONS = ("QB", "RB", "WR", "TE", "K", "DEF")


def get(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "fantasy-comanager"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def cached(name, path, max_age_hours):
    """Fetch, but reuse a saved copy if it's fresh enough."""
    CACHE.mkdir(exist_ok=True)
    f = CACHE / name
    if f.exists() and time.time() - f.stat().st_mtime < max_age_hours * 3600:
        return json.loads(f.read_text())
    data = get(path)
    f.write_text(json.dumps(data))
    return data


def state():
    return get("state/nfl")


def players():
    # Sleeper asks that the full player list be fetched at most once a day.
    return cached("players.json", "players/nfl", 24)


def projections(season, week):
    return cached(f"proj-{season}-{week}.json", f"projections/nfl/regular/{season}/{week}", 6)


def stats(season, week):
    return cached(f"stats-{season}-{week}.json", f"stats/nfl/regular/{season}/{week}", 6)


def trending_adds(hours=24, limit=50):
    return get(f"players/nfl/trending/add?lookback_hours={hours}&limit={limit}")


def points(row):
    return (row or {}).get(SCORING, 0.0) or 0.0


def teams_playing(proj, plist):
    """Teams with any projected player this week; everyone else is on bye."""
    return {plist[pid].get("team") for pid, row in proj.items()
            if pid in plist and points(row) > 0} - {None}


def find_player(plist, name):
    """Match a typed name to a player, preferring active, ranked players."""
    want = name.strip().lower()
    hits = [(pid, p) for pid, p in plist.items()
            if p.get("position") in POSITIONS
            and want in ((p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}").lower(),
                         pid.lower())]
    hits.sort(key=lambda h: (not h[1].get("active"), h[1].get("search_rank") or 99999))
    return hits[0][0] if hits else None


def name(plist, pid):
    p = plist.get(pid, {})
    if p.get("position") == "DEF":
        return f"{pid} defense"
    return p.get("full_name") or pid
