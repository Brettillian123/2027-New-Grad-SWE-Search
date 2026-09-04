"""Split one board's scan into list-phase vs detail-phase wall time, and measure
how much each of the 8 queries actually contributes."""
import collections, json, time, urllib.request
from ats import UA
import openelig

QUERIES = ["software engineer", "new grad software engineer", "entry level software engineer",
           "associate software engineer", "backend engineer", "software engineer I",
           "university graduate", "early career software"]


def post(base, body):
    req = urllib.request.Request(base + '/jobs', data=json.dumps(body).encode(),
                                 headers={**UA, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


targets = json.load(open('bench_sample.json', encoding='utf-8'))[:6]
list_t = detail_t = 0.0
n_list = n_detail = 0
contrib = collections.Counter()
qcost = collections.Counter()

for t in targets:
    host, tenant, site = t['token'].split('|')
    base = 'https://%s/wday/cxs/%s/%s' % (host, tenant, site)
    seen = set()
    for q in QUERIES:
        t0 = time.time()
        added = 0
        try:
            for off in (0, 20, 40):
                n_list += 1
                d = post(base, {'appliedFacets': {}, 'limit': 20, 'offset': off, 'searchText': q})
                ps = d.get('jobPostings', [])
                for p in ps:
                    ep = p.get('externalPath')
                    if ep and ep not in seen:
                        seen.add(ep)
                        added += 1
                if len(ps) < 20:
                    break
        except Exception:
            pass
        dt_ = time.time() - t0
        list_t += dt_
        qcost[q] += dt_
        contrib[q] += added

print('LIST PHASE   %6.1f s over %d requests  (%.2f s/request)'
      % (list_t, n_list, list_t / max(1, n_list)))
print()
print('what each query CONTRIBUTES that no earlier query already found:')
print('%-34s %8s %8s' % ('query', 'new', 'seconds'))
for q in QUERIES:
    print('%-34s %8d %8.1f' % (q, contrib[q], qcost[q]))
print()
tot = sum(contrib.values())
run = 0
for q in QUERIES:
    run += contrib[q]
    print('  after %-32s cumulative %d/%d (%.0f%%)' % (q, run, tot, 100.0 * run / max(1, tot)))
