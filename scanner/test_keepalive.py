"""Is the per-request cost TLS handshake rather than server time?

Every list request for a board goes to the SAME host, but urllib.urlopen opens a
fresh connection each time. If keep-alive collapses the cost, connection reuse is
the optimisation - not query pruning, not more workers.
"""
import json, time, urllib.request
from ats import UA

try:
    import requests
    HAVE_REQ = True
except ImportError:
    HAVE_REQ = False

t = json.load(open('bench_sample.json', encoding='utf-8'))[0]
host, tenant, site = t['token'].split('|')
url = 'https://%s/wday/cxs/%s/%s/jobs' % (host, tenant, site)
body = {'appliedFacets': {}, 'limit': 20, 'offset': 0, 'searchText': 'software engineer'}
N = 8

print('board: %s' % t['company'])
print('requests library available: %s' % HAVE_REQ)
print()

# --- current approach: a fresh connection per call
t0 = time.time()
for i in range(N):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={**UA, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=25) as r:
        r.read()
a = time.time() - t0
print('urllib, new connection each  %6.2f s  (%.3f s/req)' % (a, a / N))

# --- keep-alive
if HAVE_REQ:
    s = requests.Session()
    s.headers.update({**UA, 'Content-Type': 'application/json'})
    s.post(url, json=body, timeout=25)            # warm the connection
    t0 = time.time()
    for i in range(N):
        s.post(url, json=body, timeout=25)
    b = time.time() - t0
    print('requests.Session keep-alive  %6.2f s  (%.3f s/req)' % (b, b / N))
    print()
    print('speedup from connection reuse: %.1fx' % (a / max(0.01, b)))
else:
    print('requests not installed - run: pip install requests')
