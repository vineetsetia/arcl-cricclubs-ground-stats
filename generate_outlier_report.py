import csv
from collections import defaultdict
from fpdf import FPDF

# --- Data loading and processing ---
with open('arcl_match_stats.csv') as f:
    rows = list(csv.DictReader(f))

def safe_int(s):
    s = s.replace(' min', '').strip()
    return int(s) if s else 0

def parse_time(t):
    t = t.strip()
    if not t:
        return 0
    parts = t.replace(':', ' ').split()
    h, m = int(parts[0]), int(parts[1].replace('AM', '').replace('PM', '').strip())
    ampm = 'PM' if 'PM' in t else 'AM'
    if ampm == 'PM' and h != 12:
        h += 12
    if ampm == 'AM' and h == 12:
        h = 0
    return h * 60 + m

def fmt_time(mins):
    h = mins // 60
    m = mins % 60
    ampm = 'AM' if h < 12 else 'PM'
    if h == 0:
        h = 12
    elif h > 12:
        h -= 12
    return f'{h}:{m:02d} {ampm}'

def scheduled_start(actual_mins):
    return (actual_mins // 30) * 30

# Determine last match of day per ground
matches_by_day_ground = defaultdict(list)
for r in rows:
    key = (r['date'], r['ground'])
    matches_by_day_ground[key].append(r)

last_match_ids = set()
for key, matches in matches_by_day_ground.items():
    latest = max(matches, key=lambda x: parse_time(x['match_start_time']))
    last_match_ids.add(latest['match_id'])

# Filter outliers (>140 min)
long = []
for r in rows:
    dur = safe_int(r['match_duration'])
    if dur > 140:
        brk = safe_int(r['innings_break'])
        actual = parse_time(r['match_start_time'])
        sched = scheduled_start(actual)
        delay = actual - sched
        is_last = 'Yes' if r['match_id'] in last_match_ids else 'No'
        total_delay = delay + brk
        # Get max overs played in either innings
        max_overs = ''
        try:
            t1b = float(r['team1_overs'].split('/')[0])
            t2b = float(r['team2_overs'].split('/')[0])
            max_ov = max(t1b, t2b)
            # Format: show as-is (e.g. 16.0, 15.2)
            max_overs = r['team1_overs'].split('/')[0] if t1b >= t2b else r['team2_overs'].split('/')[0]
        except:
            pass

        long.append({
            'dur': dur,
            'break': brk,
            'actual': r['match_start_time'].strip(),
            'sched': fmt_time(sched),
            'delay': delay,
            'total_delay': total_delay,
            'team1': r['team1'],
            'team2': r['team2'],
            'date': r['date'],
            'ground': r['ground'],
            'last': is_last,
            'match_id': r['match_id'],
            'max_overs': max_overs,
            'team1_overs': r['team1_overs'],
            'team2_overs': r['team2_overs'],
        })

long.sort(key=lambda x: x['dur'], reverse=True)

# --- PDF Generation ---
class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 14)
        self.cell(0, 10, 'ARCL Match Duration Outlier Report (>140 min)', align='C', new_x='LMARGIN', new_y='NEXT')
        self.set_font('Helvetica', '', 9)
        self.cell(0, 6, f'Total outlier matches: {len(long)} out of {len(rows)} ({len(long)*100//len(rows)}%)', align='C', new_x='LMARGIN', new_y='NEXT')
        self.ln(2)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}', align='C')

pdf = PDF(orientation='L', format='A4')
pdf.alias_nb_pages()
pdf.set_auto_page_break(auto=True, margin=20)

# --- Summary Page ---
pdf.add_page()
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, 'Summary Statistics', new_x='LMARGIN', new_y='NEXT')
pdf.ln(2)

delays = [x['delay'] for x in long]
brks = [x['break'] for x in long]
total_delays = [x['total_delay'] for x in long]
last_count = sum(1 for x in long if x['last'] == 'Yes')

