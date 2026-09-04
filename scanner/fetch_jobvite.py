"""Jobvite job-board fetcher.

WHY THIS SHAPE
--------------
Jobvite careersites (jobs.jobvite.com/<token>) are an Angular SPA: every path
under the token -- /api/joblist, /jobs, /search -- returns the SAME 25 KB shell,
so there is no REST list endpoint to call. api.jobvite.com/api/v2 is the keyed
partner API and answers 401 anonymously. Two anonymous machine-readable sources
do exist, and this fetcher uses both:

  1. LIST  https://app.jobvite.com/CompanyJobs/Xml.aspx?c=<companyEId>
     text/xml, one <job> per job x location, carrying id/title/location/
     category/jobtype/description/date.
  2. DATES+PAY  https://jobs.jobvite.com/<token>/job/<id>
     carries a schema.org JobPosting block in <script type="application/ld+json">
     with `datePosted` (already ISO) and a structured `baseSalary`.

The feed's own <date> is NOT the posting date -- it is a refresh/re-publish
stamp. Measured on laserfiche, every feed <date> was LATER than the JSON-LD
datePosted, and feed dates cluster on bulk-refresh days while datePosted values
are distinct and earlier:

     id         feed<date>   datePosted
     orDbAfwz   8/12/2026    2026-05-26
     oWzdAfw2   8/12/2026    2026-06-01
     o3IBAfwG   8/12/2026    2026-08-05
     oXEFzfwz   4/24/2026    2026-02-13

Trusting <date> would make every posting look fresher than it is. So `opened`
comes from JSON-LD datePosted ONLY; the feed date is never substituted for it,
and `opened` is None rather than wrong. The feed date is still returned as
`refreshed` for callers who want it -- it is not one of the required keys but
costs nothing and documents the distinction.

<companyEId> is not the URL token; it is read off the careersite page's angular
`preloadedData` constant (companyEId: 'qklaVfwu'), so fetch() is a three-hop:
token -> companyEId -> XML list -> per-job JSON-LD.

Merging: the feed emits one <job> per job x location, and secondary rows carry a
COMPOSITE id ('oYfzAfw6-CvxKVfwr' = baseid-sourceid). That composite is not a
real posting id -- /job/oYfzAfw6-CvxKVfwr returns the empty shell. Rows are
therefore merged on the base id (text before the first '-') and their locations
unioned.
"""
import html
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

BOARD = "https://jobs.jobvite.com/%s"
FEED = "https://app.jobvite.com/CompanyJobs/Xml.aspx?c=%s"
JOB_URL = "https://jobs.jobvite.com/%s/job/%s"

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,text/xml,application/json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}

# --- politeness -------------------------------------------------------------
# <=4 requests in flight, a minimum gap per host, retry twice with a 1-2s
# backoff, and a breaker that stops the run after repeated 429s.
MAX_INFLIGHT = 4
_GATE = threading.Semaphore(MAX_INFLIGHT)
_LOCK = threading.Lock()
_LAST = {}
_GAP = {"app.jobvite.com": 2.0, "jobs.jobvite.com": 0.6}
_DEFAULT_GAP = 1.0

_429 = [0]              # consecutive 429s
_429_AT = [0.0]
_429_LIMIT = 3
_429_COOLDOWN = 300.0

# per-token counters from the most recent fetch(), for callers that want to see
# how much of a feed was company-wide noise vs actually on the board
LAST_RUN = {}


class Throttled(RuntimeError):
    """Jobvite has 429'd us repeatedly; stop hammering."""


def _host(url):
    return urllib.parse.urlsplit(url).hostname or ""


def _breaker(host):
    if _429[0] >= _429_LIMIT:
        if time.time() - _429_AT[0] > _429_COOLDOWN:
            _429[0] = 0
        else:
            raise Throttled("jobvite 429 x%d on %s; stopping" % (_429[0], host))


def _pace(host):
    gap = _GAP.get(host, _DEFAULT_GAP)
    with _LOCK:
        wait = gap - (time.time() - _LAST.get(host, 0.0))
        if wait > 0:
            time.sleep(wait)
        _LAST[host] = time.time()


