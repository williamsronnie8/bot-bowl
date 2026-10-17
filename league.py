"""An all-bot fantasy league to watch: 8 computer managers, each with its own
style, playing on real NFL scores from Sleeper.

python3 league.py setup   # draft and schedule (once)
python3 league.py         # score finished weeks, lock this week's lineups, write recaps
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import sleeper

HERE = Path(__file__).parent

STATE = HERE / "league.json"
RECAPS = HERE / "recaps"
LAST_REGULAR_WEEK = 14
SLOTS = [("QB", {"QB"}), ("RB", {"RB"}), ("RB", {"RB"}), ("WR", {"WR"}), ("WR", {"WR"}),
         ("TE", {"TE"}), ("FLEX", {"RB", "WR", "TE"}), ("K", {"K"}), ("DEF", {"DEF"})]
MINIMUM = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}
SIDELINED = {"Out", "IR", "PUP", "Sus", "NA", "DNR", "Doubtful"}

BOTS = [
    ("The Spreadsheet", "nerd", "Starts whoever projects best; picks up whoever projects best."),
    ("Bandwagon FC", "hype", "Grabs whoever everyone else is grabbing, every week."),
    ("Ride or Die", "loyal", "Starts the best projected players, but never drops anyone."),
    ("Big Swing Energy", "gambler", "Starts whoever scored most last week; chases last week's big games."),
    ("Rearview Mirror", "rearview", "Starts whoever has scored most per game this season."),
    ("Set It & Forget It", "couch", "Set a lineup on draft day and never touched it again."),
    ("Heads or Tails", "coin", "Picks lineups at random. Sometimes adds a random player."),
    ("Stream Team", "stream", "Starts by projection; swaps kicker and defense every week for the best matchup."),
]


CAPS = {"QB": 2, "RB": 5, "WR": 5, "TE": 2}


def draft(plist, teams, rounds=15):
    """Snake draft by Sleeper's ranking; kickers and defenses go in the last rounds."""
    season = sleeper.state()["season"]
    season_proj = sleeper.get(f"projections/nfl/regular/{season}")

    def ranked(positions, key):
        pool = [pid for pid, p in plist.items()
                if p.get("position") in positions and p.get("active") and p.get("team")]
        return sorted(pool, key=key)

    skill = ranked(CAPS, lambda pid: plist[pid].get("search_rank") or 99999)
    kdef = {pos: ranked([pos], lambda pid: -sleeper.points(season_proj.get(pid))) for pos in ("K", "DEF")}

    rosters = [[] for _ in range(teams)]
    taken = set()
    for rnd in range(rounds):
        order = range(teams) if rnd % 2 == 0 else reversed(range(teams))
        for t in order:
            roster = rosters[t]
            count = lambda pos: sum(plist[x]["position"] == pos for x in roster)
            need = [pos for pos in ("DEF", "K") if count(pos) == 0]
            if rnd >= rounds - len(need):
                pick = next(pid for pid in kdef[need[0]] if pid not in taken)
            else:
                pick = next(pid for pid in skill
                            if pid not in taken and count(plist[pid]["position"]) < CAPS[plist[pid]["position"]])
            roster.append(pick)
            taken.add(pick)
    return rosters


class Week:
    """Everything a bot might look at when making decisions for one week."""

    def __init__(self, season, week, plist, rosters):
        self.week, self.plist = week, plist
        self.proj = sleeper.projections(season, week)
        upcoming = [sleeper.projections(season, w) for w in range(week, min(week + 3, 19))]
        self.upcoming = [(p, sleeper.teams_playing(p, plist)) for p in upcoming]
        self.past = {w: sleeper.stats(season, w) for w in range(1, week)}
        rostered = {pid for r in rosters for pid in r}
        self.free = [pid for pid, p in plist.items()
                     if p.get("position") in sleeper.POSITIONS and p.get("active") and p.get("team")
                     and pid not in rostered and p.get("injury_status") not in SIDELINED]

    def pos(self, pid):
        return self.plist[pid]["position"]

    def pts(self, pid):
        return sleeper.points(self.proj.get(pid))

    def per_game(self, pid):
        games = [sleeper.points(p.get(pid)) for p, teams in self.upcoming
                 if self.plist[pid].get("team") in teams]
        return sum(games) / len(games) if games else 0.0

    def last_week(self, pid):
        return sleeper.points(self.past.get(self.week - 1, {}).get(pid))

    def season_avg(self, pid):
        games = [sleeper.points(s.get(pid)) for s in self.past.values() if (s.get(pid) or {}).get("gp")]
        return sum(games) / len(games) if games else 0.0


