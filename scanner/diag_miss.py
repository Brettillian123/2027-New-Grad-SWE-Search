"""Why did the fast scanner miss those? Was the posting never returned by the
walk, or returned and then dropped by a cap?"""
import datetime as dt, json

CUT = (dt.date.today() - dt.timedelta(days=14)).isoformat()
old = json.load(open('bench_old.json', encoding='utf-8'))
new = json.load(open('bench_new.json', encoding='utf-8'))

newrec = {r['company']: r for r in new}
newurls = {j.get('url') for r in new for j in r.get('jobs', [])}

print('%-22s %6s %6s %6s %6s %8s' % ('board', 'pages', 'fresh', 'cands', 'hits', 'capped'))
for r in new:
    print('%-22s %6d %6d %6d %6d %8s' % (
        r['company'][:22], r.get('pages', 0), r.get('seen', 0),
        r.get('cands', 0), len(r.get('jobs', [])), r.get('capped')))

print()
print('missed postings, by board:')
miss = {}
for r in old:
    for j in r.get('jobs', []):
        if (j.get('opened') or '') >= CUT and j.get('url') not in newurls:
            miss.setdefault(j['company'], []).append(j)
for co, js in miss.items():
    rec = newrec.get(co, {})
    print('  %-22s missed=%-3d  (walk: %d fresh, %d cands, cap=%s)'
          % (co[:22], len(js), rec.get('seen', 0), rec.get('cands', 0), rec.get('capped')))
    for j in js[:3]:
        print('       %-52s %s  %s' % (j['title'][:52], j.get('opened'), j.get('posted_rel')))
