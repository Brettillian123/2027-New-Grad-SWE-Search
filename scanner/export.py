"""Export the final target list to CSV for Brett."""
import json, csv, os

OUT = r"C:\Users\Brett\OneDrive\Documents\JobSearch"

F = json.load(open('final.json'))


def band(r):
    if r['smin'] and r['smax']:
        if r['smin'] == r['smax']:
            return '$%dk' % (r['smax'] // 1000)
        return '$%dk-$%dk' % (r['smin'] // 1000, r['smax'] // 1000)
    if r.get('est_base'):
        return r['est_base']
    return ''


def geo_label(r):
    bits = []
    if r['chicago']:
        bits.append('Chicago')
    if r['remote']:
        bits.append('Remote')
    return ' / '.join(bits) or (r.get('loc') or '')[:40]


def tier(r):
    if r['status'] == 'LIVE' and r['in_window']:
        return '1 - Live, opened in window'
    if r['status'] == 'LIVE':
        return '2 - Live now (opened earlier, still accepting)'
    return '3 - Opens by Sept 20 - watch'


rows = []
for i, r in enumerate(F, 1):
    rows.append({
        'Rank': i,
        'Company': r['company'],
        'Tier': tier(r),
        'Role (representative)': r['title'],
        'Location': geo_label(r),
        'Base salary (verified where shown)': band(r),
        'Date opened': r['opened'] or '',
        'Open roles found': r['n_roles'],
        'AI / automation': 'Yes' if r['ai'] else '',
        'Apply / watch link': r['url'],
        'Why it fits Brett': r['why'],
        'Date evidence': r.get('evidence', '')[:300],
        'Source': r['source'],
    })

os.makedirs(OUT, exist_ok=True)
p = os.path.join(OUT, 'newgrad_2027_targets.csv')
with open(p, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print('wrote', p, len(rows), 'companies')