def get(url, timeout=60, tries=3, backoff=1.5):
    """GET -> text. Retries with a 1-2s backoff; trips the breaker on 429s."""
    host = _host(url)
    _breaker(host)
    last = None
    for i in range(tries):
        with _GATE:
            _pace(host)
            try:
                req = urllib.request.Request(url, headers=UA)
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    body = r.read()
                _429[0] = 0
                return body.decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                last = e
                if e.code == 429:
                    _429[0] += 1
                    _429_AT[0] = time.time()
                    if _429[0] >= _429_LIMIT:
                        raise Throttled("jobvite 429 x%d on %s; stopping" % (_429[0], host))
                    ra = e.headers.get("Retry-After")
                    try:
                        nap = min(120.0, float(ra))
                    except (TypeError, ValueError):
                        nap = 30.0 * (i + 1)
                    time.sleep(nap)
                    continue
                if e.code in (403, 404):
                    raise
            except Exception as e:
                last = e
        time.sleep(backoff * (i + 1))
    raise last


# --- text helpers -----------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v ]+")
_NL = re.compile(r"\n{3,}")
_ATTR = re.compile(
    r"""(?i)(?:alt|src|href|style|height|width|class|id|target|rel|title|border|
        align|valign|cellpadding|cellspacing|colspan|rowspan|data-[\w-]+)
        \s*=\s*("[^"]*"|'[^']*')""", re.X)
_IMGURL = re.compile(r"(?i)https?://\S+\.(?:png|jpe?g|gif|svg|webp|bmp|ico)\S*")


def _strip(v):
    """HTML -> plain text. The feed escapes description INTO the xml, and some
    boards escape it twice (&amp;lt;p&amp;gt;), so unescape to a fixed point
    FIRST -- then every tag is a real tag and the strip is total. Unescaping
    after the strip would resurrect markup as visible text."""
    if not v:
        return ""
    s = str(v)
    for _ in range(3):
        n = html.unescape(s)
        if n == s:
            break
        s = n
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s)
    s = re.sub(r"(?i)<(br|/p|/div|/li|/tr|/h[1-6]|/ul|/ol)\s*/?>", "\n", s)
    s = _TAG.sub(" ", s)
    # malformed markup (an <a> nested inside an img src=...) leaves attribute
    # debris behind after the tag strip; sweep the orphans and bare asset URLs
    s = _ATTR.sub(" ", s)
    s = _IMGURL.sub(" ", s)
    s = s.replace("/>", " ").replace("�", " ")
    s = _WS.sub(" ", s)
    s = _NL.sub("\n\n", s)
    return s.strip()


def _iso(v):
    """-> 'YYYY-MM-DD' or None. Handles ISO and the feed's M/D/YYYY."""
    s = (v or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%b %d, %Y", "%B %d, %Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return None


# --- remote / salary --------------------------------------------------------
_REMOTE = re.compile(r"(?i)\b(remote|work\s*from\s*home|wfh|telecommut\w*|"
                     r"virtual\s*office|home[-\s]based|anywhere)\b")
_ONSITE = re.compile(r"(?i)\b(non-?remote|not\s+remote|no\s+remote|remote\s*:\s*no|"
                     r"on-?site\s+only|100%\s+on-?site)\b")

_MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{2,7}(?:\.\d+)?|\d{2,3}(?:\.\d+)?\s?[kK])"
_RANGE = re.compile(_MONEY + r"\s*(?:-|--|–|—|to|through)\s*" + _MONEY)
_HOURLY = re.compile(r"(?i)(per\s+hour|/\s*hour|hourly|/\s*hr|an\s+hour|per\s+hr)")


def _num(tok):
    t = tok.replace(",", "").replace(" ", "")
    mult = 1
    if t and t[-1] in "kK":
        t, mult = t[:-1], 1000
    try:
        return int(round(float(t) * mult))
    except ValueError:
        return None


