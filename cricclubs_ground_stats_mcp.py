"""
CricClubs Ground Stats MCP Server

An MCP tool that takes a CricClubs series URL and returns match duration
statistics aggregated by ground (avg, min, max duration + match count).
"""

import re
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "CricClubs Ground Stats",
    instructions="Fetch match duration stats per ground from CricClubs series",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def fetch_url(url: str) -> str:
    result = subprocess.run(
        ["curl", "-s", "-H", f"User-Agent: {USER_AGENT}", url],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise Exception(f"curl failed: {result.stderr}")
    return result.stdout


def parse_url(series_url: str) -> tuple[str, str, str]:
    """Extract base path, league ID, and club ID from a CricClubs URL."""
    parsed = urlparse(series_url)
    params = parse_qs(parsed.query)

    league_id = params.get("league", [""])[0]
    club_id = params.get("clubId", [""])[0]

    # Extract base path like /ARCL from the URL path
    path_parts = parsed.path.strip("/").split("/")
    base_path = path_parts[0] if path_parts else ""

    if not league_id or not club_id:
        raise ValueError(
            "URL must contain 'league' and 'clubId' parameters. "
            "Example: https://www.cricclubs.com/ARCL/listMatches.do?league=321&clubId=992"
        )

    base_url = f"{parsed.scheme}://{parsed.netloc}/{base_path}"
    return base_url, league_id, club_id


def fetch_fixtures(base_url: str, league_id: str, club_id: str) -> list[dict]:
    url = f"{base_url}/fixtures.do?league={league_id}&clubId={club_id}"
    html = fetch_url(url)

    match = re.search(
        r'<table[^>]*id="schedule-table"[^>]*>(.*?)</table>', html, re.DOTALL
    )
    if not match:
        return []

    table = match.group(1)
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)

    matches = []
    for tr in trs[1:]:
        match_ids = re.findall(r"matchId=(\d+)", tr)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
        row = []
        for td in tds:
            clean = re.sub(r"<[^>]+>", " ", td).strip()
            clean = re.sub(r"\s+", " ", clean)
            clean = clean.replace("&nbsp;", "").strip()
            row.append(clean)

        if len(row) >= 7 and match_ids:
            matches.append({
                "match_id": match_ids[0],
                "date": row[2],
                "team1": row[4],
                "team2": row[5],
            })

    return matches


def parse_innings_times(html: str, label: str) -> tuple[str, str, str]:
    idx = html.find(label)
    if idx < 0:
        return "", "", ""
    chunk = html[idx:idx + 300]
    clean = re.sub(r"<[^>]+>", "|", chunk)
    clean = clean.replace("&nbsp;", " ")
    parts = [p.strip() for p in clean.split("|") if p.strip()]
    duration = parts[1] if len(parts) >= 2 else ""
    start_time = ""
    end_time = ""
    if len(parts) >= 3:
        times = re.findall(r"\d{1,2}:\d{2}\s*[AP]M", parts[2])
        if len(times) >= 2:
            start_time, end_time = times[0], times[1]
    return duration, start_time, end_time


def extract_field(html: str, keyword: str) -> str:
    idx = html.find(keyword)
    if idx < 0:
        return ""
    chunk = html[idx:idx + 500]
    clean = re.sub(r"<[^>]+>", "|", chunk)
    clean = clean.replace("&nbsp;", " ")
    parts = [p.strip() for p in clean.split("|") if p.strip()]
    return parts[1] if len(parts) >= 2 else ""


def fetch_match_info(base_url: str, club_id: str, match_id: str) -> dict:
    url = f"{base_url}/info.do?matchId={match_id}&clubId={club_id}"
    try:
        html = fetch_url(url)
    except Exception:
        return {}

    location = extract_field(html, "Location:")
    inn1_dur, inn1_start, inn1_end = parse_innings_times(html, "1st Innings:")
    inn2_dur, inn2_start, inn2_end = parse_innings_times(html, "2nd Innings:")
    break_dur, _, _ = parse_innings_times(html, "Innings break:")

    # Overs
    overs = re.findall(r"([\d.]+)\s*/\s*([\d.]+)\s*ov", html)
    team1_overs = f"{overs[0][0]}/{overs[0][1]}" if len(overs) >= 1 else ""
    team2_overs = f"{overs[1][0]}/{overs[1][1]}" if len(overs) >= 2 else ""

    # Total duration
    total_minutes = 0
    for d in [inn1_dur, break_dur, inn2_dur]:
        m = re.search(r"(\d+)\s*min", d)
        if m:
            total_minutes += int(m.group(1))

    return {
        "ground": location,
        "match_start_time": inn1_start,
        "match_end_time": inn2_end,
        "match_duration_min": total_minutes if total_minutes > 0 else None,
        "innings1_duration": inn1_dur,
        "innings2_duration": inn2_dur,
        "innings_break": break_dur,
        "team1_overs": team1_overs,
        "team2_overs": team2_overs,
    }


@mcp.tool()
def get_ground_stats(series_url: str) -> str:
    """
    Fetch match duration statistics aggregated by ground from a CricClubs series.

    Args:
        series_url: A CricClubs series URL containing league and clubId params.
                    Example: https://www.cricclubs.com/ARCL/listMatches.do?league=321&clubId=992
    """
    base_url, league_id, club_id = parse_url(series_url)

    # Step 1: Get all fixtures
    fixtures = fetch_fixtures(base_url, league_id, club_id)
    if not fixtures:
        return "No matches found for this series URL."

    # Step 2: Fetch info for each match concurrently
    info_map = {}

    def _fetch(match):
        mid = match["match_id"]
        return mid, fetch_match_info(base_url, club_id, mid)

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch, m): m for m in fixtures}
        for future in as_completed(futures):
            mid, info = future.result()
            info_map[mid] = info

    # Step 3: Aggregate by ground
    grounds = defaultdict(list)
    for match in fixtures:
        info = info_map.get(match["match_id"], {})
        ground = info.get("ground", "")
        duration = info.get("match_duration_min")
        if ground and duration and duration > 0:
            grounds[ground].append(duration)

    if not grounds:
        return f"Found {len(fixtures)} matches but none had timing data recorded."

    # Step 4: Build stats
    stats = []
    for ground, durations in grounds.items():
        stats.append({
            "ground": ground,
            "matches": len(durations),
            "avg": round(sum(durations) / len(durations)),
            "min": min(durations),
            "max": max(durations),
        })
    stats.sort(key=lambda x: -x["matches"])

    total_matches = sum(s["matches"] for s in stats)
    weighted_avg = round(
        sum(s["avg"] * s["matches"] for s in stats) / total_matches
    )

    # Step 5: Format as markdown table
    lines = [
        f"## Ground Stats ({total_matches} matches across {len(stats)} grounds)\n",
        "| Ground | Matches | Avg (min) | Min (min) | Max (min) |",
        "|--------|---------|-----------|-----------|-----------|",
    ]
    for s in stats:
        lines.append(
            f"| {s['ground']} | {s['matches']} | {s['avg']} | {s['min']} | {s['max']} |"
        )
    lines.append(
        f"| **TOTAL** | **{total_matches}** | **{weighted_avg}** | | |"
    )

    return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="stdio")
