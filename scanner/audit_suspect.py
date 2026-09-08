"""Two rejection buckets that look wrong:
  1. location is just "United States" / "US" with no city - that usually means remote
  2. location is blank - the gate cannot judge it, so it is dropped unseen
Check whether the DESCRIPTION says remote in either case."""
import datetime as dt, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo


def aa(x):
    return ''.join(c if ord(c) < 128 else '?' for c in str(x))


FRESH = (dt.date.today() - dt.timedelta(days=14)).isoformat()
REMOTE_TXT = re.compile(r'\b(fully remote|100% remote|remote[- ]first|work from home|'
                        r'remote position|remote role|this role is remote|'
                        r'remote \(us|remote-us|us[- ]remote|anywhere in the us)\b', re.I)
COUNTRY_ONLY = re.compile(r'^\s*(united states|usa|u\.s\.|us|united states of america|'
                          r'us national|nationwide|multiple locations|various)\s*$', re.I)

rows = []
for f in ('scan_api.json', 'scan_wd.json', 'scan_new.json'):
    if not os.path.exists(f):
        continue
    for r in json.load(open(f, encoding='utf-8')):
        for j in r.get('jobs', []):
            j.setdefault('company', r.get('company'))
            rows.append(j)
fresh = [j for j in rows if (j.get('opened') or '') >= FRESH]

country_only, blanks = [], []
for j in fresh:
    loc = (j.get('loc') or '').strip()
    g = geo.geo(loc)
    if g['remote'] or g['chicago']:
        continue
    if COUNTRY_ONLY.match(loc):
        country_only.append(j)
    elif not loc:
        blanks.append(j)

for label, group in (('LOCATION IS COUNTRY-ONLY', country_only), ('LOCATION IS BLANK', blanks)):
    print('=== %s: %d postings ===' % (label, len(group)))
    hit = [j for j in group if REMOTE_TXT.search(j.get('desc') or '')]
    print('    description says remote: %d' % len(hit))
    for j in hit[:12]:
        m = REMOTE_TXT.search(j.get('desc') or '')
        print('      %-24s %-44s loc=%-16s "%s"'
              % (aa(j.get('company'))[:24], aa(j.get('title'))[:44],
                 aa(j.get('loc'))[:16], aa(m.group(0))))
    print()
