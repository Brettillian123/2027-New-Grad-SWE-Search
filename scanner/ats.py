"""Multi-ATS scanner: pulls live postings straight from company ATS APIs.
Authoritative open-date fields: greenhouse.first_published, lever.createdAt,
ashby.publishedAt, smartrecruiters.releasedDate, workable.published_on."""
import json, re, sys, time, urllib.request, urllib.error, concurrent.futures as cf
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept": "application/json,text/plain,*/*"}

def get(url, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            last = e
            time.sleep(1.2 * (i + 1))
    raise last

def iso(ts):
    if ts is None: return None
    if isinstance(ts, (int, float)):
        if ts > 1e11: ts = ts / 1000.0
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
    s = str(ts)
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    return m.group(1) if m else None

# ---------- per-ATS fetchers -> normalized dicts ----------
def gh(tok):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs?content=true")
    out = []
    for j in d.get("jobs", []):
        out.append(dict(title=j.get("title",""), loc=(j.get("location") or {}).get("name",""),
            opened=iso(j.get("first_published")), updated=iso(j.get("updated_at")),
            url=j.get("absolute_url",""), desc=j.get("content","") or "",
            smin=None, smax=None, ats="greenhouse"))
    return out

def lever(tok):
    d = get(f"https://api.lever.co/v0/postings/{tok}?mode=json")
    if not isinstance(d, list): raise ValueError("lever: not a list")
    out = []
    for j in d:
        c = j.get("categories") or {}
        out.append(dict(title=j.get("text",""), loc=c.get("location","") or "",
            opened=iso(j.get("createdAt")), updated=iso(j.get("createdAt")),
            url=j.get("hostedUrl",""), desc=(j.get("descriptionPlain","") or "") + " " +
                " ".join((l.get("text","") or "") + " " + str(l.get("content","")) for l in (j.get("lists") or [])),
            smin=None, smax=None, ats="lever"))
    return out

def ashby(tok):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{tok}?includeCompensation=true")
    out = []
    for j in d.get("jobs", []):
        smin = smax = None
        comp = j.get("compensation") or {}
        for c in (comp.get("summaryComponents") or []):
            if c.get("compensationType") == "Salary" and c.get("interval") == "1 YEAR":
                smin, smax = c.get("minValue"), c.get("maxValue")
        locs = [j.get("location","") or ""] + [s.get("location","") or "" for s in (j.get("secondaryLocations") or [])]
        out.append(dict(title=j.get("title","").strip(), loc="; ".join(x for x in locs if x),
            opened=iso(j.get("publishedAt")), updated=iso(j.get("publishedAt")),
            url=j.get("jobUrl","") or j.get("applyUrl",""), desc=j.get("descriptionPlain","") or "",
            smin=smin, smax=smax, ats="ashby",
            remote=bool(j.get("isRemote"))))
    return out

def smart(tok):
    out = []
    for off in (0, 100, 200, 300):
        d = get(f"https://api.smartrecruiters.com/v1/companies/{tok}/postings?limit=100&offset={off}")
        cont = d.get("content", [])
        if not cont: break
        for j in cont:
            loc = j.get("location") or {}
            out.append(dict(title=j.get("name",""),
                loc=f"{loc.get('city','')}, {loc.get('region','')}".strip(", "),
                opened=iso(j.get("releasedDate")), updated=iso(j.get("releasedDate")),
                url=f"https://jobs.smartrecruiters.com/{tok}/{j.get('id')}", desc="",
                smin=None, smax=None, ats="smartrecruiters",
                remote=bool(loc.get("remote"))))
        if len(cont) < 100: break
    return out

def workable(tok):
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{tok}?details=true")
    out = []
    for j in d.get("jobs", []):
        out.append(dict(title=j.get("title",""), loc=f"{j.get('city','')}, {j.get('state','')}".strip(", "),
            opened=iso(j.get("published_on") or j.get("created_at")), updated=iso(j.get("published_on")),
            url=j.get("url",""), desc=j.get("description","") or "", smin=None, smax=None, ats="workable"))
    return out

def _txt(v):
    """Rippling returns description as either HTML or a nested dict."""
    if isinstance(v, dict):
        v = v.get("html") or v.get("text") or v.get("value") or ""
    return re.sub("<[^>]+>", " ", str(v or ""))[:9000]


def rippling(tok):
    """Rippling ATS. The list endpoint carries no dates, so each candidate job is
    re-fetched for createdOn and payRangeDetails."""
    import concurrent.futures as _cf
    lst = get("https://api.rippling.com/platform/api/ats/v1/board/%s/jobs" % tok)
    if not isinstance(lst, list):
        raise ValueError("rippling: not a list")
    # only spend detail calls on titles that could possibly qualify
    cand = [j for j in lst if j.get("name") and SWE.search(j["name"])
            and not EXCLUDE.search(j["name"])][:60]
    def one(j):
        loc = (j.get("workLocation") or {}).get("label", "") or ""
        try:
            d = get("https://api.rippling.com/platform/api/ats/v1/board/%s/jobs/%s"
                    % (tok, j["uuid"]), timeout=20, tries=2)
        except Exception:
            d = {}
        locs = d.get("workLocations") or []
        if locs:
            loc = "; ".join(x.get("label", "") if isinstance(x, dict) else str(x)
                            for x in locs)
        pay = d.get("payRangeDetails") or {}
        smin = smax = None
        if isinstance(pay, dict):
            smin = pay.get("min") or pay.get("minValue")
            smax = pay.get("max") or pay.get("maxValue")
            for v in (smin, smax):
                if v and v < 1000:
                    smin = smax = None
                    break
        return dict(title=j["name"], loc=loc, opened=iso(d.get("createdOn")),
                    updated=iso(d.get("createdOn")), url=j.get("url", ""),
                    desc=_txt(d.get("description")),
                    smin=smin, smax=smax, ats="rippling")
    out = []
    with _cf.ThreadPoolExecutor(max_workers=6) as ex:
        for r in ex.map(one, cand):
            out.append(r)
    return out

FETCH = {"greenhouse": gh, "lever": lever, "ashby": ashby,
         "smartrecruiters": smart, "workable": workable, "rippling": rippling}

# ---------- filters ----------
NG_TITLE = re.compile(r"(new\s*grad|newgrad|university\s*grad|college\s*grad|recent\s*grad|"
    r"early\s*(career|talent|professional)|entry[\s-]*level|\bcampus\b|"
    r"grad(uate)?\s+(software|engineer|developer|program|rotational|scheme)|"
    r"\b(swe|sde|software engineer|engineer|developer)\s*[,\s-]*(i|1)\b|"
    r"\bassociate\s+(software|engineer|developer|backend|full)|"
    r"\bjunior\b|\bjr\.?\s|rotational\s*(program|engineer)|"
    r"20 ?27\b|class of 2027|\bnew college)", re.I)
NG_BODY = re.compile(r"(new\s*grad|recent\s*graduate|graduating\s+(in\s+)?(20 ?27|20 ?26)|"
    r"class of 20 ?27|expected graduation|degree\s+(by|between|in)\s+.{0,25}20 ?27|"
    r"final year (student|of)|0[\s-]*(to|-)\s*2 years|"
    r"less than (one|two|1|2) years? of|entry[\s-]level|early career|"
    r"university graduate|graduating student|no prior professional experience)", re.I)
SWE = re.compile(r"(software|engineer|developer|backend|back[\s-]end|full[\s-]?stack|platform|"
    r"infrastructure|data engineer|machine learning|ml engineer|ai engineer|"
    r"systems|automation|sde|swe|technolog|programmer|quantitative develop)", re.I)
EXCLUDE = re.compile(r"(intern\b|internship|\bco[\s-]?op\b|\bphd\b|principal|\bstaff\b|"
    r"senior|\bsr\.?\b|\blead\b|manager|director|\bvp\b|head of|"
    r"recruit|sales|marketing|account exec|designer|\bux\b|ui/ux|technical writer|"
    r"support engineer|solutions? (architect|engineer|consultant)|field engineer|"
    r"customer success|hardware|mechanical|electrical|firmware|asic|chip design|"
    r"silicon|analog|technician|\bqa\b|quality assurance|sdet|"
    r"fellows? program|residency|apprentice|\bii\b|\biii\b|\biv\b|teacher|"
    r"professor|instructor|part[\s-]time|fellowship|\bintern\b)", re.I)
FRONTEND = re.compile(r"(front[\s-]?end|frontend|\bios\b|android\b|mobile (engineer|developer)|"
    r"web designer|react native|flutter|\bui engineer)", re.I)
AIML = re.compile(r"(\bai\b|artificial intelligence|machine learning|\bml\b|\bllm\b|genai|"
    r"generative|automation|\bagent|data platform|deep learning|\bnlp\b)", re.I)
LOCOK = re.compile(r"(remote|anywhere|chicago|illinois|\bil\b|united states|\bus\b|\busa\b|"
    r"distributed|virtual|multiple locations|various|nationwide)", re.I)
LOCBAD = re.compile(r"(india|bangalore|hyderabad|pune|london|dublin|berlin|paris|tokyo|"
    r"singapore|sydney|toronto|vancouver|tel aviv|israel|poland|warsaw|krakow|"
    r"amsterdam|zurich|munich|belgrade|serbia|romania|bucharest|brazil|"
    r"mexico|costa rica|philippines|manila|china|beijing|shanghai|seoul|taipei|"
    r"\buk\b|england|scotland|canada|ontario|australia|japan|korea|germany|spain|"
    r"madrid|barcelona|portugal|lisbon|italy|sweden|denmark|norway|finland|dubai|uae)", re.I)
SENIOR_BODY = re.compile(r"(\b[5-9]\+? years|\b1[0-9]\+? years|minimum of (five|six|seven|eight|ten))", re.I)

DISCIPLINE_BAD = re.compile(r"(propulsion|weld|manufactur|facilit|structural|fluids|launch|"
    r"paint|avionics|stage development|thermal|aerodynam|composite|machinist|"
    r"civil|chemical engineer|industrial engineer|process engineer|nurse|clinical|"
    r"pharmac|biolog|geolog|petroleum|mining|drilling|construction|hvac|"
    r"packaging|quality engineer|safety engineer|validation engineer|"
    r"automotive|vehicle|battery|optic|photonic|laser|antenna|microwave|"
    r"power systems|substation|turbine|flight|spacecraft|propellant|"
    r"piping|pcb|signal integrity|\btest engineer|design developer|"
    r"field service|field applications|equipment engineer|\bit \b|\bdba\b|"
    r"roadway|traction power|geotechnical|highway|mbse|model based systems|"
    r"components engineer|verification engineer|layout engineer|\bcad\b|"
    r"piping design|mineral|mining engineer|"
    r"water|wastewater|environmental|\bnoc \b|network operations|"
    r"user management|specialist|survey|landscape|architectural|"
    r"structural design|bridge|transportation|traffic|utility|"
    r"plant engineer|energy engineer|sustainability)", re.I)

def classify(j):
    t = (j.get("title") or "").strip()
    if not t or EXCLUDE.search(t) or DISCIPLINE_BAD.search(t): return None
    if not SWE.search(t): return None
    body = (j.get("desc") or "")[:9000]
    tierA = bool(NG_TITLE.search(t))
    tierB = bool(NG_BODY.search(body))
    if not (tierA or tierB): return None
    if not tierA and SENIOR_BODY.search(body): return None
    loc = j.get("loc") or ""
    return dict(j, tier="A" if tierA else "B",
        frontend=bool(FRONTEND.search(t)),
        ai=bool(AIML.search(t) or AIML.search(body[:3000])),
        loc_us=bool(LOCOK.search(loc)) or bool(j.get("remote")),
        loc_foreign_only=bool(LOCBAD.search(loc)) and not LOCOK.search(loc))

def scan(name, ats, tok):
    try:
        jobs = FETCH[ats](tok)
    except Exception as e:
        return dict(company=name, ats=ats, token=tok, error=f"{type(e).__name__}: {str(e)[:120]}", jobs=[])
    import openelig  # local import: openelig imports this module
    hits = []
    for j in jobs:
        tier, floor, stretch = openelig.eligibility4(j)
        if not tier:
            continue
        c = classify(j) or {}
        loc = j.get("loc") or ""
        h = dict(j)
        h.update(tier=tier, floor=floor, stretch=stretch,
                 frontend=bool(FRONTEND.search(j.get("title") or "")),
                 ai=bool(AIML.search(j.get("title") or "")
                         or AIML.search((j.get("desc") or "")[:3000])),
                 loc_us=bool(LOCOK.search(loc)) or bool(j.get("remote")),
                 loc_foreign_only=bool(LOCBAD.search(loc)) and not LOCOK.search(loc))
        # pull pay from the FULL description before truncating: bands sit at the end
        if not h.get("smax"):
            try:
                import sal as _sal
                lo, hi = _sal.extract(j.get("desc") or "")
                if hi:
                    h["smin"], h["smax"] = lo, hi
            except Exception:
                pass
        try:
            import geo as _geo
            h["remote_body"] = _geo.remote_in_text(j.get("desc") or "")
        except Exception:
            pass
        h["desc"] = (h.get("desc") or "")[:1500]
        hits.append(h)
    return dict(company=name, ats=ats, token=tok, total=len(jobs), jobs=hits)

if __name__ == "__main__":
    targets = json.load(open(sys.argv[1]))
    out = []
    W = 32
    for _a in sys.argv[1:]:
        if _a.startswith("--workers="): W = int(_a.split("=")[1])
    with cf.ThreadPoolExecutor(max_workers=W) as ex:
        futs = {ex.submit(scan, t["company"], t["ats"], t["token"]): t for t in targets}
        for f in cf.as_completed(futs):
            r = f.result(); out.append(r)
            st = r.get("error") or f"{len(r['jobs'])}/{r.get('total',0)}"
            print(f"{r['company']:34s} {r['ats']:16s} {st}", file=sys.stderr)
            if len(out) % 50 == 0:
                json.dump(out, open(sys.argv[2], "w"))
    json.dump(out, open(sys.argv[2], "w"), indent=1)
