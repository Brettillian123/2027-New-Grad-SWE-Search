"""Board tiering: stop paying full price for boards that never produce anything.

Measured across the last full sweep of 3,680 boards:
    1,573 produced at least one eligible posting
    1,854 were reachable but silent
      253 were dead (404 / DNS / retired tenant)

So 57% of every run is spent on boards that returned nothing. Scanning only the
productive ones is 43% of the work, and a silent board is not permanently silent
- it just does not need checking twice a week.

    tier A  produced something recently   -> every run
    tier B  reachable but silent          -> every 4th run
    tier D  dead                          -> every 8th run, in case it comes back

State lives in board_tiers.json next to this file.
"""
import datetime as dt, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, 'board_tiers.json')

HOT_DAYS = 30      # a hit this recent keeps a board in tier A
B_EVERY = 4        # silent boards get checked this often
D_EVERY = 8        # dead boards this often


def load():
    if os.path.exists(PATH):
        try:
            return json.load(open(PATH, encoding='utf-8'))
        except Exception:
            pass
    return {'run': 0, 'boards': {}}


def save(st):
    json.dump(st, open(PATH, 'w'), indent=1)


def key(t):
    return '%s|%s' % (t.get('ats', 'workday'), t.get('token', ''))


def select(targets, st, force_all=False):
    """-> (to_scan, skipped_counts)"""
    if force_all:
        return targets, {'A': len(targets), 'B': 0, 'D': 0, 'skipped': 0}
    run = st.get('run', 0)
    boards = st.get('boards', {})
    today = dt.date.today()
    out, counts = [], {'A': 0, 'B': 0, 'D': 0, 'skipped': 0}
    for t in targets:
        b = boards.get(key(t))
        if not b:
            out.append(t)                       # never seen: always scan
            counts['A'] += 1
            continue
        last = b.get('last_hit')
        if last:
            try:
                age = (today - dt.date.fromisoformat(last)).days
            except Exception:
                age = 999
            if age <= HOT_DAYS:
                out.append(t)
                counts['A'] += 1
                continue
        every = D_EVERY if b.get('dead') else B_EVERY
        if run % every == 0:
            out.append(t)
            counts['D' if b.get('dead') else 'B'] += 1
        else:
            counts['skipped'] += 1
    return out, counts


def record(st, results):
    """Fold one scan's results back into the tier state."""
    boards = st.setdefault('boards', {})
    today = dt.date.today().isoformat()
    for r in results:
        k = '%s|%s' % (r.get('ats', 'workday'), r.get('token', ''))
        b = boards.setdefault(k, {})
        b['company'] = r.get('company')
        if r.get('jobs'):
            b['last_hit'] = today
            b['dead'] = False
            b['misses'] = 0
        else:
            b['misses'] = b.get('misses', 0) + 1
            b['dead'] = bool(r.get('error'))
    st['run'] = st.get('run', 0) + 1
    return st