def best_lineup(roster, value, can_play, pos):
    lineup, left = [], sorted([p for p in roster if can_play(p)], key=value, reverse=True)
    for _, ok in SLOTS:
        pick = next((p for p in left if pos(p) in ok), None)
        lineup.append(pick)
        if pick:
            left.remove(pick)
    return lineup


def can_swap(roster, out, inn, pos):
    after = [p for p in roster if p != out] + [inn]
    return all(sum(pos(p) == k for p in after) >= n for k, n in MINIMUM.items())


def swap_for(roster, add, value, wk):
    """Who to drop for `add`: the lowest-valued player whose loss keeps a full lineup."""
    options = [p for p in roster if can_swap(roster, p, add, wk.pos)]
    return min(options, key=value) if options else None


def decide_moves(style, roster, wk, rng):
    """Return a list of (add, drop) this bot wants this week."""
    moves = []
    if style == "nerd":
        best = None
        for position in ("QB", "RB", "WR", "TE"):
            add = max((p for p in wk.free if wk.pos(p) == position), key=wk.per_game, default=None)
            mine = [p for p in roster if wk.pos(p) == position]
            if add and mine:
                drop = min(mine, key=wk.per_game)
                gain = wk.per_game(add) - wk.per_game(drop)
                if gain >= 1.5 and (not best or gain > best[0]):
                    best = (gain, add, drop)
        if best:
            moves.append(best[1:])
    elif style == "hype":
        free = set(wk.free)
        hot = next((t["player_id"] for t in sleeper.trending_adds() if t["player_id"] in free), None)
        if hot:
            moves.append((hot, swap_for(roster, hot, wk.per_game, wk)))
    elif style == "gambler" and wk.week > 1:
        add = max(wk.free, key=wk.last_week)
        drop = swap_for(roster, add, wk.last_week, wk)
        if drop and wk.last_week(add) > wk.last_week(drop):
            moves.append((add, drop))
    elif style == "rearview" and wk.week > 2:
        add = max(wk.free, key=wk.season_avg)
        drop = swap_for(roster, add, wk.season_avg, wk)
        if drop and wk.season_avg(add) - wk.season_avg(drop) >= 3:
            moves.append((add, drop))
    elif style == "stream":
        for position in ("K", "DEF"):
            add = max((p for p in wk.free if wk.pos(p) == position), key=wk.pts, default=None)
            mine = [p for p in roster if wk.pos(p) == position]
            if add and mine and wk.pts(add) - wk.pts(mine[0]) >= 1:
                moves.append((add, mine[0]))
    elif style == "coin" and rng.random() < 0.5:
        add = rng.choice([p for p in wk.free if wk.pts(p) > 3] or wk.free)
        options = [p for p in roster if can_swap(roster, p, add, wk.pos)]
        if options:
            moves.append((add, rng.choice(options)))
    return [(a, d) for a, d in moves if a and d]


def fill_holes(roster, wk):
    """Pick up a stand-in for any position that can't field a full lineup (byes, injuries)."""
    moves = []
    for position, need in MINIMUM.items():
        while sum(wk.pos(p) == position and wk.pts(p) > 0 for p in roster) < need:
            add = max((p for p in wk.free if wk.pos(p) == position and wk.pts(p) > 0), key=wk.pts, default=None)
            options = [p for p in roster if can_swap(roster, p, add, wk.pos)
                       and not (wk.pos(p) != position and wk.pts(p) > 0 and wk.pos(p) in ("QB", "K", "DEF", "TE"))] if add else []
            if not options:
                break
            drop = min(options, key=wk.per_game)
            roster[roster.index(drop)] = add
            wk.free.remove(add)
            moves.append((add, drop))
    return moves


