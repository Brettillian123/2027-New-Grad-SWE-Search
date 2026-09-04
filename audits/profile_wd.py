"""Where does the Workday sweep actually spend its time?

Counts requests rather than guessing: list POSTs vs detail GETs, and how many of
those detail GETs were spent on postings the list had ALREADY reported as older
than the window.
"""
import json, re, sys, time, urllib.request
import openelig
from ats import UA

QUERIES = ["software engineer", "new grad software engineer", "entry level software engineer",
           "associate software engineer", "backend engineer", "software engineer I",
           "university graduate", "early career software"]
PAGES = (0, 20, 40)
REL = re.compile(r'posted\s+(today|yesterday|(\d+)\+?\s+days?\s+ago)', re.I)


def rel_days(s):
    """'Posted 30+ Days Ago' -> 30 ; 'Posted Today' -> 0 ; unknown -> None"""
    m = REL.search(s or '')
    if not m:
        return None
    if m.group(1).lower() == 'today':
        return 0
    if m.group(1).lower() == 'yesterday':
        return 1
    return int(m.group(2))


def post(url, body, timeout=25):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


targets = json.load(open('wd_targets_full.json', encoding='utf-8'))[:int(sys.argv[1] if len(sys.argv) > 1 else 8)]

t0 = time.time()
n_list = n_found = 0
elig = 0
would_detail = 0
needed_detail = 0
no_rel = 0

for t in targets:
    host, tenant, site = t['token'].split('|')
    base = "https://%s/wday/cxs/%s/%s" % (host, tenant, site)
    found = {}
    for q in QUERIES:
        try:
            for off in PAGES:
                n_list += 1
                d = post(base + "/jobs", {"appliedFacets": {}, "limit": 20,
                                          "offset": off, "searchText": q})
                ps = d.get("jobPostings", [])
                for p in ps:
                    if p.get("externalPath"):
                        found[p["externalPath"]] = p
                if len(ps) < 20:
                    break
        except Exception:
            break
    n_found += len(found)
    for p in found.values():
        tier, _, _ = openelig.eligibility4(dict(title=p.get('title') or '', desc=''))
        if not tier:
            continue
        elig += 1
        would_detail += 1                      # what wd2.py does today
        d = rel_days(p.get('postedOn'))
        if d is None:
            no_rel += 1
            needed_detail += 1                 # unknown, must check
        elif d <= 14:
            needed_detail += 1                 # genuinely in the window

el = time.time() - t0
print('boards sampled        %d' % len(targets))
print('elapsed               %.1f s  (%.1f s per board)' % (el, el / len(targets)))
print()
print('list POSTs            %d' % n_list)
print('postings seen         %d' % n_found)
print('eligible by title     %d' % elig)
print()
print('detail GETs today     %d' % would_detail)
print('detail GETs needed    %d' % needed_detail)
print('wasted               %d  (%.0f%%)'
      % (would_detail - needed_detail,
         100.0 * (would_detail - needed_detail) / max(1, would_detail)))
print('no postedOn field     %d' % no_rel)
