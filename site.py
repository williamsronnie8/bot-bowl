"""Build the league's web page (index.html) from league.json.

Run after league.py: python3 site.py
"""
import json
from datetime import datetime, timezone

import league
from league import sleeper

COLORS = {"nerd": "#2f6fdf", "hype": "#e0475b", "loyal": "#7a52c7", "gambler": "#e8892b",
          "rearview": "#1f9e8f", "couch": "#8a8f98", "coin": "#c9a227", "stream": "#3aa1d8"}


def main():
    state = json.loads(league.STATE.read_text())
    plist = sleeper.players()
    current = sleeper.state()["week"]
    teams = state["teams"]

    players, weeks = {}, {}
    for w, wdata in sorted(state["weeks"].items(), key=lambda kv: int(kv[0])):
        proj = sleeper.projections(state["season"], int(w))
        stats = sleeper.stats(state["season"], int(w))
        final = "scores" in wdata
        pts = {}
        for roster in wdata["rosters"]:
            for pid in roster:
                p = plist.get(pid, {})
                players[pid] = {"n": sleeper.name(plist, pid), "pos": p.get("position"),
                                "tm": p.get("team"), "inj": p.get("injury_status")}
                played = (stats.get(pid) or {}).get("gp")
                pts[pid] = [round(sleeper.points(proj.get(pid)), 1),
                            round(sleeper.points(stats.get(pid)), 1) if final or played else None]
        live = [round(sum(pts[p][1] or 0 for p in lineup if p), 1) for lineup in wdata["lineups"]]
        weeks[w] = {
            "final": final,
            "matchups": state["schedule"][w],
            "scores": wdata.get("scores") or live,
            "proj": [round(sum(pts[p][0] for p in lineup if p), 1) for lineup in wdata["lineups"]],
            "lineups": wdata["lineups"],
            "rosters": wdata["rosters"],
            "moves": wdata["moves"],
            "potw": wdata.get("player_of_week"),
            "ouch": wdata.get("ouch"),
            "pts": pts,
        }

    standings = []
    for i, t in enumerate(teams):
        _, pf, wins, losses, ties = league.record(state, i)
        standings.append({"name": t["name"], "style": t["style"], "about": t["about"],
                          "color": COLORS[t["style"]], "w": wins, "l": losses, "t": ties, "pf": round(pf, 1)})

    data = {"season": state["season"], "current": min(current, league.LAST_REGULAR_WEEK),
            "last": league.LAST_REGULAR_WEEK, "start": state["start_week"],
            "updated": datetime.now(timezone.utc).strftime("%b %-d, %-I:%M %p UTC"),
            "teams": standings, "weeks": weeks, "players": players}
    page = (league.HERE / "page.html").read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    (league.HERE / "index.html").write_text(WRAPPER.replace("__PAGE__", page))
    print(f"Wrote index.html ({len(page) // 1024} KB)")


WRAPPER = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
body{margin:0;font:14px system-ui,-apple-system,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
</head><body>
__PAGE__
</body></html>
"""


if __name__ == "__main__":
    main()
