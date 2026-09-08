"""Workday scanner. token format: host|tenant|site  e.g.
salesforce.wd12.myworkdayjobs.com|salesforce|External_Career_Site"""
import json, re, sys, time, urllib.request, concurrent.futures as cf
from ats import iso, classify, UA

QUERIES = ["new grad software engineer", "graduate software engineer",
           "entry level software engineer", "software engineer 2027"]

def post(url, body, timeout=30, tries=4):
    last=None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode(),
                headers={**UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8","replace"))
        except Exception as e:
            last=e
            code=getattr(e,"code",None)
            time.sleep((6.0 if code==429 else 1.5)*(i+1))
    raise last

def getj(url, timeout=25, tries=3):
    last=None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8","replace"))
        except Exception as e:
            last=e
            code=getattr(e,"code",None)
            time.sleep(5.0 if code==429 else 1.0)
    raise last

def scan_wd(name, token):
    try:
        host, tenant, site = token.split("|")
    except ValueError:
        return dict(company=name, ats="workday", token=token, error="bad token", jobs=[])
    base = f"https://{host}/wday/cxs/{tenant}/{site}"
    found, total = {}, 0
    try:
        for q in QUERIES:
            for off in (0, 20):
                d = post(f"{base}/jobs", {"appliedFacets":{}, "limit":20, "offset":off, "searchText":q})
                ps = d.get("jobPostings", [])
                total += len(ps)
                for p in ps:
                    found[p.get("externalPath","")] = p
                if len(ps) < 20: break
    except Exception as e:
        if not found:
            return dict(company=name, ats="workday", token=token, error=f"{type(e).__name__}: {str(e)[:100]}", jobs=[])
    # pre-filter on title before spending detail calls
    cands = [p for p in found.values() if p.get("title") and classify(
        dict(title=p["title"], loc=p.get("locationsText",""), desc="", opened=None)) is not None]
    hits = []
    def detail(p):
        try:
            ep = p["externalPath"];  ep = ep if ep.startswith("/job/") else "/job"+ep
            d = getj(base + ep).get("jobPostingInfo", {})
        except Exception:
            d = {}
        return dict(title=p["title"], loc=d.get("location") or p.get("locationsText",""),
            opened=iso(d.get("startDate")), updated=iso(d.get("startDate")),
            url=f"https://{host}/en-US/{site}" + p["externalPath"],
            desc=re.sub("<[^>]+>", " ", d.get("jobDescription","") or "")[:9000],
            smin=None, smax=None, ats="workday",
            remote="remote" in (d.get("remoteType","") or "").lower(),
            posted_rel=p.get("postedOn",""))
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        for j in ex.map(detail, cands[:25]):
            c = classify(j)
            if c:
                c["desc"] = (c.get("desc") or "")[:1200]
                hits.append(c)
    return dict(company=name, ats="workday", token=token, total=len(found), jobs=hits)

if __name__ == "__main__":
    targets = json.load(open(sys.argv[1]))
    out = []
    with cf.ThreadPoolExecutor(max_workers=7) as ex:
        futs = [ex.submit(scan_wd, t["company"], t["token"]) for t in targets]
        for f in cf.as_completed(futs):
            try: r = f.result()
            except Exception as e:
                print('FATAL', str(e)[:80], file=sys.stderr); continue
            out.append(r)
            print(f"{r['company']:30s} {r.get('error') or str(len(r['jobs']))+'/'+str(r.get('total',0))}", file=sys.stderr)
            if len(out) % 15 == 0:
                json.dump(out, open(sys.argv[2], "w"), indent=1)
    json.dump(out, open(sys.argv[2], "w"), indent=1)
    print('WROTE', len(out), file=sys.stderr)
