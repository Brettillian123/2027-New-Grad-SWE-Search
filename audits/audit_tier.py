"""Does board tiering lose postings?

Compare today's TIERED api scan (927 boards) against the FULL api sweep run
earlier the same day (2048 boards). Same day, same window - any fresh posting in
the full sweep that is missing from the tiered one is a job the optimisation cost
Brett."""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo


def aa(x):
    return ''.join(c if ord(c) < 128 else '?' for c in str(x))


FRESH = (dt.date.today() - dt.timedelta(days=14)).isoformat()
FULL = (r"C:\Users\Brett\AppData\Local\Temp\claude"
        r"\C--Users-Brett-OneDrive-Documents-JobSearch"
        r"\47409783-7799-4744-bcb8-aab5b033e227\scratchpad\scan\fresh_api.json")


def collect(path):
    out = {}
    if not os.path.exists(path):
        return out
    for r in json.load(open(path, encoding='utf-8')):
        for j in r.get('jobs', []):
            j.setdefault('company', r.get('company'))
            if (j.get('opened') or '') < FRESH:
                continue
            g = geo.geo(j.get('loc') or '')
            if g['foreign_only'] or not g['us']:
                continue
            if not (g['remote'] or g['chicago']):
                continue
            out[j.get('url') or (j['company'], j['title'])] = j
    return out


full = collect(FULL)
tier = collect('scan_api.json')
print('full sweep  (2048 boards): %d fresh remote/Chicago postings' % len(full))
print('tiered scan (927 boards) : %d' % len(tier))
missed = {k: v for k, v in full.items() if k not in tier}
print()
print('LOST TO TIERING: %d' % len(missed))
for k, j in list(missed.items())[:25]:
    print('   %-26s %-46s %s  %s'
          % (aa(j.get('company'))[:26], aa(j.get('title'))[:46],
             j.get('opened'), aa(j.get('loc'))[:22]))
