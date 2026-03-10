import re
import csv
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://www.cricclubs.com/ARCL"
CLUB_ID = 992
LEAGUE_ID = 321
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def fetch_url(url):
    result = subprocess.run(
        ["curl", "-s", "-H", f"User-Agent: {USER_AGENT}", url],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        raise Exception(f"curl failed: {result.stderr}")
    return result.stdout


def parse_fixtures():
    """Parse the fixtures page to get match IDs, dates, teams, and ground codes."""
    url = f"{BASE_URL}/fixtures.do?league={LEAGUE_ID}&clubId={CLUB_ID}"
    html = fetch_url(url)

    match = re.search(
        r'<table[^>]*id="schedule-table"[^>]*>(.*?)</table>', html, re.DOTALL
    )
    if not match:
        print("ERROR: Could not find schedule-table")
        return []

    table = match.group(1)
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL)

    matches = []
    for tr in trs[1:]:  # skip header row
        match_ids = re.findall(r"matchId=(\d+)", tr)
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL)
        row = []
        for td in tds:
            clean = re.sub(r"<[^>]+>", " ", td).strip()
            clean = re.sub(r"\s+", " ", clean)
            clean = clean.replace("&nbsp;", "").strip()
            row.append(clean)

        if len(row) >= 10 and match_ids:
            matches.append({
                "match_id": match_ids[0],
                "match_number": row[0],
                "match_type": row[1],
                "date": row[2],
                "team1": row[4],
                "team2": row[5],
            })

    return matches


def extract_field(html, keyword):
    """Extract a field value from the info page given a keyword like 'Location:'."""
    idx = html.find(keyword)
    if idx < 0:
        return ""
    chunk = html[idx:idx + 500]
    # The value is in the next element after the keyword
    clean = re.sub(r"<[^>]+>", "|", chunk)
    clean = clean.replace("&nbsp;", " ")
    parts = [p.strip() for p in clean.split("|") if p.strip()]
    # parts[0] is the keyword itself, parts[1] should be the value
    if len(parts) >= 2:
        return parts[1]
    return ""


def parse_innings_times(html, label):
    """Extract duration, start time, end time for an innings section."""
    idx = html.find(label)
    if idx < 0:
        return "", "", ""
    chunk = html[idx:idx + 300]
    clean = re.sub(r"<[^>]+>", "|", chunk)
    clean = clean.replace("&nbsp;", " ")
    parts = [p.strip() for p in clean.split("|") if p.strip()]
    # parts: [label, duration, start_time end_time, ...]
    duration = ""
    start_time = ""
    end_time = ""
    if len(parts) >= 2:
        duration = parts[1]  # e.g. "61 min"
    if len(parts) >= 3:
        # "10:49 AM 11:50 AM"
        times = re.findall(r"\d{1,2}:\d{2}\s*[AP]M", parts[2])
        if len(times) >= 2:
            start_time = times[0]
            end_time = times[1]
        elif len(times) == 1:
            start_time = times[0]
    return duration, start_time, end_time


