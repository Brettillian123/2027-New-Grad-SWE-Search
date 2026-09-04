"""iCIMS board fetcher.

The classic board hosts (careers-<token>.icims.com) are ALL behind an AWS WAF
CAPTCHA challenge: every path, including /, answers HTTP 405 with the header
x-amzn-waf-action: captcha. There is no anonymous JSON on that host, and
CAPTCHAs are not something we solve.

The reachable public JSON is the iCIMS Career Sites (Jibe) front end that most
iCIMS customers run in front of the same requisitions:

    https://<host>.jibeapply.com/api/jobs?limit=100&page=N

It is anonymous, returns application/json, paginates 100/page (1-based "page";
"offset"/"from" are ignored), and carries the employer's own posted_date.
Each row echoes ats_code and client_code, and its apply_url points back at
careers-<token>.icims.com -- which is how we confirm the board really is iCIMS.
Boards on jibeapply that report a non-iCIMS ats_code (e.g. pepsico ->
"pepsico-prod-adp") are rejected so they cannot leak into the iCIMS lane.

Authoritative open-date field: posted_date (fallback create_date).
"""
import json, re, html, time, urllib.request, urllib.error
import concurrent.futures as cf

API = "https://{host}.jibeapply.com/api/jobs?limit={limit}&page={page}"
PAGE = 100
WORKERS = 4
TIMEOUT = 20
RETRY_WAIT = (1.0, 2.0)          # polite 1-2s backoff
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
      "Accept": "application/json,*/*"}

_PREFIXES = ("careers-", "career-", "uscareers-", "us-careers-", "jobs-", "job-",
             "university-", "external-", "staff-", "internal-", "main-",
             "corporate-", "global-", "ukcareers-", "non-clinical-", "clinical-",
             "students-", "student-", "apply-", "hiring-", "talent-")
_SUFFIXES = ("-careers", "-jobs", "careers", "jobs")

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n{3,}")
_MONEY = re.compile(r"\$\s?([\d,]{4,12})(?:\.\d\d)?\s*(?:-|to|–|—)\s*"
                    r"\$?\s?([\d,]{4,12})(?:\.\d\d)?", re.I)
_REMOTE = re.compile(r"\b(remote|virtual|work from home|telework|telecommut)", re.I)


class Throttled(Exception):
    """Raised when the board answers 429 repeatedly."""


# ---------------------------------------------------------------- transport
def _get(url, tries=3):
    """GET JSON. Polite 1-2s backoff. Raises Throttled after repeated 429s."""
    last, throttles = None, 0
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                throttles += 1
                if throttles >= 2:            # stop early on repeated 429s
                    raise Throttled(url) from e
                time.sleep(RETRY_WAIT[1] * (i + 2))
                continue
            if 400 <= e.code < 500 and e.code != 408:
                raise                          # 403/404 -> not this host
            time.sleep(RETRY_WAIT[i % 2])
        except Exception as e:
            last = e
            time.sleep(RETRY_WAIT[i % 2])
    raise last


# ---------------------------------------------------------------- helpers
def _candidates(token):
    """iCIMS token -> ordered jibeapply host guesses."""
    t = (token or "").strip().lower()
    t = re.sub(r"^https?://", "", t).split(".")[0].strip("/")
    out = [t]
    for p in _PREFIXES:
        if t.startswith(p) and len(t) > len(p) + 1:
            out.append(t[len(p):])
    for base in list(out):
        for s in _SUFFIXES:
            if base.endswith(s) and len(base) > len(s) + 2:
                out.append(base[:-len(s)].strip("-"))
    seen, res = set(), []
    for c in out:
        c = c.strip("-")
        if c and c not in seen:
            seen.add(c)
            res.append(c)
    return res


def _strip(s):
    """HTML -> readable plain text."""
    if not s:
        return ""
    s = re.sub(r"(?i)<br\s*/?>", "\n", s)
    s = re.sub(r"(?i)</(p|div|li|tr|h[1-6])>", "\n", s)
    s = re.sub(r"(?i)<li[^>]*>", "\n- ", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = s.replace("\xa0", " ")
    s = _WS.sub(" ", s)
    s = _NL.sub("\n\n", s)
    return "\n".join(ln.strip() for ln in s.split("\n")).strip()


def _iso(v):
    if not v:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(v))
    return m.group(0) if m else None


def _money(v):
    """Annual USD int, or None. Rejects 0/placeholder and hourly-looking values."""
    try:
        n = float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n < 1000:            # an hourly rate, not an annual figure
        return None
    return int(round(n))


