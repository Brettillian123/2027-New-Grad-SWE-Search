"""Benchmark on a REPRESENTATIVE sample, not the head of the file.

wd_targets_full.json is ordered by how often a board appeared in the harvest, so
its first rows are Boeing, RTX, Northrop, NVIDIA - the largest boards in the set
and the worst case for a date-walk. Sampling evenly across the file is the only
way to know which scanner is actually faster for a typical run.
"""
import json, subprocess, sys, time

targets = json.load(open('wd_targets_full.json', encoding='utf-8'))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 24
step = max(1, len(targets) // N)
sample = targets[::step][:N]
json.dump(sample, open('bench_sample.json', 'w'), indent=1)

print('sampled %d boards evenly across %d (every %dth)' % (len(sample), len(targets), step))
print('sizes range from position 0 to %d in the frequency-ordered file' % (step * (len(sample) - 1)))
print()

res = {}
for tag, script, out in (('wd2 (keyword queries)', 'wd2.py', 'fair_old.json'),
                         ('wd3 (date walk)', 'wd3.py', 'fair_new.json')):
    t = time.time()
    subprocess.run([sys.executable, script, 'bench_sample.json', out],
                   stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    el = time.time() - t
    d = json.load(open(out, encoding='utf-8'))
    hits = sum(len(r.get('jobs', [])) for r in d)
    res[tag] = (el, hits, out)
    print('%-24s %6.1f s  (%.2f s/board)  %d raw hits' % (tag, el, el / len(sample), hits))

print()
import datetime as dt
CUT = (dt.date.today() - dt.timedelta(days=14)).isoformat()


def fresh(p):
    return {j.get('url') for r in json.load(open(p, encoding='utf-8'))
            for j in r.get('jobs', []) if (j.get('opened') or '') >= CUT}


a, b = fresh('fair_old.json'), fresh('fair_new.json')
print('FRESH postings (the only ones that reach the board)')
print('  wd2 %d   wd3 %d   wd3-only %d   wd2-only %d'
      % (len(a), len(b), len(b - a), len(a - b)))
speed = res['wd2 (keyword queries)'][0] / max(0.01, res['wd3 (date walk)'][0])
print()
print('wd3 is %.2fx the speed of wd2 on a representative sample' % speed)