def _salary_from_text(text):
    """Annual USD floor/ceiling scraped from prose. (None, None) if absent."""
    if not text or "$" not in text:
        return None, None
    for m in _RANGE.finditer(text):
        head = text[max(0, m.start() - 60):m.start()]
        tail = text[m.end():m.end() + 60]
        if _HOURLY.search(head) or _HOURLY.search(tail):
            continue
        lo, hi = _num(m.group(1)), _num(m.group(2))
        if lo is None or hi is None or lo > hi:
            continue
        if 20000 <= lo <= 2000000 and 20000 <= hi <= 2000000:
            return lo, hi
    return None, None


_HOUR_UNITS = {"HOUR", "HOURLY"}
_YEAR_UNITS = {"YEAR", "YEARLY", "ANNUAL", "ANNUALLY", ""}


def _salary_from_ld(bs):
    """schema.org baseSalary -> annual USD (min, max). Jobvite emits the block
    even when unpopulated (empty-string min/max), so treat blanks as absent.
    Hourly figures are annualised at 2080h only when they look like a real wage."""
    if not isinstance(bs, dict):
        return None, None
    cur = (bs.get("currency") or "").upper()
    if cur and cur not in ("USD", "US$", "$"):
        return None, None
    val = bs.get("value")
    if not isinstance(val, dict):
        return None, None
    unit = (val.get("unitText") or "").upper()

    def n(x):
        if x in (None, ""):
            return None
        try:
            return int(round(float(str(x).replace(",", "").replace("$", ""))))
        except ValueError:
            return None

    lo, hi = n(val.get("minValue")), n(val.get("maxValue"))
    if lo is None and hi is None:
        lo = hi = n(val.get("value"))
    if lo is None and hi is None:
        return None, None
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    if lo > hi:
        lo, hi = hi, lo
    if unit in _HOUR_UNITS:
        if not (5 <= lo <= 1000):
            return None, None
        lo, hi = int(lo * 2080), int(hi * 2080)
    elif unit not in _YEAR_UNITS:
        return None, None
    if not (20000 <= lo <= 2000000 and 20000 <= hi <= 2000000):
        return None, None
    return lo, hi


# --- feed parsing -----------------------------------------------------------
def _txt(el, tag):
    n = el.find(tag)
    return (n.text or "").strip() if n is not None and n.text else ""


_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BARE_AMP = re.compile(r"&(?!(amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")


def _parse_feed(raw):
    raw = _CTRL.sub(" ", raw)
    try:
        return ET.fromstring(raw).findall(".//job")
    except ET.ParseError:
        pass
    # salvage per-<job> so one malformed posting cannot lose the whole board
    jobs = []
    for m in re.finditer(r"<job>.*?</job>", raw, re.S):
        try:
            jobs.append(ET.fromstring(_BARE_AMP.sub("&amp;", m.group(0))))
        except ET.ParseError:
            continue
    return jobs


def company_id(token):
    """token -> Jobvite companyEId, read off the careersite page."""
    page = get(BOARD % token, timeout=30)
    m = re.search(r"companyEId\s*:\s*['\"]([A-Za-z0-9]+)['\"]", page)
    if not m:
        m = re.search(r"[?&]c=([A-Za-z0-9]{8})\b", page)
    if not m:
        raise ValueError("jobvite: no companyEId on board page for %r" % token)
    return m.group(1)


_LD = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


def _job_ld(token, jid):
    """Per-job schema.org JobPosting -> dict, or {} if the page has none
    (closed postings serve the bare SPA shell)."""
    try:
        page = get(JOB_URL % (token, jid), timeout=40)
    except Exception:
        return {}
    for blk in _LD.findall(page):
        try:
            d = json.loads(blk.strip())
        except ValueError:
            try:
                d = json.loads(html.unescape(blk.strip()))
            except ValueError:
                continue
        if isinstance(d, list):
            d = next((x for x in d if isinstance(x, dict)
                      and x.get("@type") == "JobPosting"), None)
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            return d
    return {}


