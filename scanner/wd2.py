"""Workday scanner, corrected.

Two fixes over wd.py:
  1. QUERIES only searched new-grad phrasing, so ordinary junior reqs were never
     even requested from the server.
  2. The pre-filter used ats.classify(), which DROPS 'Software Engineer',
     'Backend Engineer', 'Data Engineer', 'Platform Engineer' and 'ML Engineer'.
     Those are exactly the tier-C titles eligibility4 accepts. Every Workday
     board previously scanned was filtered with the superseded rule.

Usage: python wd2.py <targets.json> <out.json> [limit]
"""
import json, re, sys, time, urllib.request, concurrent.futures as cf
from ats import iso, UA
import openelig

QUERIES = ["software engineer", "new grad software engineer", "entry level software engineer",
           "associate software engineer", "backend engineer", "software engineer I",
           "university graduate", "early career software"]

MAX_DETAIL = 60          # was silently 25 in wd.py
PAGES = (0, 20, 40)


def post(url, body, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                         headers={**UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep((5.0 if getattr(e, "code", None) == 429 else 1.2) * (i + 1))
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
            time.sleep(4.0 if getattr(e, "code", None) == 429 else 0.8)
    raise last


def scan(name, token):
    try:
        host, tenant, site = token.split("|")
    except ValueError:
        return dict(company=name, token=token, error="bad token", jobs=[])
    base = "https://%s/wday/cxs/%s/%s" % (host, tenant, site)
    found, err = {}, None
    for q in QUERIES:
        try:
            for off in PAGES:
                d = post(base + "/jobs", {"appliedFacets": {}, "limit": 20,
                                          "offset": off, "searchText": q})
                ps = d.get("jobPostings", [])
                for p in ps:
                    if p.get("externalPath"):
                        found[p["externalPath"]] = p
                if len(ps) < 20:
                    break
        except Exception as e:
            err = "%s: %s" % (type(e).__name__, str(e)[:60])
            break
    if not found:
        return dict(company=name, token=token, error=err or "no postings", jobs=[], total=0)

    # pre-filter on TITLE with the current eligibility rule, not the old classify()
    cands = []
    for p in found.values():
        t = p.get("title") or ""
        if not t:
            continue
        tier, floor, stretch = openelig.eligibility4(dict(title=t, desc=""))
        if tier:
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
        return dict(
            company=name, title=p["title"],
            loc=d.get("location") or p.get("locationsText", ""),
            opened=iso(d.get("startDate")), url="https://%s/en-US/%s%s" % (host, site, p["externalPath"]),
            desc=desc[:9000], ats="workday",
            remote="remote" in (d.get("remoteType", "") or "").lower(),
            posted_rel=p.get("postedOn", ""),
        )

    with cf.ThreadPoolExecutor(max_workers=4) as ex:
        for j in ex.map(detail, cands[:MAX_DETAIL]):
            tier, floor, stretch = openelig.eligibility4(j)
            if not tier:
                continue
            j.update(tier=tier, floor=floor, stretch=stretch)
            j["desc"] = j["desc"][:1500]
            hits.append(j)

    return dict(company=name, token=token, total=len(found),
                cands=len(cands), jobs=hits, error=err)


if __name__ == "__main__":
    targets = json.load(open(sys.argv[1]))
    if len(sys.argv) > 3:
        targets = targets[:int(sys.argv[3])]
    out, done = [], 0
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(scan, t["company"], t["token"]): t for t in targets}
        for f in cf.as_completed(futs):
            done += 1
            try:
                r = f.result()
            except Exception as e:
                print("FATAL %s" % str(e)[:70], file=sys.stderr)
                continue
            out.append(r)
            if r["jobs"] or done % 25 == 0:
                print("[%4d/%4d] %-28s %s" % (
                    done, len(targets), r["company"][:28],
                    r.get("error") or "%d hits / %d cands / %d posts"
                    % (len(r["jobs"]), r.get("cands", 0), r.get("total", 0))),
                    file=sys.stderr)
            if done % 40 == 0:
                json.dump(out, open(sys.argv[2], "w"), indent=1)
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    tot = sum(len(r["jobs"]) for r in out)
    ok = sum(1 for r in out if not r.get("error"))
    print("\nDONE boards=%d reachable=%d hits=%d" % (len(out), ok, tot), file=sys.stderr)
