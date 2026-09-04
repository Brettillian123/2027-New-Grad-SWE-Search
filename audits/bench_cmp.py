"""Correctness check: does the fast scanner find every FRESH posting the old one
found? Raw hit counts are not comparable - the old scanner also collected stale
postings that the gate throws away later."""
import datetime as dt, json

CUT = (dt.date.today() - dt.timedelta(days=14)).isoformat()


def fresh(path):
    out = {}
    for r in json.load(open(path, encoding='utf-8')):
        for j in r.get('jobs', []):
            op = j.get('opened') or ''
            if op >= CUT:
                out[j.get('url') or (j['company'], j['title'])] = j
    return out


old, new = fresh('bench_old.json'), fresh('bench_new.json')
print('window cutoff        %s' % CUT)
print('fresh found by wd2   %d' % len(old))
print('fresh found by wd3   %d' % len(new))
print()

missed = [k for k in old if k not in new]
gained = [k for k in new if k not in old]
print('MISSED by the fast scanner: %d' % len(missed))
for k in missed[:12]:
    j = old[k]
    print('   %-22s %-46s %s' % (j['company'][:22], j['title'][:46], j.get('opened')))
print()
print('FOUND ONLY by the fast scanner: %d' % len(gained))
for k in gained[:12]:
    j = new[k]
    print('   %-22s %-46s %s' % (j['company'][:22], j['title'][:46], j.get('opened')))
