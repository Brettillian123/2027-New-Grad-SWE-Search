"""Find board tokens for companies we know by name but have never scanned.

We scan 3,680 boards, discovered from one aggregator dump plus name guessing.
Checked against 85 companies that demonstrably hire remote US engineers, 23 were
missing - Shopify, Atlassian, HashiCorp, Rippling, Segment, Netlify, Deel. So the
gap is COMPANIES, not postings.

An ATS token is almost always the company name lowercased and stripped, so every
known name is a cheap 5-endpoint probe.

    python probe.py [limit] [--workers N]
"""
import json, re, sys, urllib.request, concurrent.futures as cf
from ats import UA

ENDPOINTS = [
    ('greenhouse',      'https://boards-api.greenhouse.io/v1/boards/%s/jobs'),
    ('ashby',           'https://api.ashbyhq.com/posting-api/job-board/%s'),
    ('lever',           'https://api.lever.co/v0/postings/%s?mode=json'),
    ('smartrecruiters', 'https://api.smartrecruiters.com/v1/companies/%s/postings'),
    ('workable',        'https://apply.workable.com/api/v1/widget/accounts/%s?details=true'),
]


def variants(name):
    s = re.sub(r'[^a-z0-9 ]', '', (name or '').lower()).strip()
    s = re.sub(r'\s+(inc|llc|ltd|corp|corporation|co|company|group|holdings|technologies|technology|labs|software)$', '', s)
    base = s.replace(' ', '')
    out = [base]
    if ' ' in s:
        out.append(s.replace(' ', '-'))
        # NO first-word-only variant: it cross-matches unrelated boards.
        # "General Atomics" and "General Dynamics" both resolved to token
        # "general", and "Space Dynamics Laboratory" to "space".
    return [v for v in dict.fromkeys(out) if 3 < len(v) < 40]


def count_jobs(ats, d):
    if ats == 'greenhouse':
        return len(d.get('jobs') or [])
    if ats == 'ashby':
        return len(d.get('jobs') or [])
    if ats == 'lever':
        return len(d) if isinstance(d, list) else 0
    if ats == 'smartrecruiters':
        return int(d.get('totalFound') or 0)
    if ats == 'workable':
        return len((d.get('jobs') or []))
    return 0


def probe_one(item):
    name = item['company']
    for tok in variants(name):
        for ats, tmpl in ENDPOINTS:
            try:
                req = urllib.request.Request(tmpl % tok, headers=UA)
                with urllib.request.urlopen(req, timeout=12) as r:
                    if r.status != 200:
                        continue
                    d = json.loads(r.read().decode('utf-8', 'replace'))
            except Exception:
                continue
            n = count_jobs(ats, d)
            if n > 0:
                return dict(company=name, ats=ats, token=tok, n_jobs=n)
    return None


if __name__ == '__main__':
    argv = sys.argv[1:]
    workers = 32
    for a in argv:
        if a.startswith('--workers='):
            workers = int(a.split('=')[1])
    args = [a for a in argv if not a.startswith('--')]

    names = json.load(open('probe_names.json', encoding='utf-8'))
    if args:
        names = names[:int(args[0])]

    print('probing %d company names across %d ATS endpoints (workers=%d)'
          % (len(names), len(ENDPOINTS), workers), file=sys.stderr)

    found, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(probe_one, names):
            done += 1
            if r:
                found.append(r)
                print('  [%4d/%4d] %-30s %-16s %s (%d jobs)'
                      % (done, len(names), r['company'][:30], r['ats'], r['token'], r['n_jobs']),
                      file=sys.stderr)
            elif done % 200 == 0:
                print('  [%4d/%4d] ... %d found so far' % (done, len(names), len(found)),
                      file=sys.stderr)
            if done % 250 == 0:
                json.dump(found, open('probe_found.json', 'w'), indent=1)

    json.dump(found, open('probe_found.json', 'w'), indent=1)
    import collections
    c = collections.Counter(f['ats'] for f in found)
    print('\nFOUND %d new boards out of %d names probed' % (len(found), len(names)), file=sys.stderr)
    for k, v in c.most_common():
        print('   %-18s %4d' % (k, v), file=sys.stderr)
