"""The Empower miss exposes a second bug class.

Its structured location is "Greenwood Village, Colorado" but the posting says
"Workplace flexibility: Remote - Nationwide". The geo gate only reads the
location field, so a remote role whose location names an office is rejected.

Earlier I audited blank and country-only locations. I never checked the big
bucket: locations that name a CITY while the body says the role is remote.
"""
import datetime as dt, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo


def aa(x):
    return ''.join(c if ord(c) < 128 else '?' for c in str(x))


FRESH = (dt.date.today() - dt.timedelta(days=14)).isoformat()

# Deliberately strict: phrases that state the ROLE is remote, not boilerplate
# like "our remote-friendly culture" or an EEO paragraph.
STRONG = re.compile(
    r'(remote\s*[-–—:]\s*nationwide|fully\s+remote|100%\s+remote|'
    r'this\s+(role|position)\s+is\s+(fully\s+)?remote|'
    r'remote\s*\(\s*(us|united states|nationwide|anywhere)|'
    r'work\s+location:\s*remote|workplace\s+flexibility[:\s]*remote|'
    r'location:\s*remote|remote\s+within\s+the\s+(us|united states)|'
    r'anywhere\s+in\s+the\s+(us|united states)|us[-\s]remote|remote[-\s]us\b)', re.I)

rows = []
for f in ('scan_api.json', 'scan_wd.json', 'scan_new.json', 'scan_newboards.json'):
    if not os.path.exists(f):
        continue
    for r in json.load(open(f, encoding='utf-8')):
        for j in r.get('jobs', []):
            j.setdefault('company', r.get('company'))
            rows.append(j)

fresh = [j for j in rows if (j.get('opened') or '') >= FRESH]
rejected = []
for j in fresh:
    g = geo.geo(j.get('loc') or '')
    if g['foreign_only'] or not g['us']:
        continue
    if g['remote'] or g['chicago']:
        continue
    rejected.append(j)

hits = [j for j in rejected if STRONG.search(j.get('desc') or '')]
print('fresh US postings rejected as not remote/Chicago: %d' % len(rejected))
print('  ...whose DESCRIPTION states the role is remote: %d  (%.0f%%)'
      % (len(hits), 100.0 * len(hits) / max(1, len(rejected))))
print()
print('NOTE: descriptions are truncated to 1500 chars at collection, so this is a')
print('FLOOR. The real number is higher.')
print()
for j in hits[:25]:
    m = STRONG.search(j.get('desc') or '')
    print('  %-24s %-42s loc=%-22s "%s"'
          % (aa(j.get('company'))[:24], aa(j.get('title'))[:42],
             aa(j.get('loc'))[:22], aa(m.group(0))[:34]))
