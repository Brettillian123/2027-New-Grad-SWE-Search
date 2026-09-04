"""Eightfold (<company>.eightfold.ai) job-board fetcher.

Endpoints used (both public, anonymous, JSON -- no HTML scraping of job data):

  LIST   https://<token>.eightfold.ai/api/pcsx/search
             ?domain=<domain>&start=<n>&num=10&sort_by=timestamp
         -> {"data": {"count": N, "positions": [{id, name, locations,
                                                 postedTs, creationTs,
                                                 workLocationOption, ...}]}}
         Page size is server-pinned at 10 regardless of `num`.
         `sort_by=timestamp` orders newest-posted first.
         Legacy tenants answer on /api/apply/v2/jobs (same params, "positions"
         at the top level); tried as a fallback.

  DETAIL https://<token>.eightfold.ai/api/apply/v2/jobs/<id>?domain=<domain>
         -> {name, location(s), job_description (HTML), t_create, t_update,
             canonicalPositionUrl, work_location_option, custom_JD{...}}

AUTHORITATIVE DATE: the list row's `postedTs` (unix seconds) is the employer's
own "Posted Date" -- verified against the tenant-defined custom_JD fields
(Starbucks "postedDate", Boston Scientific "posteddate", Qualcomm
"job_posting_date"), which agree with it. custom_JD wins when present.
`t_create` is the Eightfold record-creation time and can be months older than
the date the employer publishes, so it is only a last resort.

Eightfold boards are enterprise-sized (Starbucks: ~21,900 live postings) and the
list carries no description, so -- like the Rippling fetcher in ats.py -- this
pages the newest postings, keeps titles that could plausibly be software roles,
and spends detail calls only on those.
"""
import concurrent.futures as cf
import gzip
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept": "application/json,text/plain,*/*",
      "Accept-Encoding": "gzip, deflate"}

WORKERS      = 2     # max concurrent requests (be polite)
MIN_GAP      = 0.45  # seconds between any two requests, process-wide
RECENT_PAGES = 20    # newest-first pages of 10 -> 200 most recent postings
QUERY_PAGES  = 5     # extra pages per keyword probe
QUERIES      = ("software engineer", "software developer")
MAX_DETAIL   = 40    # cap on per-job detail calls
RETRY_SLEEP  = 1.5   # seconds between retries
BLOCK_SLEEP  = 20    # seconds to wait out an edge (CloudFront) rate block
TRIES        = 3
TIMEOUT      = 25

# Eightfold sits behind CloudFront with a rate-based WAF rule. Bursting ~4
# concurrent requests across several boards trips it, and it then answers every
# request with an HTML "Request blocked" 403 for a few minutes. Hence the
# process-wide spacing below, 2 workers, and the block-aware backoff in _raw.
_GAP_LOCK = threading.Lock()
_LAST = [0.0]


def _pace():
    with _GAP_LOCK:
        wait = _LAST[0] + MIN_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _LAST[0] = time.monotonic()

# only spend detail calls on titles that could possibly be software roles
SWE = re.compile(r"(software|engineer|developer|backend|back[\s-]end|full[\s-]?stack|"
                 r"platform|infrastructure|data engineer|machine learning|ml engineer|"
                 r"ai engineer|systems|automation|sde|swe|technolog|programmer|"
                 r"quantitative develop)", re.I)
EXCLUDE = re.compile(r"(field service|sales|account exec|recruit|technician|nurse|"
                     r"barista|store manager|shift supervisor|warehouse|driver)", re.I)


class _RateLimited(Exception):
    pass


class _Budget:
    """Trips after repeated 429s so a whole board stops hammering the host."""

    def __init__(self, limit=3):
        self.limit = limit
        self.hits = 0
        self.lock = threading.Lock()

    def note_429(self):
        with self.lock:
            self.hits += 1
            return self.hits >= self.limit

    @property
    def tripped(self):
        with self.lock:
            return self.hits >= self.limit


def _throttled(e):
    """True if this HTTPError is edge rate-limiting rather than a real API
    answer. The API always replies JSON; CloudFront's block page is HTML."""
    if e.code == 429:
        return True
    if e.code != 403:
        return False
    if "cloudfront" in (e.headers.get("Server", "") or "").lower():
        return True
    ct = (e.headers.get("Content-Type", "") or "").lower()
    return "html" in ct


def _raw(url, budget=None, timeout=TIMEOUT, tries=TRIES):
    """GET -> bytes. Retries transient errors; raises _RateLimited once the
    host has rate-blocked us repeatedly, so callers can stop early."""
    last = None
    for i in range(tries):
        if budget is not None and budget.tripped:
            raise _RateLimited("rate-limit budget exhausted")
        _pace()
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                b = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    b = gzip.decompress(b)
                return b
        except urllib.error.HTTPError as e:
            if _throttled(e):
                if budget is not None and budget.note_429():
                    raise _RateLimited("repeatedly rate-blocked by the host")
                time.sleep(BLOCK_SLEEP * (i + 1))
                last = e
                continue
            if e.code in (400, 401, 403, 404):
                raise                      # real API answer, don't retry
            last = e
        except Exception as e:             # timeouts, resets, DNS
            last = e
        time.sleep(RETRY_SLEEP * (i + 1))
    raise last


def _get_json(url, budget=None, **kw):
    return json.loads(_raw(url, budget, **kw).decode("utf-8", "replace"))


_DOMAINS = {}
_DOMAIN_LOCK = threading.Lock()


def _domain(token):
    """The tenant's configured `domain` param, read once from its careers page
    config blob (config discovery only -- no job data is scraped from HTML)."""
    with _DOMAIN_LOCK:
        if token in _DOMAINS:
            return _DOMAINS[token]
    dom = None
    try:
        html = _raw("https://%s.eightfold.ai/careers" % token).decode("utf-8", "replace")
        m = (re.search(r'&#34;domain&#34;:\s*&#34;([a-z0-9.\-]+)&#34;', html, re.I)
             or re.search(r'"domain"\s*:\s*"([a-z0-9.\-]+)"', html, re.I))
        if m:
            dom = m.group(1)
    except Exception:
        pass
    dom = dom or token + ".com"
    with _DOMAIN_LOCK:
        _DOMAINS[token] = dom
    return dom


def _iso(ts):
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        if not ts:
            return None
        if ts > 1e11:
            ts = ts / 1000.0
        try:
            return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")
        except Exception:
            return None
    s = str(ts)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    m = re.match(r"([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})", s)  # "Aug 31, 2026"
    if m:
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime("%s %s %s" % (m.group(1)[:9], m.group(2),
                                                       m.group(3)), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2)))
    return None


def _flat(v):
    """custom_JD values arrive as str, [str] or [[str]]."""
    while isinstance(v, (list, tuple)) and v:
        v = v[0]
    return v if isinstance(v, str) else None


DATE_KEY = re.compile(r"post.*date|date.*post|publish", re.I)
PAY_KEY = re.compile(r"pay|salary|compensation|wage", re.I)
MONEY = re.compile(r"\$\s?([\d,]{3,})(?:\.\d+)?\s*(?:k\b)?\s*(?:-|–|—|to)\s*"
                   r"\$?\s?([\d,]{3,})(?:\.\d+)?\s*(k\b)?", re.I)


def _custom_date(cjd):
    fields = (cjd or {}).get("data_fields") or {}
    for k, v in fields.items():
        if DATE_KEY.search(k):
            d = _iso(_flat(v))
            if d:
                return d
    return None


def _salary(cjd, text):
    """Annual USD floor/ceiling if the employer published one."""
    cands = []
    fields = (cjd or {}).get("data_fields") or {}
    for k, v in fields.items():
        if PAY_KEY.search(k):
            s = _flat(v)
            if s:
                cands.append(s)
    cands.append(text[:9000])
    for s in cands:
        for m in MONEY.finditer(s):
            lo = int(m.group(1).replace(",", ""))
            hi = int(m.group(2).replace(",", ""))
            if m.group(3) and lo < 1000:
                lo, hi = lo * 1000, hi * 1000
            tail = s[m.end():m.end() + 40].lower()
            if re.search(r"per hour|/ ?hour|hourly|an hour", tail):
                lo, hi = lo * 2080, hi * 2080
            if 15000 <= lo <= hi <= 2000000:
                return lo, hi
    return None, None


TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t\r\f\v]+")
ENT = {"&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
       "&#39;": "'", "&rsquo;": "'", "&ldquo;": '"', "&rdquo;": '"', "&ndash;": "-",
       "&mdash;": "-", "&bull;": "-"}


def _strip(html):
    s = str(html or "")
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<(br|/p|/div|/li|/tr|/h\d)[^>]*>", "\n", s)
    s = TAG.sub(" ", s)
    for a, b in ENT.items():
        s = s.replace(a, b)
    s = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), s)
    s = WS.sub(" ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    return s.strip()[:9000]


REMOTE = re.compile(r"\bremote\b|\bwork from home\b|\banywhere\b|\bvirtual\b", re.I)


def _pages(token, dom, budget, query=None, pages=RECENT_PAGES):
    """Newest-first pages of the pcsx search endpoint -> raw position dicts."""
    out, seen = [], set()
    stop = threading.Event()

    def one(start):
        if stop.is_set() or budget.tripped:
            return []
        q = {"domain": dom, "start": start, "num": 10, "sort_by": "timestamp"}
        if query:
            q["query"] = query
        url = "https://%s.eightfold.ai/api/pcsx/search?%s" % (token, urllib.parse.urlencode(q))
        try:
            d = _get_json(url, budget)
        except _RateLimited:
            stop.set()
            return []
        except urllib.error.HTTPError:
            if start == 0:
                raise                       # tenant not on pcsx -> caller falls back
            return []
        except Exception:
            return []
        ps = ((d.get("data") or {}) if isinstance(d, dict) else {}).get("positions") or []
        if not ps:
            stop.set()
        return ps

    first = one(0)
    if not first:
        return out
    for p in first:
        if p.get("id") not in seen:
            seen.add(p["id"])
            out.append(p)
    starts = [i * 10 for i in range(1, pages)]
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for ps in ex.map(one, starts):
            for p in ps:
                if p.get("id") not in seen:
                    seen.add(p["id"])
                    out.append(p)
    return out


def _legacy_pages(token, dom, budget, pages=RECENT_PAGES):
    """Older tenants: /api/apply/v2/jobs, positions at the top level."""
    out, seen = [], set()
    for i in range(pages):
        if budget.tripped:
            break
        url = ("https://%s.eightfold.ai/api/apply/v2/jobs?%s"
               % (token, urllib.parse.urlencode({"domain": dom, "start": i * 10,
                                                 "num": 10, "sort_by": "timestamp"})))
        try:
            d = _get_json(url, budget)
        except Exception:
            break
        ps = d.get("positions") or []
        if not ps:
            break
        for p in ps:
            if p.get("id") not in seen:
                seen.add(p["id"])
                out.append(p)
    return out


def fetch(token):
    """-> list of dicts

    Keys: title, loc, desc, opened ('YYYY-MM-DD' or None), url, remote,
    smin, smax.
    """
    dom = _domain(token)
    budget = _Budget(limit=3)

    try:
        rows = _pages(token, dom, budget)
    except (urllib.error.HTTPError, _RateLimited):
        rows = []
    seen = {p.get("id") for p in rows}
    if rows:
        for q in QUERIES:
            if budget.tripped:
                break
            try:
                for p in _pages(token, dom, budget, query=q, pages=QUERY_PAGES):
                    if p.get("id") not in seen:
                        seen.add(p["id"])
                        rows.append(p)
            except Exception:
                pass
    else:
        rows = _legacy_pages(token, dom, budget)

    if not rows:
        return []

    cand = [p for p in rows
            if p.get("name") and SWE.search(p["name"]) and not EXCLUDE.search(p["name"])]
    cand.sort(key=lambda p: -(p.get("postedTs") or 0))
    cand = cand[:MAX_DETAIL]

    def one(p):
        jid = p.get("id")
        loc = "; ".join(x for x in (p.get("locations") or []) if x) or p.get("location") or ""
        opened = _iso(p.get("postedTs")) or _iso(p.get("creationTs"))
        url = "https://%s.eightfold.ai/careers/job/%s" % (token, jid)
        wlo = (p.get("workLocationOption") or "") + " " + str(p.get("locationFlexibility") or "")
        d = {}
        if not budget.tripped:
            try:
                d = _get_json("https://%s.eightfold.ai/api/apply/v2/jobs/%s?domain=%s"
                              % (token, jid, dom), budget, timeout=20, tries=2)
            except Exception:
                d = {}
        if d:
            locs = [x for x in (d.get("locations") or []) if x] or \
                   ([d.get("location")] if d.get("location") else [])
            if locs:
                loc = "; ".join(locs)
            url = d.get("canonicalPositionUrl") or url
            wlo += " " + (d.get("work_location_option") or "") + " " + \
                   str(d.get("location_flexibility") or "")
        desc = _strip(d.get("job_description"))
        cjd = d.get("custom_JD") or {}
        opened = _custom_date(cjd) or opened or _iso(d.get("t_update")) or _iso(d.get("t_create"))
        smin, smax = _salary(cjd, desc)
        return dict(title=(d.get("name") or p.get("name") or "").strip(),
                    loc=loc,
                    desc=desc,
                    opened=opened,
                    url=url,
                    remote=bool(REMOTE.search(wlo) or REMOTE.search(loc)),
                    smin=smin, smax=smax)

    out = []
    with cf.ThreadPoolExecutor(max_workers=WORKERS) as ex:
        for r in ex.map(one, cand):
            out.append(r)
    return out
