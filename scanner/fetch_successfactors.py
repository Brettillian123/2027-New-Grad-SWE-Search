"""SAP SuccessFactors (Recruiting Marketing / "jobs2web", RMK) career-site fetcher.

PLATFORM NOTE -- READ BEFORE TRUSTING THIS AS A "JSON API" FETCHER
-----------------------------------------------------------------
SuccessFactors exposes NO public JSON job-search API. Verified 2026-08-31:

  * The RCM OData API is the documented machine interface, but it is authenticated:
      GET https://performancemanager4.successfactors.com/odata/v2/JobRequisition?$format=json
      -> HTTP 401  "[LGN0003]Authentication information is missing.
                    Please use OAuth 2.0 to authenticate the user."
    No anonymous read. Needs a per-tenant OAuth client, so it is unusable for scanning.

  * The public career sites (career<N>.successfactors.com, jobs.sap.com, and the ~72
    vanity domains mined from the aggregator dump) run RMK/jobs2web, which is
    server-rendered HTML. Its OWN pagination call is HTML by design -- from
    /platform/js/j2w/min/j2w.searchResults.min.js:
        apiEndpoint:"tile-search-results" ... $.ajax({type:"GET", url:.../tile-search-results/?q=&startrow=N,
                                                       accept:"text/html; charset=UTF-8"})
    Requesting it with `Accept: application/json` still returns text/html.

  * Every unknown path (/api/jobs, /jobs.json, /odata/v2/..., /rss) soft-404s to the
    site's HTML shell with HTTP 200, so path-guessing cannot surface a hidden JSON API.

So this fetcher parses HTML. It is NOT scraping a rendered SPA: it reads (a) the
platform's own tile-search-results pagination endpoint and (b) the schema.org
JobPosting **microdata** that RMK stamps into every job detail page. The posting date
comes from the employer's own field:

    <meta itemprop="datePosted" content="Fri Aug 21 07:00:00 UTC 2026">

That is the authoritative RCM job-requisition posting date, not an aggregator's
"first seen". The list endpoint carries no date at all, so `opened` requires one
detail request per job -- which is why MAX_JOBS is capped by default.

TOKEN = the career-site host, e.g. "jobs.l3harris.com", "jobs.sap.com".
"""

import concurrent.futures as cf
import html
import re
import time
import urllib.error
import urllib.request

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

PAGE = 25             # rows per tile-search-results page
MAX_PAGES = 40        # hard stop on pagination
MAX_JOBS = 300        # cap detail fetches (1 request per job for the date)
WORKERS = 4           # <= 4 concurrent requests, per politeness budget
TIMEOUT = 20          # per-request socket timeout (seconds)
RETRY_WAIT = 1.5      # 1-2s backoff between retries
TRIES = 3

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


class _Stop429(Exception):
    """Raised to abort a board after repeated rate-limit responses."""


class _Budget:
    """Trips after `limit` consecutive 429/503 responses so we back off a board."""

    def __init__(self, limit=3):
        self.limit = limit
        self.hits = 0
        self.tripped = False

    def rate_limited(self):
        self.hits += 1
        if self.hits >= self.limit:
            self.tripped = True

    def ok(self):
        self.hits = 0


def _get(url, budget, tries=TRIES):
    """GET -> text. Retries with a 1.5s wait; gives up on repeated 429s."""
    last = None
    for i in range(tries):
        if budget.tripped:
            raise _Stop429("rate limited")
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read().decode("utf-8", "replace")
            budget.ok()
            return body
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (429, 503):
                budget.rate_limited()
                if budget.tripped:
                    raise _Stop429(f"HTTP {e.code} x{budget.hits}")
                time.sleep(RETRY_WAIT * (i + 2))
            elif e.code in (404, 410):
                raise
            else:
                time.sleep(RETRY_WAIT * (i + 1))
        except Exception as e:
            last = e
            time.sleep(RETRY_WAIT * (i + 1))
    raise last


def _strip(fragment):
    """HTML -> plain text."""
    s = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", fragment)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace(" ", " ").replace("�", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    return s.strip()


def _iso(raw):
    """'Fri Aug 21 07:00:00 UTC 2026' | '2026-08-21' -> '2026-08-21'."""
    if not raw:
        return None
    raw = html.unescape(raw).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if m:
        return m.group(0)
    m = re.search(r"\b([A-Z][a-z]{2})\s+(\d{1,2})\b.*?\b(\d{4})\b", raw)
    if m and m.group(1) in MONTHS:
        return "%s-%02d-%02d" % (m.group(3), MONTHS[m.group(1)], int(m.group(2)))
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", raw)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2)))
    return None


_SAL = re.compile(
    r"\$\s*([\d]{2,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?\s*[kK])"
    r"(?:\s*(?:-|–|—|to|through)\s*)"
    r"\$?\s*([\d]{2,3}(?:,\d{3})+|\d{2,3}(?:\.\d+)?\s*[kK])")


def _num(tok):
    tok = tok.strip().replace(",", "")
    if tok.lower().endswith("k"):
        return int(float(tok[:-1]) * 1000)
    return int(float(tok))


