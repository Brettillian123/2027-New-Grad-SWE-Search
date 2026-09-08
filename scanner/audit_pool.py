"""How many company NAMES do we already know but have no board token for?

Those are free expansion: an ATS token is usually the company name lowercased and
stripped, so every known name is a cheap probe against 5 endpoints."""
import json, os, re, sys


def aa(x):
    return ''.join(c if ord(c) < 128 else '?' for c in str(x))


def slug(n):
    return re.sub(r'[^a-z0-9]', '', (n or '').lower())


have = set()
for f in ('rescan_nonwd.json', 'wd_targets_full.json'):
    if not os.path.exists(f):
        continue
    for t in json.load(open(f, encoding='utf-8')):
        have.add(slug(t.get('company')))
        tok = (t.get('token') or '')
        have.add(slug(tok.split('|')[0] if '|' in tok else tok))

SCRATCH = (r"C:\Users\Brett\AppData\Local\Temp\claude"
           r"\C--Users-Brett-OneDrive-Documents-JobSearch"
           r"\47409783-7799-4744-bcb8-aab5b033e227\scratchpad\scan")

names = {}
for fn in ('simplify.json', 'simplify_all.json', 'himalayas_names.json',
           'harvest_names.json', 'master_all.json', 'wf1_companies.json'):
    p = os.path.join(SCRATCH, fn)
    if not os.path.exists(p):
        continue
    try:
        d = json.load(open(p, encoding='utf-8'))
    except Exception:
        continue
    rows = d if isinstance(d, list) else (d.get('data') or [])
    n = 0
    for r in rows:
        if not isinstance(r, dict):
            if isinstance(r, str):
                s = slug(r)
                if s and s not in have and s not in names:
                    names[s] = r
                    n += 1
            continue
        for k in ('company', 'company_name', 'employer', 'org', 'name'):
            v = r.get(k)
            if isinstance(v, str) and v.strip():
                s = slug(v)
                if s and s not in have and s not in names:
                    names[s] = v.strip()
                    n += 1
                break
    print('%-24s +%d new names' % (fn, n))

print()
print('companies we already have a board for : %d' % len({h for h in have if h}))
print('KNOWN NAMES WITH NO BOARD TOKEN       : %d' % len(names))
print()
print('sample:', ', '.join(aa(v) for v in list(names.values())[:18]))
json.dump([{'company': v, 'slug': k} for k, v in names.items()],
          open('probe_names.json', 'w'), indent=1)
print()
print('wrote probe_names.json')
