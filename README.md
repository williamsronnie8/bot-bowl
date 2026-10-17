# Bot Bowl

An all-bot fantasy football league. Eight computer managers, each with its own
style, play the 2026 NFL season on real stats. Nobody human makes a single move.

**Watch it:** https://williamsronnie8.github.io/bot-bowl/

- **Live scores:** the page pulls stats from Sleeper's free public data feed
  about once a minute while you have it open.
- **Everything else runs itself:** once a day, a GitHub Action
  (`.github/workflows/daily.yml`) scores finished weeks, lets the bots make
  their pickups and set lineups for the new week, and rebuilds the page. No AI
  involved; the bots are plain rules.
- **Run it by hand:** Actions tab → "Run the league" → Run workflow.

## The managers

| Team | Style |
|---|---|
| The Spreadsheet | Starts whoever projects best; picks up whoever projects best |
| Bandwagon FC | Grabs whoever everyone else is grabbing, every week |
| Ride or Die | Starts the best projected players, but never drops anyone |
| Big Swing Energy | Starts whoever scored most last week; chases last week's big games |
| Rearview Mirror | Starts whoever has scored most per game this season |
| Set It & Forget It | Set a lineup on draft day and never touched it again |
| Heads or Tails | Random lineups; sometimes adds a random player |
| Stream Team | Starts by projection; swaps kicker and defense every week |

Every bot grabs a stand-in when a bye or injury would leave a hole, except Ride
or Die and Set It & Forget It.

## How it works

- 8 teams, 15 players each, half-PPR scoring, weeks 6–14 of 2026, everyone
  plays everyone. No playoffs yet.
- Bots move worst-record-first, then set lineups with only pre-game info.
- A week counts as final after Tuesday midday UTC, once Monday night is done.
- Plain-text recaps land in `recaps/`.

## Files

| File | What it does |
|---|---|
| `league.py` | The league: draft, bots, moves, lineups, scoring, recaps |
| `site.py` | Builds `index.html` from `league.json` using the `page.html` design |
| `sleeper.py` | Fetches Sleeper data (projections and stats are an unofficial part of its feed) |
| `league.json` | The whole league history |

## Limits

- Projections and stats come from an undocumented part of Sleeper's feed.
  Works as of Oct 2026, could change.
- Injury news is whatever Sleeper says when the daily run happens.
- Bots drafted with October rankings (hindsight).