def _salary(text):
    """Annual USD floor/ceiling if published, else (None, None)."""
    for m in _SAL.finditer(text):
        try:
            lo, hi = _num(m.group(1)), _num(m.group(2))
        except Exception:
            continue
        if lo > hi:
            lo, hi = hi, lo
        # keep plausible annual bands only (filters hourly rates and stray figures)
        if 15000 <= lo <= 1200000 and 15000 <= hi <= 2000000:
            window = text[max(0, m.start() - 90):m.end() + 90].lower()
            if any(w in window for w in ("hour", "hourly", "/hr", "per hour")):
                continue
            return lo, hi
    return None, None


_REMOTE = re.compile(
    r"(?i)\b(fully remote|100% remote|remote[- ]first|work from home|telecommut|"
    r"remote position|remote role|is remote|virtual/remote|remote \(us\))\b")


def _remote(title, loc, desc):
    blob = " ".join([title or "", loc or ""])
    if re.search(r"(?i)\bremote\b", blob):
        return True
    return bool(_REMOTE.search(desc or ""))


def _tiles(host, budget):
    """Page the platform's tile-search-results endpoint -> [(url, title, loc)]."""
    seen, rows = set(), []
    base = f"https://{host}"
    for page in range(MAX_PAGES):
        url = f"{base}/tile-search-results/?q=&startrow={page * PAGE}"
        try:
            body = _get(url, budget)
        except _Stop429:
            break
        except Exception:
            break
        chunks = re.findall(r'(?is)<li class="job-tile.*?</li>', body)
        if not chunks:
            break
        new = 0
        for c in chunks:
            m = re.search(r'data-url="([^"]+)"', c)
            if not m:
                continue
            href = html.unescape(m.group(1))
            if href.startswith("/"):
                href = base + href
            if href in seen:
                continue
            seen.add(href)
            t = re.search(r'(?is)class="jobTitle-link[^"]*"[^>]*>(.*?)</a>', c)
            title = _strip(t.group(1)) if t else ""
            locs = re.findall(
                r'(?is)section-field location.*?-value">(.*?)</div>', c)
            loc = _strip(locs[0]) if locs else ""
            rows.append((href, title, loc))
            new += 1
        if new == 0 or len(rows) >= MAX_JOBS:
            break
    return rows[:MAX_JOBS]


def _detail(url, title, loc, budget):
    try:
        body = _get(url, budget)
    except _Stop429:
        raise
    except Exception:
        return None

    m = re.search(r'itemprop="datePosted"[^>]*content="([^"]*)"', body) \
        or re.search(r'"datePosted"\s*:\s*"([^"]*)"', body)
    opened = _iso(m.group(1)) if m else None

    if not loc:
        city = re.findall(r'addressLocality"\s*content="([^"]*)"', body)
        reg = re.findall(r'addressRegion"\s*content="([^"]*)"', body)
        if city:
            loc = ", ".join(x for x in [city[0], reg[0] if reg else ""] if x)

    i = body.find("jobDisplayShell")
    if i >= 0:
        j = body.find(">", i)          # skip past the rest of the opening tag
        i = j + 1 if j >= 0 else i
        seg = body[i:i + 120000]
    else:
        seg = body
    desc = _strip(seg)
    desc = re.sub(r"^\s*Apply now\s*", "", desc)
    desc = re.sub(r"^.*?Job Description:?\s*", "", desc, count=1, flags=re.S) \
        if "Job Description" in desc[:1500] else desc
    desc = desc[:9000]

    if not title:
        t = re.search(r"(?is)<title>(.*?)</title>", body)
        title = re.sub(r"\s*Job Details.*$", "", _strip(t.group(1))) if t else ""

    smin, smax = _salary(desc)
    return dict(title=title, loc=loc, desc=desc, opened=opened, url=url,
                remote=_remote(title, loc, desc), smin=smin, smax=smax)


def fetch(token):
    """-> list of dicts

    token: SuccessFactors career-site host, e.g. 'jobs.l3harris.com'.
    """
    host = re.sub(r"^https?://", "", str(token).strip()).strip("/").split("/")[0]
    budget = _Budget()

    rows = _tiles(host, budget)
    if not rows:
        return []

    out = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = {ex.submit(_detail, u, t, l, budget): u for u, t, l in rows}
        for f in cf.as_completed(futs):
            try:
                r = f.result()
            except _Stop429:
                break
            except Exception:
                continue
            if r and r["title"]:
                out.append(r)

    out.sort(key=lambda r: (r["opened"] or ""), reverse=True)
    return out


if __name__ == "__main__":
    import json
    import sys
    for tok in (sys.argv[1:] or ["jobs.l3harris.com"]):
        t0 = time.time()
        jobs = fetch(tok)
        dated = sum(1 for j in jobs if j["opened"])
        print(f"\n=== {tok}: {len(jobs)} postings, {dated} dated "
              f"({time.time() - t0:.1f}s)")
        for j in jobs[:3]:
            print(json.dumps(j | {"desc": j["desc"][:160] + "..."},
                             indent=2)[:900])
