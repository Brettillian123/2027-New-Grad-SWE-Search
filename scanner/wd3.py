"""Workday scanner, date-walk edition.

wd2.py ran 8 keyword queries x 3 pages against every board (~17.6 POSTs), then
spent a detail GET on every title that passed eligibility just to learn its date
- 57% of which the list had ALREADY reported as older than the window.

Workday returns an empty search NEWEST-FIRST (verified across 5 boards). So:

  1. Page an empty search until the postings fall out of the window, then STOP.
  2. Read `postedOn` off the LIST row, and only spend a detail GET on postings
     that are both in-window and eligible by title.

That is fewer requests AND better coverage, because an empty search returns every
posting rather than only the ones matching eight guessed phrases.

Usage: python wd3.py <targets.json> <out.json> [limit] [--days N]
"""
import json, re, sys, time, urllib.request, concurrent.futures as cf
from ats import iso, UA
import openelig

WINDOW = 14          # days back to walk
PAGE = 20            # Workday pins page size at 20
MAX_PAGES = 60       # 800 postings; boards busier than that get logged, not silently cut
MAX_DETAIL = 80

FALLBACK_QUERIES = ["software engineer", "software developer", "data engineer",
                    "backend engineer", "full stack", "machine learning engineer",
                    "new grad", "entry level"]

REL = re.compile(r'posted\s+(today|yesterday|(\d+)\+?\s*days?\s+ago)', re.I)


def rel_days(s):
    """'Posted 30+ Days Ago' -> 30, 'Posted Today' -> 0, unknown -> None."""
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

    fresh, pages, err, capped, unknown, dry = [], 0, None, False, 0, 0
    total = 0
    try:
        for pg in range(MAX_PAGES):
            pages += 1
            d = post(base + "/jobs", {"appliedFacets": {}, "limit": PAGE,
                                      "offset": pg * PAGE, "searchText": ""})
            ps = d.get("jobPostings", [])
            total = d.get("total") or total
            if not ps:
                break
            got = 0
            for p in ps:
                if not p.get("externalPath"):
                    continue
                days = rel_days(p.get("postedOn"))
                if days is None:
                    unknown += 1
                    fresh.append(p)          # cannot tell, keep and let detail decide
                    got += 1
                elif days <= window:
                    fresh.append(p)
                    got += 1
            # Workday's default order is MOSTLY newest-first but not strictly, so
            # stopping at the first out-of-window row ends the walk early: Micron
            # stopped after 1 page and lost 3 fresh reqs, Leidos after 2 and lost
            # 19. Stop only after two consecutive pages yield nothing fresh.
            dry = dry + 1 if got == 0 else 0
            if dry >= 2 or len(ps) < PAGE:
                break
        else:
            capped = True
    except Exception as e:
        err = "%s: %s" % (type(e).__name__, str(e)[:60])

    # Run the keyword sweep when the walk cannot be trusted to have seen the whole
    # window: either it hit the page cap, or it stopped on dry pages while the
    # board still reports far more postings than we walked. Leidos is the case
    # that forced this - its ordering degrades after the first pages, so the walk
    # went dry at page 4 while 19 fresh Software Engineer reqs sat deeper in.
    walked = pages * PAGE
    unsure = capped or (total and total > walked * 1.5)
    if unsure:
        bykey = {p.get("externalPath"): p for p in fresh}
        try:
            for q in FALLBACK_QUERIES:
                for off in (0, 20, 40):
                    d = post(base + "/jobs", {"appliedFacets": {}, "limit": PAGE,
                                              "offset": off, "searchText": q})
                    ps = d.get("jobPostings", [])
                    for p in ps:
                        ep = p.get("externalPath")
                        if not ep or ep in bykey:
                            continue
                        days = rel_days(p.get("postedOn"))
                        if days is None or days <= window:
                            bykey[ep] = p
                    if len(ps) < PAGE:
                        break
        except Exception as e:
            err = err or "fallback %s: %s" % (type(e).__name__, str(e)[:50])
        fresh = list(bykey.values())

    if not fresh:
        return dict(company=name, token=token, error=err, jobs=[],
                    pages=pages, seen=0, capped=capped)

    cands = [p for p in fresh
             if p.get("title") and openelig.eligibility4(dict(title=p["title"], desc=""))[0]]

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

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
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

    return dict(company=name, token=token, pages=pages, seen=len(fresh),
                cands=len(cands), jobs=hits, error=err, capped=capped,
                unknown_date=unknown, total=total, fallback=bool(unsure))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    window = WINDOW
    for a in sys.argv[1:]:
        if a.startswith('--days'):
            window = int(a.split('=')[1]) if '=' in a else WINDOW

    targets = json.load(open(args[0]))
    if len(args) > 2:
        targets = targets[:int(args[2])]

    out, done, t0 = [], 0, time.time()
    with cf.ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(scan, t["company"], t["token"], window) for t in targets]
        for f in cf.as_completed(futs):
            done += 1
            try:
                r = f.result()
            except Exception as e:
                print("FATAL %s" % str(e)[:70], file=sys.stderr)
                continue
            out.append(r)
            if r["jobs"] or done % 50 == 0:
                print("[%4d/%4d] %-26s %2dp %s" % (
                    done, len(targets), r["company"][:26], r.get("pages", 0),
                    r.get("error") or "%d hits / %d cands / %d fresh%s"
                    % (len(r["jobs"]), r.get("cands", 0), r.get("seen", 0),
                       ' CAPPED' if r.get('capped') else '')), file=sys.stderr)
            if done % 60 == 0:
                json.dump(out, open(args[1], "w"))

    json.dump(out, open(args[1], "w"), indent=1)
    el = time.time() - t0
    print("\nDONE boards=%d hits=%d pages=%d elapsed=%.0fs (%.2fs/board) capped=%d"
          % (len(out), sum(len(r["jobs"]) for r in out),
             sum(r.get("pages", 0) for r in out), el, el / max(1, len(out)),
             sum(1 for r in out if r.get('capped'))), file=sys.stderr)