pdf.set_font('Helvetica', '', 10)
stats = [
    ('Total outlier matches', str(len(long))),
    ('Last match of the day', f'{last_count} ({last_count*100//len(long)}%)'),
    ('Not last match of the day', f'{len(long)-last_count} ({(len(long)-last_count)*100//len(long)}%)'),
    ('', ''),
    ('Avg start delay', f'{sum(delays)/len(delays):.1f} min'),
    ('Max start delay', f'{max(delays)} min'),
    ('Min start delay', f'{min(delays)} min'),
    ('', ''),
    ('Avg innings break', f'{sum(brks)/len(brks):.1f} min'),
    ('Max innings break', f'{max(brks)} min'),
    ('Min innings break', f'{min(brks)} min'),
    ('', ''),
    ('Avg total delay (start + break)', f'{sum(total_delays)/len(total_delays):.1f} min'),
    ('Max total delay (start + break)', f'{max(total_delays)} min'),
    ('', ''),
    ('Matches with full 16 overs (at least 1 inn)', f'{sum(1 for x in long if x["max_overs"] == "16.0")} ({sum(1 for x in long if x["max_overs"] == "16.0")*100//len(long)}%)'),
]
for label, val in stats:
    if not label:
        pdf.ln(2)
        continue
    pdf.set_font('Helvetica', 'B', 10)
    pdf.cell(80, 6, label, new_x='RIGHT')
    pdf.set_font('Helvetica', '', 10)
    pdf.cell(50, 6, val, new_x='LMARGIN', new_y='NEXT')

# Ground breakdown
pdf.ln(4)
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, 'Grounds with Most Outlier Matches', new_x='LMARGIN', new_y='NEXT')
pdf.ln(2)

from collections import Counter
gc = Counter(x['ground'] for x in long)

pdf.set_font('Helvetica', 'B', 9)
pdf.set_fill_color(41, 128, 185)
pdf.set_text_color(255, 255, 255)
pdf.cell(130, 7, 'Ground', border=1, fill=True, new_x='RIGHT')
pdf.cell(30, 7, 'Matches', border=1, fill=True, align='C', new_x='RIGHT')
pdf.cell(40, 7, 'Avg Delay', border=1, fill=True, align='C', new_x='RIGHT')
pdf.cell(40, 7, 'Avg Break', border=1, fill=True, align='C', new_x='RIGHT')
pdf.cell(40, 7, 'Avg Total Delay', border=1, fill=True, align='C', new_x='LMARGIN', new_y='NEXT')
pdf.set_text_color(0, 0, 0)

for ground, count in gc.most_common(15):
    g_matches = [x for x in long if x['ground'] == ground]
    avg_delay = sum(x['delay'] for x in g_matches) / len(g_matches)
    avg_brk = sum(x['break'] for x in g_matches) / len(g_matches)
    avg_total = sum(x['total_delay'] for x in g_matches) / len(g_matches)
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(130, 6, ground[:60], border=1, new_x='RIGHT')
    pdf.cell(30, 6, str(count), border=1, align='C', new_x='RIGHT')
    pdf.cell(40, 6, f'{avg_delay:.0f} min', border=1, align='C', new_x='RIGHT')
    pdf.cell(40, 6, f'{avg_brk:.0f} min', border=1, align='C', new_x='RIGHT')
    pdf.cell(40, 6, f'{avg_total:.0f} min', border=1, align='C', new_x='LMARGIN', new_y='NEXT')

# --- Detail Table ---
pdf.add_page()
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, 'All Outlier Matches (>140 min) - Sorted by Duration', new_x='LMARGIN', new_y='NEXT')
pdf.ln(2)

# Column widths
col_w = {
    '#': 8,
    'Dur': 12,
    'Break': 13,
    'Delay': 13,
    'Total': 13,
    'Sched': 17,
    'Actual': 17,
    'Match': 68,
    'Date': 22,
    'Ground': 55,
    'Last': 12,
    'Max Ov': 14,
}

# Header row
pdf.set_font('Helvetica', 'B', 7)
pdf.set_fill_color(41, 128, 185)
pdf.set_text_color(255, 255, 255)
headers = ['#', 'Dur', 'Break', 'Delay', 'Total', 'Sched', 'Actual', 'Match', 'Date', 'Ground', 'Last', 'Max Ov']
for h in headers:
    pdf.cell(col_w[h], 7, h, border=1, fill=True, align='C', new_x='RIGHT')