def _salary(d, desc):
    smin = _money(d.get("salary_min_value"))
    smax = _money(d.get("salary_max_value"))
    if smin or smax:
        if smin and smax and smin > smax:
            smin, smax = smax, smin
        return smin, smax
    m = _MONEY.search(desc or "")
    if m:
        lo, hi = _money(m.group(1)), _money(m.group(2))
        if lo and hi and lo <= hi:
            return lo, hi
    return None, None


def _location(d):
    loc = ""
    for k in ("full_location", "short_location", "location_name"):
        v = (d.get(k) or "").strip()
        if v:
            loc = v
            break
    if not loc:
        loc = ", ".join(x for x in (d.get("city"), d.get("state"), d.get("country")) if x)
    ml = d.get("multipleLocations")
    if isinstance(ml, list) and len(ml) > 1:
        extra = [str(x) for x in ml if isinstance(x, str)]
        if extra:
            loc = "; ".join(dict.fromkeys(([loc] if loc else []) + extra))
    return loc or ""


def _is_remote(d, loc, title):
    if _REMOTE.search(title or "") or _REMOTE.search(loc or ""):
        return True
    # location_type ANY with no pinned city means "anywhere"
    if str(d.get("location_type", "")).upper() == "ANY" and not (d.get("city") or "").strip():
        return True
    return False


def _url(d, host):
    a = (d.get("apply_url") or "").strip()
    if "icims.com" in a:
        # canonical public posting URL: .../jobs/<id>/job
        m = re.match(r"(https://[^/]+\.icims\.com/jobs/\d+)/", a)
        if m:
            return m.group(1) + "/job"
        return a
    slug = d.get("slug") or d.get("req_id")
    if slug:
        return f"https://{host}.jibeapply.com/jobs/{slug}"
    return a


def _row(d, host):
    title = (d.get("title") or "").strip()
    loc = _location(d)
    desc = _strip(" \n".join(x for x in (d.get("description"),
                                         d.get("responsibilities"),
                                         d.get("qualifications")) if x))[:9000]
    smin, smax = _salary(d, desc)
    return {
        "title":  title,
        "loc":    loc,
        "desc":   desc,
        "opened": _iso(d.get("posted_date")) or _iso(d.get("create_date")),
        "url":    _url(d, host),
        "remote": _is_remote(d, loc, title),
        "smin":   smin,
        "smax":   smax,
    }


def _resolve(token):
    """token -> (host, first_page_json). Raises LookupError if no iCIMS board."""
    err = None
    for host in _candidates(token):
        try:
            d = _get(API.format(host=host, limit=PAGE, page=1))
        except Throttled:
            raise
        except Exception as e:
            err = e
            continue
        jobs = d.get("jobs") or []
        if not jobs:
            continue
        ats = str((jobs[0].get("data") or {}).get("ats_code") or "").lower()
        if ats != "icims":
            err = ValueError("%s: board is ats_code=%r, not icims" % (host, ats))
            continue
        return host, d
    raise LookupError("no public iCIMS/Jibe board for token %r%s"
                      % (token, " (%s)" % err if err else ""))


# ---------------------------------------------------------------- public API
def fetch(token):
    """-> list of dicts"""
    host, first = _resolve(token)
    rows = [_row(j.get("data") or {}, host) for j in (first.get("jobs") or [])]

    total = first.get("totalCount") or first.get("count") or len(rows)
    pages = list(range(2, (int(total) + PAGE - 1) // PAGE + 1))
    if not pages:
        return rows

    stop = False

    def grab(p):
        nonlocal stop
        if stop:
            return []
        try:
            d = _get(API.format(host=host, limit=PAGE, page=p))
        except Throttled:
            stop = True                       # stop early on repeated 429s
            return []
        except Exception:
            return []
        return [_row(j.get("data") or {}, host) for j in (d.get("jobs") or [])]

    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for chunk in ex.map(grab, pages):
            rows.extend(chunk)

    seen, out = set(), []
    for r in rows:
        k = r["url"] or (r["title"], r["loc"])
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


if __name__ == "__main__":
    import sys
    for t in (sys.argv[1:] or ["careers-peraton"]):
        try:
            rs = fetch(t)
            print("%s: %d postings" % (t, len(rs)))
            for r in rs[:2]:
                print("   ", r["opened"], "|", r["title"][:50], "|", r["loc"][:30])
        except Exception as e:
            print("%s: FAILED %s: %s" % (t, type(e).__name__, e))