def _ld_locs(ld):
    out = []
    jl = ld.get("jobLocation")
    if isinstance(jl, dict):
        jl = [jl]
    for p in (jl or []):
        if not isinstance(p, dict):
            continue
        a = p.get("address")
        if not isinstance(a, dict):
            continue
        bits = [a.get("addressLocality"), a.get("addressRegion"), a.get("addressCountry")]
        s = ", ".join(x for x in bits if isinstance(x, str) and x.strip())
        if s:
            out.append(s)
    return out


# --- public -----------------------------------------------------------------
def fetch(token):
    """-> list of dicts

    keys: title, loc, desc, opened, url, remote, smin, smax
    (plus `refreshed`, the feed's own re-publish stamp -- NOT the posting date)
    """
    cid = company_id(token)
    raw = get(FEED % cid, timeout=90)
    if "<result" not in raw[:400] and "<job>" not in raw[:4000]:
        raise ValueError("jobvite: feed for %r (%s) is not the XML job feed" % (token, cid))

    # one <job> per job x location; secondary rows carry a composite
    # "<baseid>-<sourceid>" that is NOT a reachable posting id -> merge on base
    merged, order = {}, []
    for j in _parse_feed(raw):
        raw_id = _txt(j, "id")
        if not raw_id:
            continue
        base = raw_id.split("-", 1)[0]
        locs = [x for x in ((e.text or "").strip() for e in j.findall("location")) if x]
        if base in merged:
            for L in locs:
                if L not in merged[base]["locs"]:
                    merged[base]["locs"].append(L)
            continue
        order.append(base)
        merged[base] = {
            "locs": locs,
            "title": _txt(j, "title"),
            "desc": _txt(j, "description") or _txt(j, "briefdescription"),
            "refreshed": _iso(_txt(j, "date")),
            "extra": " ".join([_txt(j, "workflow"), _txt(j, "category"),
                               _txt(j, "jobtype"), _txt(j, "department")]),
        }
    if not order:
        return []

    # hop 3: the authoritative datePosted + structured pay, <=4 in flight
    with ThreadPoolExecutor(max_workers=MAX_INFLIGHT) as ex:
        lds = list(ex.map(lambda b: _job_ld(token, b), order))

    out = []
    dropped = 0
    for base, ld in zip(order, lds):
        # The XML feed is COMPANY-wide, but a careersite is per-board: a large
        # employer's feed carries postings that live on a sibling board (e.g.
        # sews ships 312 German-language reqs that are not on jobs.jobvite.com/
        # sews). Those ids serve the bare shell -- no JobPosting -- so the URL we
        # would emit is dead and the date unknowable. Drop them rather than ship
        # a broken link with opened=None.
        if not ld:
            dropped += 1
            continue
        rec = merged[base]
        desc_html = ld.get("description") or rec["desc"]
        desc = _strip(desc_html)
        title = _strip(ld.get("title") or rec["title"])

        locs = list(rec["locs"])
        for L in _ld_locs(ld):
            if L not in locs:
                locs.append(L)
        loc = "; ".join(locs)

        smin, smax = _salary_from_ld(ld.get("baseSalary"))
        if smin is None:
            smin, smax = _salary_from_text(desc)

        blob = " ".join([loc, title, rec["extra"], desc[:4000]])
        remote = bool(_REMOTE.search(blob)) and not _ONSITE.search(blob)

        out.append({
            "title": title,
            "loc": loc,
            "desc": desc[:9000],
            "opened": _iso(ld.get("datePosted")),   # employer's own field; never the feed stamp
            "url": JOB_URL % (token, base),
            "remote": remote,
            "smin": smin,
            "smax": smax,
            "refreshed": rec["refreshed"],
        })
    LAST_RUN[token] = {"feed_jobs": len(order), "kept": len(out),
                       "dropped_not_on_board": dropped}
    return out


if __name__ == "__main__":
    import sys
    for t in (sys.argv[1:] or ["laserfiche"]):
        try:
            rows = fetch(t)
            print("%-24s %d postings" % (t, len(rows)))
            print(json.dumps(rows[:2], indent=1)[:1200])
        except Exception as e:
            print("%-24s FAIL %s: %s" % (t, type(e).__name__, e))