def choose_lineup(team, wk, rng):
    style, roster = team["style"], team["roster"]
    if style == "couch":
        return team["draft_day_lineup"]
    plays = lambda p: wk.pts(p) > 0
    value = {"gambler": lambda p: (wk.last_week(p), wk.pts(p)),
             "rearview": lambda p: (wk.season_avg(p), wk.pts(p)),
             "coin": lambda p: rng.random()}.get(style, wk.pts)
    return best_lineup(roster, value, plays, wk.pos)


def lock(state, w, plist):
    """Bots make their moves (worst record first), then set lineups."""
    rosters = [t["roster"] for t in state["teams"]]
    wk = Week(state["season"], w, plist, rosters)
    order = sorted(range(len(state["teams"])), key=lambda i: record(state, i))
    moves, lineups = [], {}
    for i in order:
        team = state["teams"][i]
        rng = random.Random(f"{w}-{i}")
        for add, drop in decide_moves(team["style"], team["roster"], wk, rng):
            if add in wk.free and drop in team["roster"]:
                team["roster"][team["roster"].index(drop)] = add
                wk.free.remove(add)
                moves.append([i, add, drop])
        if team["style"] not in ("loyal", "couch"):
            moves += [[i, add, drop] for add, drop in fill_holes(team["roster"], wk)]
        lineups[i] = choose_lineup(team, wk, rng)
    state["weeks"][str(w)] = {"moves": moves, "lineups": [lineups[i] for i in range(len(state["teams"]))],
                              "rosters": [list(t["roster"]) for t in state["teams"]]}


def record(state, i):
    wins = losses = ties = 0
    pf = 0.0
    for wdata in state["weeks"].values():
        if "scores" not in wdata:
            continue
        pf += wdata["scores"][i]
        for a, b in wdata["matchups"]:
            if i in (a, b):
                me, them = (wdata["scores"][a], wdata["scores"][b]) if i == a else (wdata["scores"][b], wdata["scores"][a])
                wins, losses, ties = wins + (me > them), losses + (me < them), ties + (me == them)
    return (wins + ties / 2, pf, wins, losses, ties)


def score(state, w, plist):
    stats = sleeper.stats(state["season"], w)
    wdata = state["weeks"][str(w)]
    pts = lambda p: sleeper.points(stats.get(p)) if p else 0.0
    wdata["scores"] = [round(sum(pts(p) for p in lineup), 2) for lineup in wdata["lineups"]]
    wdata["matchups"] = state["schedule"][str(w)]
    teams = state["teams"]
    name = lambda p: sleeper.name(plist, p)

    lines = [f"# Week {w} recap", "", "## Scores"]
    for a, b in wdata["matchups"]:
        (wi, wsc), (li, lsc) = sorted([(a, wdata["scores"][a]), (b, wdata["scores"][b])], key=lambda x: -x[1])
        verb = "tied" if wsc == lsc else "beat"
        lines.append(f"- **{teams[wi]['name']}** {wsc:.1f} {verb} {teams[li]['name']} {lsc:.1f}")

    starters = [(pts(p), p, i) for i, lineup in enumerate(wdata["lineups"]) for p in lineup if p]
    top, pid, i = max(starters)
    wdata["player_of_week"] = [i, pid, top]
    lines += ["", f"**Player of the week:** {name(pid)}, {top:.1f} points for {teams[i]['name']}."]

    worst = None  # biggest bench blunder: a benched player who outscored a starter they could have replaced
    for i, lineup in enumerate(wdata["lineups"]):
        bench = [p for p in wdata["rosters"][i] if p not in lineup]
        for b in bench:
            for s, (_, ok) in zip(lineup, SLOTS):
                if s and plist[b]["position"] in ok and (not worst or pts(b) - pts(s) > worst[0]):
                    worst = (pts(b) - pts(s), i, b, s)
    if worst and worst[0] > 5:
        gap, i, b, s = worst
        wdata["ouch"] = [i, b, s]
        lines.append(f"**Ouch:** {teams[i]['name']} benched {name(b)} ({pts(b):.1f}) "
                     f"and started {name(s)} ({pts(s):.1f}). That's {gap:.1f} points left on the bench.")

    if wdata["moves"]:
        lines += ["", "## Moves"]
        lines += [f"- {teams[i]['name']} added {name(a)}, dropped {name(d)}" for i, a, d in wdata["moves"]]

    lines += ["", "## Standings", "", "| | Team | Style | Record | Points |", "|---|---|---|---|---|"]
    table = sorted(range(len(teams)), key=lambda i: record(state, i), reverse=True)
    for rank, i in enumerate(table, 1):
        _, pf, wins, losses, ties = record(state, i)
        rec = f"{wins}-{losses}" + (f"-{ties}" if ties else "")
        lines.append(f"| {rank} | {teams[i]['name']} | {teams[i]['style']} | {rec} | {pf:.1f} |")
    RECAPS.mkdir(exist_ok=True)
    text = "\n".join(lines) + "\n"
    (RECAPS / f"week-{w:02d}.md").write_text(text)
    return text


