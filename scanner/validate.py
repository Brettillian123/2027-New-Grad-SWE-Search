#!/usr/bin/env python3
"""Confirm harvested candidate tokens are real, live job boards.

    python validate.py cc_candidates.json new_targets.json [--workers=24]

ccharvest.py reads slugs out of crawled URLs, so its output is dirty by
construction: dead boards, renamed companies, tracking paths and hex blobs all
look like slugs. This asks each candidate's API once and keeps only the ones that
answer with a usable posting list.

Deliberately gentler than the scanner (24 workers, backoff on 429, and a token is
dropped rather than retried forever) because this runs against tens of thousands
of boards at once and the point is to be a good citizen of APIs we depend on.
"""
import argparse, json, os, random, sys, time, urllib.error, urllib.request
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (compatible; jobscanner/1.0)",
      "Accept": "application/json,*/*"}

# the cheapest endpoint per ATS that proves the board exists AND has postings.
# Greenhouse deliberately omits content=true here - the list alone is ~20x
# smaller and still carries first_published.
PROBE = {
    "greenhouse":      "https://boards-api.greenhouse.io/v1/boards/%s/jobs",
    "ashby":           "https://api.ashbyhq.com/posting-api/job-board/%s",
    "smartrecruiters": "https://api.smartrecruiters.com/v1/companies/%s/postings?limit=1",
    "workable":        "https://apply.workable.com/api/v1/widget/accounts/%s",
    "lever":           "https://api.lever.co/v0/postings/%s?mode=json",
}


def probe_workday(tok):
    """Workday needs a POST to host/wday/cxs/tenant/site/jobs, not a GET."""
    try:
        host, tenant, site = tok.split("|")
    except ValueError:
        return None
    url = "https://%s/wday/cxs/%s/%s/jobs" % (host, tenant, site)
    body = json.dumps({"appliedFacets": {}, "limit": 20, "offset": 0,
                       "searchText": ""}).encode()
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, data=body,
                                         headers={**UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            n = int(d.get("total") or len(d.get("jobPostings") or []))
            return n or None
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404, 410):
                return None
            if e.code == 429:
                time.sleep(2.0 * (attempt + 1) + random.random())
                continue
            return None
        except Exception:
            return None
    return None


def count_jobs(ats, d):
    if ats == "lever":
        return len(d) if isinstance(d, list) else 0
    if ats == "smartrecruiters":
        return int(d.get("totalFound") or len(d.get("content") or []))
    return len(d.get("jobs") or [])


def probe(rec):
    ats, tok = rec["ats"], rec["token"]
    if ats == "workday":
        n = probe_workday(tok)
        return dict(rec, n=n) if n else None
    url = PROBE.get(ats)
    if not url:
        return None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url % tok, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                d = json.loads(r.read().decode("utf-8", "replace"))
            n = count_jobs(ats, d)
            return dict(rec, n=n) if n else None
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return None                 # board does not exist; do not retry
            if e.code == 429:               # rate limited: back off, then retry
                time.sleep(2.0 * (attempt + 1) + random.random())
                continue
            return None
        except Exception:
            time.sleep(0.5 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cands")
    ap.add_argument("out")
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--known", default="rescan_nonwd.json",
                    help="existing targets; already-known tokens are skipped")
    a = ap.parse_args()

    cands = json.load(open(os.path.join(HERE, a.cands), encoding="utf-8"))
    known = set()
    kp = os.path.join(HERE, a.known)
    if os.path.exists(kp):
        # wd_targets_full.json carries no "ats" key - it is all Workday - so the
        # ats is inferred from the candidate set rather than demanded of the file
        dflt = cands[0]["ats"] if cands else None
        known = {(t.get("ats") or dflt, (t.get("token") or "").lower())
                 for t in json.load(open(kp, encoding="utf-8"))}
    todo = [c for c in cands if (c["ats"], c["token"].lower()) not in known]
    print("%d candidates, %d already known, %d to check"
          % (len(cands), len(cands) - len(todo), len(todo)), flush=True)

    live, done, t0 = [], 0, time.time()
    with cf.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for r in ex.map(probe, todo):
            done += 1
            if r:
                live.append(r)
            if done % 500 == 0:
                el = time.time() - t0
                print("  %6d/%d checked  %5d live  %4.1f/s  eta %.0f min"
                      % (done, len(todo), len(live), done / el,
                         (len(todo) - done) / max(0.1, done / el) / 60), flush=True)

    live.sort(key=lambda r: (r["ats"], r["token"]))
    json.dump([{"company": r["token"], "ats": r["ats"], "token": r["token"]}
               for r in live], open(os.path.join(HERE, a.out), "w"), indent=1)
    print()
    print("live boards found: %d of %d checked (%.1f%%) in %.1f min"
          % (len(live), len(todo), 100 * len(live) / max(1, len(todo)),
             (time.time() - t0) / 60))
    import collections
    for k, v in sorted(collections.Counter(r["ats"] for r in live).items()):
        print("  %-16s %5d" % (k, v))
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
