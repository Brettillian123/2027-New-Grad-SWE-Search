"""wd2 vs wd4 on the same representative sample. wd4 must be faster AND must not
lose any fresh posting - a speedup that drops results is not a speedup."""
import datetime as dt, json, subprocess, sys, time

CUT = (dt.date.today() - dt.timedelta(days=14)).isoformat()
sample = 'bench_sample.json'
n = len(json.load(open(sample, encoding='utf-8')))


def fresh(p):
    return {j.get('url') for r in json.load(open(p, encoding='utf-8'))
            for j in r.get('jobs', []) if (j.get('opened') or '') >= CUT}


runs = [
    ('wd2  (8 workers, no prefilter)', ['wd2.py', sample, 'b_wd2.json']),
    ('wd4  (16 workers, prefilter)  ', ['wd4.py', sample, 'b_wd4.json']),
    ('wd4  (24 workers, prefilter)  ', ['wd4.py', sample, 'b_wd4b.json', '--workers=24']),
]

res = {}
for tag, cmd in runs:
    t = time.time()
    subprocess.run([sys.executable] + cmd, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    el = time.time() - t
    out = cmd[2]
    f = fresh(out)
    res[tag] = (el, f, out)
    print('%-32s %6.1f s  (%.2f s/board)  %d fresh' % (tag, el, el / n, len(f)))

base_t, base_f, _ = res['wd2  (8 workers, no prefilter)']
print()
for tag, (el, f, _) in res.items():
    if tag.startswith('wd2'):
        continue
    lost = base_f - f
    gained = f - base_f
    print('%s  ->  %.2fx faster, lost %d, gained %d'
          % (tag.strip(), base_t / max(0.01, el), len(lost), len(gained)))
    for u in list(lost)[:5]:
        print('      LOST %s' % (u or '')[:100])

d = json.load(open('b_wd4.json', encoding='utf-8'))
print()
print('detail GETs avoided by the postedOn prefilter: %d'
      % sum(r.get('skipped_stale', 0) for r in d))
