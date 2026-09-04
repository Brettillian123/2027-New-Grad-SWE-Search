"""Sweep the five newly-covered ATS platforms through the same gates as everything
else: eligibility4 on the title, then the caller applies date / geo / pay.

Usage: python sweep_new.py <out.json>
"""
import json, os, sys, importlib, concurrent.futures as cf
import openelig

PLATFORMS = [
    ('icims', 'tok_icims.json', 'fetch_icims'),
    ('successfactors', 'tok_successfactors.json', 'fetch_successfactors'),
    ('eightfold', 'tok_eightfold.json', 'fetch_eightfold'),
    ('taleo', 'tok_taleo.json', 'fetch_taleo'),
    ('jobvite', 'tok_jobvite.json', 'fetch_jobvite'),
]


def load(mod):
    try:
        m = importlib.import_module(mod)
        return getattr(m, 'fetch', None)
    except Exception as e:
        print('  cannot import %s: %s %s' % (mod, type(e).__name__, str(e)[:70]), file=sys.stderr)
        return None


def scan_one(ats, fetch, company, token):
    try:
        jobs = fetch(token)
    except Exception as e:
        return dict(company=company, ats=ats, token=token,
                    error='%s: %s' % (type(e).__name__, str(e)[:90]), jobs=[])
    hits = []
    for j in jobs or []:
        j.setdefault('company', company)
        j['ats'] = ats
        tier, floor, stretch = openelig.eligibility4(j)
        if not tier:
            continue
        j.update(tier=tier, floor=floor, stretch=stretch)
        try:
            import geo as _geo
            j['remote_body'] = _geo.remote_in_text(j.get('desc') or '')
        except Exception:
            pass
        j['desc'] = (j.get('desc') or '')[:1500]
        hits.append(j)
    return dict(company=company, ats=ats, token=token, total=len(jobs or []), jobs=hits)


out, done = [], 0
tasks = []
for ats, tokfile, mod in PLATFORMS:
    if not os.path.exists(tokfile):
        continue
    fetch = load(mod)
    if not fetch:
        continue
    toks = json.load(open(tokfile, encoding='utf-8'))
    toks = [t for t in toks if t.get('reachable') is not False]
    for t in toks:
        tok = t.get('token') or t.get('id') or t.get('slug')
        if tok:
            tasks.append((ats, fetch, t.get('company') or tok, tok))
    print('%-16s queued %d boards' % (ats, len(toks)), file=sys.stderr)

print('TOTAL %d boards' % len(tasks), file=sys.stderr)

W = 24
for _a in sys.argv[1:]:
    if _a.startswith("--workers="): W = int(_a.split("=")[1])
with cf.ThreadPoolExecutor(max_workers=W) as ex:
    futs = [ex.submit(scan_one, *t) for t in tasks]
    for f in cf.as_completed(futs):
        done += 1
        try:
            r = f.result()
        except Exception as e:
            print('FATAL %s' % str(e)[:70], file=sys.stderr)
            continue
        out.append(r)
        if r['jobs'] or done % 25 == 0:
            print('[%4d/%4d] %-14s %-26s %s' % (
                done, len(tasks), r['ats'], r['company'][:26],
                r.get('error') or '%d hits / %d posts' % (len(r['jobs']), r.get('total', 0))),
                file=sys.stderr)
        if done % 40 == 0:
            json.dump(out, open(sys.argv[1], 'w'))

json.dump(out, open(sys.argv[1], 'w'), indent=1)
tot = sum(len(r['jobs']) for r in out)
ok = sum(1 for r in out if not r.get('error'))
print('\nDONE boards=%d reachable=%d eligible=%d' % (len(out), ok, tot), file=sys.stderr)
