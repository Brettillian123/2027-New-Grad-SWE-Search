"""Is 8 postings in 48 hours plausible, or are we still missing jobs?

Measures the shape of the funnel so the answer is arithmetic rather than a guess.
"""
import datetime as dt, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import geo

TODAY = dt.date.today()
rows = []
for f in ('scan_api.json', 'scan_wd.json', 'scan_new.json', 'scan_newboards.json'):
    if not os.path.exists(f):
        continue
    for r in json.load(open(f, encoding='utf-8')):
        for j in r.get('jobs', []):
            j.setdefault('company', r.get('company'))
            rows.append(j)

print('eligible software postings on file: %d' % len(rows))
print()

for days in (2, 7, 14, 30):
    cut = (TODAY - dt.timedelta(days=days)).isoformat()
    fresh = [j for j in rows if (j.get('opened') or '') >= cut]
    us = [j for j in fresh if not geo.geo(j.get('loc') or '')['foreign_only']
          and geo.geo(j.get('loc') or '')['us']]
    rem = [j for j in us if geo.geo(j.get('loc') or '')['remote']]
    chi = [j for j in us if geo.geo(j.get('loc') or '')['chicago']]
    both = len({id(x) for x in rem} | {id(x) for x in chi})
    print('last %2d days: %5d posted | %5d US | %4d remote | %3d Chicago | %4d either  (%.1f%% of US)'
          % (days, len(fresh), len(us), len(rem), len(chi), both,
             100.0 * both / max(1, len(us))))

print()
cut = (TODAY - dt.timedelta(days=14)).isoformat()
fresh = [j for j in rows if (j.get('opened') or '') >= cut]
us = [j for j in fresh if geo.geo(j.get('loc') or '')['us']
      and not geo.geo(j.get('loc') or '')['foreign_only']]
rem = [j for j in us if geo.geo(j.get('loc') or '')['remote']]
print('THE SHAPE OF IT')
print('  of %d US software postings in the last 14 days, %d are remote-eligible = %.1f%%'
      % (len(us), len(rem), 100.0 * len(rem) / max(1, len(us))))
print('  that rate applied to a 48-hour slice is what produces single digits.')
