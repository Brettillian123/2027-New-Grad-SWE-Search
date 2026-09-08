#!/usr/bin/env python3
"""Refresh Brett's 2027 target board.

    python refresh.py              full refresh, every platform (~40-60 min)
    python refresh.py --fast       skip Workday + enterprise ATS (~15 min)
    python refresh.py --no-scan    re-gate the last scan without re-fetching (~10 s)

All dates are computed from TODAY, never hardcoded, so this stays correct on any
day it runs. Prints a short report on purpose: the point is to answer "what is
new and worth applying to" without anyone reading thousands of postings.

Applying inside 48 hours is the whole game, so anything opened within two days is
labelled `<48 hours` on the board and listed first in the report.
"""
import argparse, collections, datetime as dt, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.dirname(HERE)                       # ...\JobSearch
STATE = os.path.join(HERE, 'board_state.json')    # what we had seen before
sys.path.insert(0, HERE)

TODAY = dt.date.today()
FRESH = TODAY - dt.timedelta(days=14)     # the two-week rule
NEW48 = TODAY - dt.timedelta(days=2)      # the <48h label
FLOOR = 90000
MID_TOLERANCE = 0.90

# Entry level means entry level. openelig's SENIOR_TITLE now rejects these at
# collection time, but re-gating a scan taken before that fix needs the same
# test here - GitLab's "Intermediate Backend Engineer" states no year floor and
# so passed as an unlevelled title.
LEVEL_UP = re.compile(r'\b(intermediate|mid[\s-]?level|mid[\s-]?senior|experienced)\b', re.I)
MAX_FLOOR = 1   # anything REQUIRING 2+ years is out (preferred figures don't count)

# Seniority asserted without a number ("deep systems experience", "have run large
# GPU fleets in production"). One such phrase can appear in a nice-to-have on a
# genuinely open req, so one is shown and kept; two or more is the posting telling
# you what it wants, and is cut.
MAX_HINTS = 1

# ATS tokens are lowercase slugs, so company names arrive as "gitlab", "imc".
CANON = {
    'imc': 'IMC Trading', 'gitlab': 'GitLab', 'roo': 'Roo', 'hightouch': 'Hightouch',
    'globalizationpartners': 'Globalization Partners', 'propelus': 'Propelus',
    'mercury': 'Mercury', 'cursor': 'Cursor (Anysphere)', 'alpaca': 'Alpaca',
    'openai': 'OpenAI', 'abbvie': 'AbbVie', 'caci': 'CACI', 'nvidia': 'NVIDIA',
    'slate': 'Slate', 'virtualitics': 'Virtualitics', 'ontic': 'Ontic',
    'lumin-digital': 'Lumin Digital', 'litellm': 'LiteLLM (BerriAI)',
}


def disp(name):
    k = (name or '').lower().strip()
    if k in CANON:
        return CANON[k]
    if name.isupper() and len(name) <= 5:
        return name
    if name.islower():
        return re.sub(r'\b([a-z])', lambda m: m.group(1).upper(), name.replace('-', ' '))
    return name


#   script, full target file, output, is-slow, default ats for tiering
SCANS = [
    ('api', 'ats.py',       'targets_all.json',     'scan_api.json', False, None),
    ('wd',  'wd4.py',       'wd_targets_full.json', 'scan_wd.json',  True,  'workday'),
    ('new', 'sweep_new.py',  None,                  'scan_new.json', True,  None),
]

WORKERS = 32   # measured: 8 -> 8.1 req/s, 32 -> 16.0, 64 -> 18.6. 32 is the knee.


def run_scans(fast, scan_all):
    import tiers
    st = tiers.load()
    for name, script, tgtfile, out, slow, ats in SCANS:
        if fast and slow:
            print('  skip   %-4s (--fast)' % name)
            continue
        cmd = [sys.executable, script]
        if tgtfile:
            p = os.path.join(HERE, tgtfile)
            if not os.path.exists(p):
                print('  skip   %-4s (no %s)' % (name, tgtfile))
                continue
            targets = json.load(open(p, encoding='utf-8'))
            for t in targets:
                t.setdefault('ats', ats or t.get('ats'))
            sel, c = tiers.select(targets, st, force_all=scan_all)
            sub = os.path.join(HERE, 'tier_%s.json' % name)
            json.dump(sel, open(sub, 'w'))
            print('  run    %-4s %d of %d boards (A=%d B=%d D=%d, skipped %d)'
                  % (name, len(sel), len(targets), c['A'], c['B'], c['D'], c['skipped']),
                  flush=True)
            cmd += [sub, out]
        else:
            print('  run    %-4s -> %s' % (name, out), flush=True)
            cmd += [out]
        if script in ('wd4.py', 'ats.py', 'sweep_new.py'):
            cmd.append('--workers=%d' % WORKERS)
        with open(os.path.join(HERE, 'scan_%s.log' % name), 'w') as fh:
            subprocess.run(cmd, cwd=HERE, stderr=fh, stdout=subprocess.DEVNULL)
        if os.path.exists(os.path.join(HERE, out)):
            rows = json.load(open(os.path.join(HERE, out), encoding='utf-8'))
            for r in rows:
                r.setdefault('ats', ats or r.get('ats') or 'workday')
            st = tiers.record(st, rows)
    tiers.save(st)