pdf.ln()
pdf.set_text_color(0, 0, 0)

# Data rows
for i, m in enumerate(long, 1):
    # Alternate row colors
    if i % 2 == 0:
        pdf.set_fill_color(235, 245, 251)
        fill = True
    else:
        pdf.set_fill_color(255, 255, 255)
        fill = True

    # Highlight extreme outliers (>170)
    if m['dur'] > 170:
        pdf.set_fill_color(255, 200, 200)
        fill = True

    pdf.set_font('Helvetica', '', 7)
    match_str = f"{m['team1']} vs {m['team2']}"

    pdf.cell(col_w['#'], 6, str(i), border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Dur'], 6, f"{m['dur']}", border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Break'], 6, f"{m['break']} min", border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Delay'], 6, f"{m['delay']} min", border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Total'], 6, f"{m['total_delay']} min", border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Sched'], 6, m['sched'], border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Actual'], 6, m['actual'], border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Match'], 6, match_str[:38], border=1, fill=fill, new_x='RIGHT')
    pdf.cell(col_w['Date'], 6, m['date'], border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Ground'], 6, m['ground'][:28], border=1, fill=fill, new_x='RIGHT')
    pdf.cell(col_w['Last'], 6, m['last'], border=1, fill=fill, align='C', new_x='RIGHT')
    pdf.cell(col_w['Max Ov'], 6, m['max_overs'], border=1, fill=fill, align='C', new_x='LMARGIN', new_y='NEXT')

# --- CricClubs URLs page ---
pdf.add_page()
pdf.set_font('Helvetica', 'B', 12)
pdf.cell(0, 8, 'CricClubs Scorecard URLs', new_x='LMARGIN', new_y='NEXT')
pdf.set_font('Helvetica', '', 8)
pdf.cell(0, 5, 'Use these links to verify if scoring was closed on time or left open after match ended.', new_x='LMARGIN', new_y='NEXT')
pdf.ln(3)

pdf.set_font('Helvetica', 'B', 7)
pdf.set_fill_color(41, 128, 185)
pdf.set_text_color(255, 255, 255)
pdf.cell(8, 7, '#', border=1, fill=True, align='C', new_x='RIGHT')
pdf.cell(12, 7, 'Dur', border=1, fill=True, align='C', new_x='RIGHT')
pdf.cell(75, 7, 'Match', border=1, fill=True, new_x='RIGHT')
pdf.cell(22, 7, 'Date', border=1, fill=True, align='C', new_x='RIGHT')
pdf.cell(150, 7, 'CricClubs URL', border=1, fill=True, new_x='LMARGIN', new_y='NEXT')
pdf.set_text_color(0, 0, 0)

for i, m in enumerate(long, 1):
    if i % 2 == 0:
        pdf.set_fill_color(235, 245, 251)
    else:
        pdf.set_fill_color(255, 255, 255)

    if m['dur'] > 170:
        pdf.set_fill_color(255, 200, 200)

    url = f"https://www.cricclubs.com/ARCL/viewScorecard.do?matchId={m['match_id']}&clubId=992"
    match_str = f"{m['team1']} vs {m['team2']}"
    pdf.set_font('Helvetica', '', 7)
    pdf.cell(8, 5, str(i), border=1, fill=True, align='C', new_x='RIGHT')
    pdf.cell(12, 5, str(m['dur']), border=1, fill=True, align='C', new_x='RIGHT')
    pdf.cell(75, 5, match_str[:40], border=1, fill=True, new_x='RIGHT')
    pdf.cell(22, 5, m['date'], border=1, fill=True, align='C', new_x='RIGHT')
    pdf.set_text_color(0, 0, 200)
    pdf.cell(150, 5, url, border=1, fill=True, link=url, new_x='LMARGIN', new_y='NEXT')
    pdf.set_text_color(0, 0, 0)

output_path = 'arcl_outlier_matches_report_v2.pdf'
pdf.output(output_path)
print(f'PDF saved to {output_path}')
