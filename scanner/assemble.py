"""Assemble the final target list from every verified source."""
import json, os, re, csv
from collections import defaultdict
import rank

WF = r"C:\Users\Brett\.claude\projects\C--Users-Brett-OneDrive-Documents-JobSearch\47409783-7799-4744-bcb8-aab5b033e227\subagents\workflows"

WINDOW_START = '2026-08-25'
CYCLE_START = '2026-06-01'   # 2027 new-grad cycle effectively opens here


def journal(run):
    p = os.path.join(WF, run, 'journal.jsonl')
    if not os.path.exists(p):
        return []
    out = []
    for line in open(p, encoding='utf-8'):
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get('type') == 'result' and isinstance(d.get('result'), dict):
            out.append(d['result'])
    return out


def load_live():
    """Verified live postings from company ATS APIs."""
    M = json.load(open('master_all.json'))
    us = [r for r in M
          if r['us'] and not r['foreign_only'] and not r['frontend']
          and (not r['smin'] or r['smax'] >= 95000)]
    by = defaultdict(list)
    for r in us:
        by[rank.canon(r['company'])].append(r)
    rows = []
    for c, ps in by.items():
        s, best, why, sm, newest = rank.score(c, ps)
        if s < 25 or newest < CYCLE_START:
            continue
        rows.append(dict(
            company=c, score=round(s, 1), status='LIVE',
            in_window=newest >= WINDOW_START,
            title=best['title'], url=best['url'], loc=best['loc'],
            opened=newest, smin=best['smin'], smax=sm,
            chicago=any(p['chicago'] for p in ps),
            remote=any(p['remote'] for p in ps),
            ai=any(p['ai'] for p in ps),
            n_roles=len(ps), why='; '.join(why), source=best['src'],
            evidence='%s ATS API, first_published/publishedAt = %s' % (best['src'], newest),
        ))
    return rows


def load_watch():
    """Companies confirmed opening by Sept 20, from the openers workflow."""
    rows = []
    for r in journal('wf_10818994-285'):
        for c in (r.get('companies') or []):
            st = (c.get('status') or '').upper()
            if st not in ('LIVE_NOW', 'OPENS_BY_SEP20'):
                continue
            rows.append(dict(
                company=c['company'], score=0, status=st,
                in_window=True,
                title=c.get('title', ''), url=c.get('apply_url', ''),
                loc=('Chicago' if c.get('chicago') else ('Remote' if c.get('remote') else '')),
                opened=c.get('opened_date', ''), smin=None, smax=0,
                chicago=bool(c.get('chicago')), remote=bool(c.get('remote')),
                ai=bool(c.get('backend_ai')), n_roles=1,
                why=c.get('notes', '')[:220], source='research',
                evidence=(c.get('evidence') or '')[:400],
                confidence=c.get('confidence', ''), est_base=c.get('est_base', ''),
            ))
    return rows


def load_portals():
    """Postings confirmed at source by the hard-targets workflow."""
    rows = []
    for r in journal('wf_22f0e86c-f3c'):
        for p in (r.get('postings') or []):
            if (p.get('status') or '') == 'closed':
                continue
            rows.append(dict(
                company=p['company'], score=0, status='LIVE' if p.get('status') == 'open' else 'WATCH',
                in_window=(p.get('opened_date', '') >= WINDOW_START
                           or p.get('opens_by_2026_09_20') in ('yes', 'likely')),
                title=p.get('title', ''), url=p.get('url', ''),
                loc=p.get('location', ''), opened=p.get('opened_date', ''),
                smin=None, smax=0,
                chicago='chicago' in (p.get('remote_or_chicago', '') + p.get('location', '')).lower(),
                remote='remote' in (p.get('remote_or_chicago', '') + p.get('location', '')).lower(),
                ai=bool(p.get('ai_automation')), n_roles=1,
                why=(p.get('notes') or '')[:220], source='research',
                evidence=(p.get('date_evidence') or '')[:400],
                est_base=p.get('est_base', ''),
            ))
    return rows


def merge(*groups):
    seen = {}
    for g in groups:
        for r in g:
            k = re.sub(r'[^a-z0-9]', '', rank.canon(r['company']).lower())
            if not k:
                continue
            if k in seen:
                cur = seen[k]
                # prefer a LIVE record with a real URL and a date
                better = (r['status'] == 'LIVE' and cur['status'] != 'LIVE') or \
                         (r.get('opened') and not cur.get('opened'))
                if better:
                    r['why'] = (r.get('why') or '') or cur.get('why', '')
                    seen[k] = r
                continue
            r['company'] = rank.canon(r['company'])
            seen[k] = r
    return list(seen.values())


if __name__ == '__main__':
    live, watch, portals = load_live(), load_watch(), load_portals()
    print('live=%d watch=%d portals=%d' % (len(live), len(watch), len(portals)))
    allr = merge(live, portals, watch)
    for r in allr:
        s = r.get('score') or 0
        if r['chicago']:
            s += 22
        if r['remote']:
            s += 22
        if r['ai']:
            s += 12
        if r['in_window']:
            s += 14
        if r['status'] == 'LIVE':
            s += 10
        r['final'] = round(s, 1)
    allr.sort(key=lambda r: -r['final'])
    json.dump(allr, open('final.json', 'w'), indent=1, default=str)
    print('merged companies:', len(allr))
    print('  chicago:', sum(1 for r in allr if r['chicago']),
          '| remote:', sum(1 for r in allr if r['remote']),
          '| in-window:', sum(1 for r in allr if r['in_window']),
          '| live:', sum(1 for r in allr if r['status'] == 'LIVE'))
