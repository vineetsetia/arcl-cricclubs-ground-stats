# ARCL CricClubs Ground Stats

An MCP plugin for Claude Code that fetches match duration statistics per ground from any [CricClubs](https://www.cricclubs.com) cricket series.

## What it does

Given a CricClubs series URL, this tool:

1. Scrapes the fixtures page for all matches (date, time, teams, ground)
2. Fetches each match's info page for actual start/end times and innings durations
3. Aggregates match duration by ground and returns a summary table

**Sample output (ARCL Summer 2025 Men):**

| Ground | Matches | Avg (min) | Min (min) | Max (min) |
|--------|---------|-----------|-----------|-----------|
| North SeaTac Park | 46 | 136 | 77 | 303 |
| Ron Regis Park | 42 | 139 | 67 | 233 |
| Hidden Valley Park Field 1 | 31 | 122 | 81 | 147 |
| Big Finn Hill Park | 27 | 120 | 10 | 146 |
| Petrovitsky Park Field #2 | 17 | 125 | 93 | 157 |
| Petrovitsky Park Field #1 | 16 | 128 | 90 | 161 |
| Central Park Field #2 | 13 | 123 | 40 | 259 |
| Central Park Field #1 | 13 | 123 | 53 | 148 |
| Perigo Park Softball Field 1 | 12 | 124 | 65 | 158 |
| GrassLawn Park Softball Field 1 Pitch 1 | 11 | 123 | 57 | 146 |
| Redmond Ridge Park - Soccer Field | 11 | 131 | 103 | 146 |
| North Robinswood Park | 10 | 121 | 74 | 139 |
| Marymoor Park Soccer #5 | 8 | 133 | 115 | 151 |
| GrassLawn Park Softball Field 2 | 7 | 116 | 90 | 148 |
| Evergreen Playfields 1 | 6 | 120 | 77 | 135 |
| Hartman Park Soccer Field (Pitch 1) | 4 | 136 | 135 | 139 |
| Marymoor Park Soccer #6 | 3 | 205 | 122 | 348 |
| Central Park Field #3 | 3 | 106 | 67 | 150 |
| Central Park Field #4 | 3 | 109 | 87 | 142 |
| **TOTAL** | **283** | **129** | | |

## Setup

### Prerequisites

- Python 3.10+
- `mcp` Python package: `pip install "mcp[cli]"`
- `curl` available in PATH

### Option 1: Use as MCP server in Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "cricclubs-ground-stats": {
      "command": "python",
      "args": ["/path/to/cricclubs_ground_stats_mcp.py"]
    }
  }
}
```

Then in Claude Code, ask:

> Get ground stats for https://www.cricclubs.com/ARCL/listMatches.do?league=321&clubId=992

### Option 2: Install as Claude Marketplace plugin

Add to your `~/.claude/settings.json`:

```json
{
  "extraKnownMarketplaces": {
    "arcl-cricclubs-ground-stats": {
      "source": {
        "source": "github",
        "repo": "vineetsetia/arcl-cricclubs-ground-stats"
      }
    }
  },
  "enabledPlugins": {
    "cricclubs-ground-stats@arcl-cricclubs-ground-stats": true
  }
}
```

Restart Claude Code and the `get_ground_stats` tool will be available.

## Standalone scripts

### fetch_match_stats.py

Fetches all match data and writes two CSVs:

```bash
python fetch_match_stats.py
```

- `arcl_match_stats.csv` — matches with timing data
- `arcl_match_stats_without_result.csv` — matches without timing data

**Fields:** match_id, date, team1, team2, ground, match_start_time, match_end_time, match_duration, innings1/2 duration, innings break, overs bowled, toss

### ground_stats.py

Reads `arcl_match_stats.csv` and generates:

```bash
python ground_stats.py
```

- `ground_stats.csv` — aggregated stats per ground
- `ground_stats_chart.png` — bar chart with avg/min/max duration per ground (requires `matplotlib`)

## Input URL format

The tool accepts any CricClubs series URL that contains `league` and `clubId` parameters:

```
https://www.cricclubs.com/{LEAGUE}/listMatches.do?league={ID}&clubId={ID}
https://www.cricclubs.com/{LEAGUE}/fixtures.do?league={ID}&clubId={ID}
```

## Notes

- Only matches where the scorer recorded innings start/end times will have duration data
- Match duration = 1st innings + innings break + 2nd innings
- The tool fetches each match's info page concurrently (10 threads) for speed
