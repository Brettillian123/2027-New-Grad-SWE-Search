"""Audit the geography gate. It rejects 1,769 of ~1,863 fresh postings, so if
anything is being lost it is almost certainly here."""
import collections, datetime as dt, json, os, sys


def aa(x):
    return ''.join(c if ord(c) < 128 else '?' for c in str(x))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo

FRESH = (dt.date.today() - dt.timedelta(days=14)).isoformat()

rows = []
for f in ('scan_api.json', 'scan_wd.json', 'scan_new.json'):
    if not os.path.exists(f):
        continue
    for r in json.load(open(f, encoding='utf-8')):
        for j in r.get('jobs', []):
            j.setdefault('company', r.get('company'))
            rows.append(j)

fresh = [j for j in rows if (j.get('opened') or '') >= FRESH]
print('fresh postings: %d' % len(fresh))

notus, notloc, kept, blank = [], [], [], []
for j in fresh:
    loc = j.get('loc') or ''
    g = geo.geo(loc)
    if not loc.strip():
        blank.append(j)
    if g['foreign_only'] or not g['us']:
        notus.append(j)
    elif not (g['remote'] or g['chicago']):
        notloc.append(j)
    else:
        kept.append(j)

print('  kept              %5d' % len(kept))
print('  rejected not-US   %5d' % len(notus))
print('  rejected not r/c  %5d' % len(notloc))
print('  BLANK location    %5d   <-- these cannot be judged at all' % len(blank))
print()

print('=== most common locations rejected as NOT US ===')
c = collections.Counter((j.get('loc') or '(blank)')[:52] for j in notus)
for k, v in c.most_common(22):
    print('  %5d  %s' % (v, aa(k)))
print()
print('=== most common locations rejected as not remote/Chicago ===')
c = collections.Counter((j.get('loc') or '(blank)')[:52] for j in notloc)
for k, v in c.most_common(22):
    print('  %5d  %s' % (v, aa(k)))
