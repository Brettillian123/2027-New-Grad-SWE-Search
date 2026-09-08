"""Find the real concurrency ceiling.

Each request costs ~0.4 s of server time, so throughput is purely how many we
keep in flight. Raising outer workers 16 -> 24 made the sweep SLOWER, which is
either noise or a real saturation point. This measures it directly: fire the same
120 requests spread across many hosts at increasing concurrency.
"""
import json, time, urllib.request, concurrent.futures as cf
from ats import UA

targets = json.load(open('wd_targets_full.json', encoding='utf-8'))[:40]
jobs = []
for t in targets:
    try:
        host, tenant, site = t['token'].split('|')
    except ValueError:
        continue
    url = 'https://%s/wday/cxs/%s/%s/jobs' % (host, tenant, site)
    for q in ('software engineer', 'backend engineer', 'data engineer'):
        jobs.append((url, {'appliedFacets': {}, 'limit': 20, 'offset': 0, 'searchText': q}))
jobs = jobs[:120]


def one(a):
    url, body = a
    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                     headers={**UA, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=25) as r:
            r.read()
        return True
    except Exception:
        return False


print('%d requests across %d distinct hosts' % (len(jobs), len(targets)))
print()
print('%-10s %8s %10s %8s' % ('workers', 'seconds', 'req/s', 'errors'))
for w in (8, 16, 32, 48, 64):
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=w) as ex:
        ok = list(ex.map(one, jobs))
    el = time.time() - t0
    print('%-10d %8.1f %10.1f %8d' % (w, el, len(jobs) / el, ok.count(False)))
