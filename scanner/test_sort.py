"""Does an empty Workday search return newest-first? If so the sweep can page
until it passes the 14-day window and stop, instead of running 8 queries x 3
pages against every board."""
import json, re, urllib.request
from ats import UA

REL = re.compile(r'posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)', re.I)


def rel_days(s):
    m = REL.search(s or '')
    if not m:
        return None
    g = m.group(1).lower()
    if g == 'today':
        return 0
    if g == 'yesterday':
        return 1
    return int(m.group(2))


def post(base, body):
    req = urllib.request.Request(base + '/jobs', data=json.dumps(body).encode(),
                                 headers={**UA, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


targets = json.load(open('wd_targets_full.json', encoding='utf-8'))[:5]
for t in targets:
    host, tenant, site = t['token'].split('|')
    base = 'https://%s/wday/cxs/%s/%s' % (host, tenant, site)
    print('=== %s' % t['company'][:40])
    for label, body in (
        ('empty search      ', {'appliedFacets': {}, 'limit': 20, 'offset': 0, 'searchText': ''}),
        ('empty + sort facet', {'appliedFacets': {}, 'limit': 20, 'offset': 0,
                                'searchText': '', 'sortBy': 'POSTING_DATES_DESC'}),
    ):
        try:
            d = post(base, body)
            ps = d.get('jobPostings', [])
            days = [rel_days(p.get('postedOn')) for p in ps]
            days = [x for x in days if x is not None]
            mono = all(days[i] <= days[i + 1] for i in range(len(days) - 1))
            print('   %s total=%-6s first20 days=%s  newest-first=%s'
                  % (label, d.get('total'), days[:8], mono))
        except Exception as e:
            print('   %s FAILED %s %s' % (label, type(e).__name__, str(e)[:50]))