def parse_match_info(match_id):
    """Parse the info.do page for a match to get times, ground, overs."""
    url = f"{BASE_URL}/info.do?matchId={match_id}&clubId={CLUB_ID}"
    try:
        html = fetch_url(url)
    except Exception as e:
        print(f"  Error fetching info for {match_id}: {e}")
        return None

    location = extract_field(html, "Location:")
    toss = extract_field(html, "Toss:")
    # Clean up toss - get full toss text
    toss_idx = html.find("Toss:")
    if toss_idx >= 0:
        toss_chunk = html[toss_idx:toss_idx + 500]
        toss_clean = re.sub(r"<[^>]+>", " ", toss_chunk)
        toss_clean = toss_clean.replace("&nbsp;", " ")
        toss_clean = re.sub(r"\s+", " ", toss_clean).strip()
        # Remove "Toss:" prefix
        toss = toss_clean.replace("Toss:", "").strip()
        # Trim at next field boundary or HTML artifacts
        for stopper in ["Player of", "Location:", "1st Innings", "Last Updated", "<th", "<td"]:
            si = toss.find(stopper)
            if si > 0:
                toss = toss[:si].strip()

    inn1_dur, inn1_start, inn1_end = parse_innings_times(html, "1st Innings:")
    inn2_dur, inn2_start, inn2_end = parse_innings_times(html, "2nd Innings:")
    break_dur, break_start, break_end = parse_innings_times(html, "Innings break:")

    # Match start = 1st innings start, Match end = 2nd innings end
    match_start_time = inn1_start
    match_end_time = inn2_end

    # Calculate total duration
    total_duration = ""
    durations = []
    for d in [inn1_dur, break_dur, inn2_dur]:
        m = re.search(r"(\d+)\s*min", d)
        if m:
            durations.append(int(m.group(1)))
    if durations:
        total_minutes = sum(durations)
        total_duration = f"{total_minutes} min"

    # Extract overs from scorecard summary on info page
    overs = re.findall(r"([\d.]+)\s*/\s*([\d.]+)\s*ov", html)
    team1_overs = ""
    team2_overs = ""
    if len(overs) >= 2:
        team1_overs = f"{overs[0][0]}/{overs[0][1]}"
        team2_overs = f"{overs[1][0]}/{overs[1][1]}"
    elif len(overs) == 1:
        team1_overs = f"{overs[0][0]}/{overs[0][1]}"

    return {
        "ground": location,
        "match_start_time": match_start_time,
        "match_end_time": match_end_time,
        "match_duration": total_duration,
        "innings1_duration": inn1_dur,
        "innings1_start": inn1_start,
        "innings1_end": inn1_end,
        "innings_break": break_dur,
        "innings2_duration": inn2_dur,
        "innings2_start": inn2_start,
        "innings2_end": inn2_end,
        "team1_overs": team1_overs,
        "team2_overs": team2_overs,
        "toss": toss,
    }


def main():
    print("Fetching fixtures from ARCL CricClubs...")
    matches = parse_fixtures()
    print(f"Found {len(matches)} matches")

    if not matches:
        return

    fieldnames = [
        "match_id",
        "match_number",
        "match_type",
        "date",
        "team1",
        "team2",
        "ground",
        "match_start_time",
        "match_end_time",
        "match_duration",
        "innings1_duration",
        "innings1_start",
        "innings1_end",
        "innings_break",
        "innings2_duration",
        "innings2_start",
        "innings2_end",
        "team1_overs",
        "team2_overs",
        "toss",
    ]

    empty_info = {k: "" for k in fieldnames if k not in ["match_id", "match_number", "match_type", "date", "team1", "team2"]}

    print("Fetching match info pages...")
    info_results = {}

    def fetch_one(match):
        mid = match["match_id"]
        info = parse_match_info(mid)
        return mid, info

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(fetch_one, m): m for m in matches}
        done = 0
        for future in as_completed(futures):
            done += 1
            mid, info = future.result()
            info_results[mid] = info or empty_info
            if done % 50 == 0:
                print(f"  Progress: {done}/{len(matches)}")

    print(f"Fetched all {len(matches)} match info pages. Writing CSVs...")

    with_result = []
    without_result = []

    for match in matches:
        info = info_results.get(match["match_id"], empty_info)
        row = {**match, **info}
        if row.get("match_start_time"):
            with_result.append(row)
        else:
            without_result.append(row)

    with open("arcl_match_stats.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(with_result)

    with open("arcl_match_stats_without_result.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(without_result)

    print(f"\narcl_match_stats.csv: {len(with_result)} matches with timing data")
    print(f"arcl_match_stats_without_result.csv: {len(without_result)} matches without timing data")
    print("Done!")


if __name__ == "__main__":
    main()