def preview(state, w, plist):
    wdata = state["weeks"][str(w)]
    proj = sleeper.projections(state["season"], w)
    total = lambda i: sum(sleeper.points(proj.get(p)) for p in wdata["lineups"][i] if p)
    out = [f"Week {w} lineups are locked. Matchups (projected points):"]
    for a, b in state["schedule"][str(w)]:
        out.append(f"  {state['teams'][a]['name']} ({total(a):.0f}) vs {state['teams'][b]['name']} ({total(b):.0f})")
    if wdata["moves"]:
        out.append("Moves this week:")
        out += [f"  {state['teams'][i]['name']} added {sleeper.name(plist, a)}, dropped {sleeper.name(plist, d)}"
                for i, a, d in wdata["moves"]]
    return "\n".join(out)


def setup():
    st = sleeper.state()
    plist = sleeper.players()
    rng = random.Random(st["season"])
    bots = BOTS[:]
    rng.shuffle(bots)  # random draft order
    rosters = draft(plist, teams=len(bots))
    teams = []
    for (name, style, about), roster in zip(bots, rosters):
        rank = lambda p: -(plist[p].get("search_rank") or 99999)
        lineup = best_lineup(roster, rank, lambda p: True, lambda p: plist[p]["position"])
        teams.append({"name": name, "style": style, "about": about, "roster": roster, "draft_day_lineup": lineup})
    # Round robin (circle method), repeated until the regular season ends.
    rest, schedule = list(range(1, len(teams))), {}
    for n, w in enumerate(range(st["week"], LAST_REGULAR_WEEK + 1)):
        k = n % len(rest)
        r = [0] + rest[k:] + rest[:k]
        schedule[str(w)] = [[r[j], r[-1 - j]] for j in range(len(r) // 2)]
    state = {"season": st["season"], "start_week": st["week"], "next_week": st["week"],
             "teams": teams, "schedule": schedule, "weeks": {}}
    STATE.write_text(json.dumps(state, indent=1) + "\n")
    print(f"Drafted {len(teams)} bot teams. Season runs weeks {st['week']}–{LAST_REGULAR_WEEK}.")
    for t in teams:
        print(f"  {t['name']} ({t['style']}): {t['about']}")


def finished(st, w):
    """Week w is over once it's Tuesday midday (UTC) after its Monday night game."""
    start = datetime.fromisoformat(st["season_start_date"]).replace(tzinfo=timezone.utc)  # a Wednesday
    return datetime.now(timezone.utc) >= start + timedelta(days=7 * (w - 1) + 6, hours=12)


def play():
    state = json.loads(STATE.read_text())
    plist = sleeper.players()
    st = sleeper.state()
    current = st["week"]
    for w in range(state["next_week"], min(current, LAST_REGULAR_WEEK + 1)):
        if not finished(st, w):
            break
        if str(w) not in state["weeks"]:
            lock(state, w, plist)
        print(score(state, w, plist))
        state["next_week"] = w + 1
    if current <= LAST_REGULAR_WEEK:
        if str(current) not in state["weeks"]:
            lock(state, current, plist)
        print(preview(state, current, plist))
    else:
        print("The regular season is over. Final standings are in the last recap.")
    STATE.write_text(json.dumps(state, indent=1) + "\n")


if __name__ == "__main__":
    setup() if sys.argv[1:] == ["setup"] else play()
