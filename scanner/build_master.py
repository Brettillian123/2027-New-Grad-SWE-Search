"""Rebuild master_all.json from every cached source, one corpus file at a time
so we never hold two multi-hundred-MB corpora in memory at once."""
import json, os, re, gc
import ats, sal
from geo import geo

rows = []


def eat_corpus(path):
    if not os.path.exists(path):
        return 0
    data = json.load(open(path))
    n = 0
    for c in data:
        r = ats.classify(c)
        if not r:
            continue
        lo, hi = r.get('smin'), r.get('smax')
        if not lo:
            lo, hi = sal.extract(c.get('desc') or '')
        rows.append(dict(company=c.get('company'), src=c.get('_ats'), title=r['title'],
                         loc=r['loc'], opened=r['opened'], url=r['url'], tier=r['tier'],
                         frontend=r['frontend'], ai=r['ai'], smin=lo, smax=hi,
                         **geo(r['loc'] or '')))
        n += 1
    del data
    gc.collect()
    return n


for f in ('corpus_all.json', 'corpus4.json'):
    print(f, '->', eat_corpus(f), 'classified')

for f in ('wd_results2.json', 'wd_results3.json'):
    if not os.path.exists(f):
        continue
    for R in json.load(open(f)):
        for j in R['jobs']:
            if not ats.classify(j):
                continue
            lo, hi = sal.extract(j.get('desc') or '')
            rows.append(dict(company=R['company'], src='workday', title=j['title'],
                             loc=j['loc'], opened=j['opened'], url=j['url'], tier=j['tier'],
                             frontend=j['frontend'], ai=j['ai'], smin=lo, smax=hi,
                             **geo(j['loc'] or '')))

if os.path.exists('amazon_hits.json'):
    import datetime
    for h in json.load(open('amazon_hits.json')):
        d = ''
        try:
            d = datetime.datetime.strptime(' '.join(h['posted'].split()),
                                           '%B %d, %Y').strftime('%Y-%m-%d')
        except Exception:
            pass
        rows.append(dict(company='Amazon', src='amazon', title=h['title'], loc=h['loc'],
                         opened=d, url=h['url'], tier='A', frontend=False, ai=True,
                         smin=None, smax=None, **geo(h['loc'])))


def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


seen, out = set(), []
for r in rows:
    k = (norm(str(r['company'])), norm(r['title']), r['loc'][:20])
    if k in seen:
        continue
    seen.add(k)
    out.append(r)

json.dump(out, open('master_all.json', 'w'), indent=1)
print('master postings:', len(out))