def n_boards():
    """How many boards this scan could actually reach, counted not retyped."""
    n = 0
    for f in ('targets_all.json', 'wd_targets_full.json'):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            try:
                n += len(json.load(open(p, encoding='utf-8')))
            except Exception:
                pass
    return n or 3680


def load_postings():
    """Every eligible posting the scanners produced, flattened."""
    import geo, sal
    rows = []
    for f in ('scan_api.json', 'scan_wd.json', 'scan_new.json'):
        p = os.path.join(HERE, f)
        if not os.path.exists(p):
            continue
        for r in json.load(open(p, encoding='utf-8')):
            for j in r.get('jobs', []):
                j.setdefault('company', r.get('company'))
                j.setdefault('ats', r.get('ats', 'workday'))
                rows.append(j)
    return rows, geo, sal


def gate(rows, geo, sal):
    import openelig as _elig
    f = collections.Counter()
    kept = []
    for j in rows:
        f['eligible'] += 1
        op = j.get('opened') or ''
        if not op:
            f['no date'] += 1
            continue
        if op < FRESH.isoformat():
            f['older than 2 weeks'] += 1
            continue
        if LEVEL_UP.search(j.get('title') or ''):
            f['not entry level (title)'] += 1
            continue
        # recompute from the stored body: the posting text travels with the scan,
        # so a rule change re-gates the last run instead of needing a refetch
        body = j.get('desc') or ''
        if body:
            req, pref = _elig.required_years(body)
            j['floor'], j['floor_pref'] = req, pref
            # recompute too: remote_body was recorded with a regex whose last two
            # alternatives could never fire (literal backspaces for word boundaries)
            if not j.get('remote_body'):
                j['remote_body'] = geo.remote_in_text(body)
        if (j.get('floor') or 0) > MAX_FLOOR:
            f['requires %d+ yrs' % (MAX_FLOOR + 1)] += 1
            continue
        if len(j.get('senior_hint') or []) > MAX_HINTS:
            f['not entry level (implied)'] += 1
            continue
        g = geo.geo(j.get('loc') or '')
        if g['foreign_only'] or not g['us']:
            f['not US'] += 1
            continue
        # A posting whose location names an office can still BE remote; the
        # collectors set remote_body from the full text before truncation.
        body_remote = bool(j.get('remote_body'))
        if not (g['remote'] or g['chicago'] or body_remote):
            f['not remote/Chicago'] += 1
            continue
        lo, hi = j.get('smin'), j.get('smax')
        if not hi:
            lo, hi = sal.extract(j.get('desc') or '')
        if hi:
            if hi < FLOOR:
                f['band under floor'] += 1
                continue
            if ((lo or hi) + hi) / 2 < FLOOR * MID_TOLERANCE:
                f['midpoint too low'] += 1
                continue
        j.update(smin=lo, smax=hi, chicago=g['chicago'], remote=g['remote'],
                 new48=(op >= NEW48.isoformat()))
        if body_remote:
            j['remote'] = True
        kept.append(j)
        f['KEPT'] += 1
    return kept, f


