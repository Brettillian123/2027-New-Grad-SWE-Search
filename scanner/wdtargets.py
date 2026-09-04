"""Mine Workday host|tenant|site triples out of everything already collected.

The original scan probed 308 guessed Workday tenants and kept 22 companies. These
triples are real URLs that appeared in harvested postings, so they need no
guessing at all -- the coverage gap was never a discovery problem, it was that
nothing ever read them back out.
"""
import json, os, re, sys, collections

PAT = re.compile(r'https?://([a-z0-9][a-z0-9-]*)\.(wd\d+)\.myworkdayjobs\.com'
                 r'(?:/[a-z]{2}-[A-Z]{2})?/([A-Za-z0-9_\-]+)', re.I)

SKIP_SITE = {'en-US', 'en-GB', 'fr-CA', 'es-ES', 'de-DE', 'ja-JP', 'zh-CN',
             'en-CA', 'pt-BR', 'it-IT', 'nl-NL', 'ko-KR'}

trip = collections.Counter()
names = {}


def feed(blob, name_hint=None):
    for m in PAT.finditer(blob):
        host_t, pod, site = m.group(1), m.group(2), m.group(3)
        if site in SKIP_SITE:
            continue
        key = ('%s.%s.myworkdayjobs.com' % (host_t, pod), host_t, site)
        trip[key] += 1
        if name_hint and key not in names:
            names[key] = name_hint


src = sys.argv[1:] or ['simplify.json']
for f in src:
    if not os.path.exists(f):
        print('skip (missing):', f, file=sys.stderr)
        continue
    try:
        d = json.load(open(f, encoding='utf-8'))
    except Exception as e:
        print('skip (unreadable):', f, type(e).__name__, file=sys.stderr)
        continue
    rows = d if isinstance(d, list) else (d.get('data') or d.get('jobs') or [])
    for r in rows:
        blob = json.dumps(r)
        if 'myworkdayjobs' not in blob:
            continue
        nm = None
        for k in ('company', 'company_name', 'employer', 'org', 'name'):
            v = r.get(k) if isinstance(r, dict) else None
            if isinstance(v, str) and v.strip():
                nm = v.strip()
                break
        feed(blob, nm)
    print('%-22s -> running total %d triples' % (f, len(trip)), file=sys.stderr)

out = []
for (host, tenant, site), n in trip.most_common():
    out.append(dict(
        company=names.get((host, tenant, site)) or tenant,
        token='%s|%s|%s' % (host, tenant, site),
        seen=n,
    ))

json.dump(out, open('wd_targets_full.json', 'w'), indent=1)
print('\nwrote wd_targets_full.json with %d Workday boards' % len(out))
print('distinct tenants: %d' % len({t['token'].split('|')[1] for t in out}))
