"""Workday scanner: wd2's query strategy, with the wasted work removed.

Benchmarked on 24 boards sampled evenly across the target file:
  wd2 keyword queries  1.57 s/board, 16 fresh
  wd3 date walk        4.00 s/board, 38 fresh   <- more coverage, 2.5x slower

So the date walk is a COVERAGE win, not a speed win. This keeps wd2's cheap
query strategy and removes the two things that were pure waste:

  1. A detail GET on every eligible title just to learn its date, when the LIST
     row already carries `postedOn`. 57% of those were for postings the list had
     already reported as older than the window.
  2. Low concurrency. This work is entirely network-bound.

`--walk` switches to the wd3 date-walk when coverage matters more than time.

Usage: python wd4.py <targets.json> <out.json> [limit] [--workers N] [--days N] [--walk]
"""
import json, re, sys, time, urllib.request, concurrent.futures as cf
from ats import iso, UA
import openelig

WINDOW = 14
PAGE = 20
MAX_DETAIL = 80
WORKERS = 16          # network-bound; 8 was leaving the link idle

QUERIES = ["software engineer", "new grad software engineer", "entry level software engineer",
           "associate software engineer", "backend engineer", "software engineer I",
           "university graduate", "early career software"]

REL = re.compile(r'posted\s+(today|yesterday|(\d+)\+?\s*days?\s+ago)', re.I)


def rel_days(s):
    m = REL.search(s or '')
    if not m:
        return None
    g = m.group(1).lower()
    if g.startswith('today'):
        return 0
    if g.startswith('yesterday'):
        return 1
    return int(m.group(2))


def post(url, body, timeout=25, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={**UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep((5.0 if getattr(e, "code", None) == 429 else 1.0) * (i + 1))
    raise last


def getj(url, timeout=25, tries=2):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(3.0 if getattr(e, "code", None) == 429 else 0.6)
    raise last


def scan(name, token, window=WINDOW):
    try:
        host, tenant, site = token.split("|")
    except ValueError:
        return dict(company=name, token=token, error="bad token", jobs=[])
    base = "https://%s/wday/cxs/%s/%s" % (host, tenant, site)

    found, err = {}, None
    for q in QUERIES:
        try:
            for off in (0, 20, 40):
                d = post(base + "/jobs", {"appliedFacets": {}, "limit": PAGE,
                                          "offset": off, "searchText": q})
                ps = d.get("jobPostings", [])
                for p in ps:
                    if p.get("externalPath"):
                        found[p["externalPath"]] = p
                if len(ps) < PAGE:
                    break
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, str(e)[:60])
            break

    if not found:
        return dict(company=name, token=token, error=err or "no postings",
                    jobs=[], total=0, skipped_stale=0)

    # THE FIX: the list row already carries the posting age. Drop anything older
    # than the window BEFORE spending a detail request on it. Postings with no
    # postedOn are kept, because unknown is not the same as stale.
    cands, stale = [], 0
    for p in found.values():
        t = p.get("title") or ""
        if not t:
            continue
        d = rel_days(p.get("postedOn"))
        if d is not None and d > window:
            stale += 1
            continue
        if openelig.eligibility4(dict(title=t, desc=""))[0]:
            cands.append(p)

    hits = []

    def detail(p):
        try:
            ep = p["externalPath"]
            ep = ep if ep.startswith("/job/") else "/job" + ep
            d = getj(base + ep).get("jobPostingInfo", {})
        except Exception:
            d = {}
        desc = re.sub("<[^>]+>", " ", d.get("jobDescription", "") or "")
        return dict(company=name, title=p["title"],
                    loc=d.get("location") or p.get("locationsText", ""),
                    opened=iso(d.get("startDate")),
                    url="https://%s/en-US/%s%s" % (host, site, p["externalPath"]),
                    desc=desc[:9000], ats="workday",
                    remote="remote" in (d.get("remoteType", "") or "").lower(),
                    posted_rel=p.get("postedOn", ""))

    if cands:
        with cf.ThreadPoolExecutor(max_workers=5) as ex:
            for j in ex.map(detail, cands[:MAX_DETAIL]):
                tier, floor, stretch = openelig.eligibility4(j)
                if not tier:
                    continue
                j.update(tier=tier, floor=floor, stretch=stretch)
                try:
                    import geo as _geo
                    j["remote_body"] = _geo.remote_in_text(j.get("desc") or "")
                except Exception:
                    pass
                j["desc"] = j["desc"][:1500]
                hits.append(j)

    return dict(company=name, token=token, total=len(found), cands=len(cands),
                jobs=hits, error=err, skipped_stale=stale)


if __name__ == "__main__":
    argv = sys.argv[1:]
    walk = '--walk' in argv
    workers, window = WORKERS, WINDOW
    for a in argv:
        if a.startswith('--workers='):
            workers = int(a.split('=')[1])
        if a.startswith('--days='):
            window = int(a.split('=')[1])
    args = [a for a in argv if not a.startswith('--')]

    if walk:
        import wd3
        scan = wd3.scan

    targets = json.load(open(args[0]))
    if len(args) > 2:
        targets = targets[:int(args[2])]

    out, done, t0 = [], 0, time.time()
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(scan, t["company"], t["token"], window) for t in targets]
        for f in cf.as_completed(futs):
            done += 1
            try:
                r = f.result()
            except Exception as e:
                print("FATAL %s" % str(e)[:70], file=sys.stderr)
                continue
            out.append(r)
            if r.get("jobs") or done % 50 == 0:
                print("[%4d/%4d] %-26s %d hits (skipped %d stale)"
                      % (done, len(targets), r["company"][:26], len(r.get("jobs", [])),
                         r.get("skipped_stale", 0)), file=sys.stderr)
            if done % 60 == 0:
                json.dump(out, open(args[1], "w"))

    json.dump(out, open(args[1], "w"), indent=1)
    el = time.time() - t0
    print("\nDONE boards=%d hits=%d skipped_stale=%d elapsed=%.0fs (%.2fs/board) workers=%d"
          % (len(out), sum(len(r.get("jobs", [])) for r in out),
             sum(r.get("skipped_stale", 0) for r in out), el, el / max(1, len(out)), workers),
          file=sys.stderr)