def build_board(kept):
    """Company-level rows, watch entries preserved from the previous board."""
    # The same req reaches us more than once: multi-location postings, and boards
    # that appear under two tokens. Dedupe before counting roles, or a company
    # shows "2 open roles" that are one job listed twice.
    seen, uniq = set(), []
    for j in kept:
        key = (disp(j['company']).lower(), (j.get('title') or '').lower(),
               (j.get('loc') or '').lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(j)
    kept[:] = uniq

    co = collections.defaultdict(list)
    for j in kept:
        co[disp(j['company'])].append(j)
    rows = []
    for name, js in co.items():
        js.sort(key=lambda x: (x.get('smax') or 0, x.get('opened') or ''), reverse=True)
        b = js[0]
        band = [x for x in js if x.get('smax')]
        top = max(band, key=lambda x: x['smax']) if band else None
        rows.append(dict(
            company=name, title=b['title'],
            chicago=any(x['chicago'] for x in js), remote=any(x['remote'] for x in js),
            ai=any(x.get('ai') for x in js), new48=any(x.get('new48') for x in js),
            smin=(top['smin'] if top else None), smax=(top['smax'] if top else None),
            opened=max(x.get('opened') or '' for x in js),
            url=b.get('url') or '', loc=b.get('loc') or '',
            floor=b.get('floor'), floor_pref=b.get('floor_pref'),
            senior_hint=sorted({h for x in js for h in (x.get('senior_hint') or [])})[:2],
            status='LIVE', in_window=True, n_roles=len(js),
            why='; '.join(sorted({x['title'] for x in js})[:3])[:180], est_base=''))

    prev = os.path.join(HERE, 'final.json')
    if os.path.exists(prev):
        have = {r['company'].lower() for r in rows}
        for r in json.load(open(prev, encoding='utf-8')):
            if r.get('status') != 'LIVE' and r['company'].lower() not in have:
                r['new48'] = False
                rows.append(r)          # keep watch-tier entries
    rows.sort(key=lambda r: (r['status'] != 'LIVE', not r.get('new48'),
                             -(r['smax'] or 0), r['company'].lower()))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fast', action='store_true', help='skip Workday + enterprise ATS')
    ap.add_argument('--no-scan', action='store_true', help='re-gate without re-fetching')
    ap.add_argument('--all', action='store_true', help='scan every board, ignore tiering')
    a = ap.parse_args()

    print('BOARD REFRESH  %s' % TODAY.isoformat())
    print('  two-week cutoff  %s' % FRESH.isoformat())
    print('  <48h cutoff      %s' % NEW48.isoformat())
    print()

    if not a.no_scan:
        run_scans(a.fast, a.all)
        print()

    rows, geo, sal = load_postings()
    if not rows:
        print('NO SCAN DATA. Run without --no-scan first.')
        return 1
    kept, f = gate(rows, geo, sal)

    print('FUNNEL')
    for k in ('eligible', 'no date', 'older than 2 weeks',
              'not entry level (title)', 'requires 2+ yrs',
              'not entry level (implied)', 'not US',
              'not remote/Chicago', 'band under floor', 'midpoint too low', 'KEPT'):
        if f[k]:
            print('  %-20s %6d' % (k, f[k]))

    board = build_board(kept)
    json.dump(board, open(os.path.join(HERE, 'final.json'), 'w'), indent=1)
    json.dump({'boards': format(n_boards(), ','), 'posts': format(len(rows), ','),
               'classified': len(kept),
               # the page states its own filters, so they travel with the run
               # instead of being retyped into the template every time
               'rundate': TODAY.strftime('%-d %B %Y') if os.name != 'nt'
                          else TODAY.strftime('%#d %B %Y'),
               'windate': FRESH.strftime('%#d %b' if os.name == 'nt' else '%-d %b'),
               'floor': '$%dk' % (FLOOR // 1000), 'funnel': dict(f)},
              open(os.path.join(HERE, 'stats.json'), 'w'))

    # what is genuinely new since the last run
    seen = set()
    if os.path.exists(STATE):
        try:
            seen = set(json.load(open(STATE, encoding='utf-8')).get('urls', []))
        except Exception:
            seen = set()
    fresh_urls = [j for j in kept if j.get('url') and j['url'] not in seen]
    json.dump({'ran': TODAY.isoformat(), 'urls': sorted({j['url'] for j in kept if j.get('url')})},
              open(STATE, 'w'))

    n48 = [j for j in kept if j.get('new48')]
    print()
    print('BOARD  %d companies  (%d live, %d watch)  %d Chicago  %d remote'
          % (len(board), sum(1 for r in board if r['status'] == 'LIVE'),
             sum(1 for r in board if r['status'] != 'LIVE'),
             sum(1 for r in board if r['chicago']),
             sum(1 for r in board if r['remote'])))
    print()
    print('POSTED IN THE LAST 48 HOURS: %d' % len(n48))
    for j in sorted(n48, key=lambda x: -(x.get('smax') or 0)):
        pay = ('$%dk' % (j['smax'] // 1000)) if j.get('smax') else '-'
        where = 'Chicago' if j['chicago'] else 'Remote'
        print('   %-26s %-44s %-8s %-8s %s'
              % (disp(j['company'])[:26], j['title'][:44], where, pay, j['opened']))
    if not n48:
        print('   (nothing new in that window)')

    print()
    print('NEW SINCE LAST RUN: %d postings' % len(fresh_urls))
    for j in fresh_urls[:15]:
        print('   %-26s %s' % (disp(j['company'])[:26], j['title'][:52]))
    if len(fresh_urls) > 15:
        print('   ... and %d more' % (len(fresh_urls) - 15))

    subprocess.run([sys.executable, 'inject.py'], cwd=HERE)
    print()
    print('Wrote target_board.html and final.json.')
    print('Ask Claude to publish the board when you want the artifact updated.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
