"""Oracle Taleo + Oracle Cloud Recruiting (ORC) job-board fetcher.

Two distinct Oracle products share this module because both surface as "Taleo"
in aggregator data:

  1. Taleo classic  -- token "<host>/<careersection>", e.g. "textron/textron"
     JSON: POST https://<host>.taleo.net/careersection/rest/jobboard/searchjobs
                ?lang=en&portal=<portalNo>       body {"pageNo": N}
     The portalNo is read out of the career-section page. Requires the 'tz' /
     'tzname' headers the real UI sends, otherwise TEE answers 400.
     Authoritative date: a posting-date COLUMN, present only when the employer
     configured the board to show it (~7 of 13 live boards). No description is
     reachable anonymously -- the detail page is a stateful FTL/JS shell that
     renders nothing without a session, and there is no detail REST endpoint
     (all /rest/jobboard/*job* paths 404). desc is therefore built from the
     columns the list API does return.

  2. Oracle Cloud Recruiting -- token "<host>/<siteNumber>",
     e.g. "jpmc.fa.oraclecloud.com/CX_1001"
     JSON: GET https://<host>/hcmRestApi/resources/latest/
               recruitingCEJobRequisitions?finder=findReqs;siteNumber=<site>,...
     Authoritative date: requisitionList[].PostedDate ('YYYY-MM-DD').
     Full description via .../recruitingCEJobRequisitionDetails
               ?finder=ById;Id="<id>",siteNumber=<site>&expand=all
"""
import json, re, html, time, urllib.request, urllib.parse, urllib.error
import concurrent.futures as cf

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
H_HTML = {"User-Agent": UA, "Accept": "text/html,*/*"}
H_JSON = {"User-Agent": UA, "Accept": "application/json"}
# The faceted-search UI sends these; TEE rejects the POST without them.
H_TALEO = dict(H_JSON, **{"Content-Type": "application/json",
                          "tz": "GMT-05:00", "tzname": "America/New_York"})

MAX_WORKERS = 4          # politeness cap
TIMEOUT     = 20
RETRIES     = 2          # 1-2s backoff between attempts
DESC_CHARS  = 9000


class Blocked(Exception):
    """Raised when the board answers 429 repeatedly."""


class _Budget:
    """Trips after repeated 429s so we stop hammering a board."""
    def __init__(self, limit=3):
        self.n, self.limit = 0, limit

    def hit(self):
        self.n += 1
        return self.n >= self.limit

    def tripped(self):
        return self.n >= self.limit


def _open(req, budget=None):
    last = None
    for i in range(RETRIES + 1):
        if budget is not None and budget.tripped():
            raise Blocked("stopped after repeated 429s")
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 429:
                if budget is not None and budget.hit():
                    raise Blocked("stopped after repeated 429s")
                time.sleep(2.0)
                continue
            if e.code in (500, 502, 503, 504):
                time.sleep(1.0 + i)
                continue
            raise
        except Exception as e:
            last = e
            time.sleep(1.0 + i)
    raise last


def _get_json(url, headers=H_JSON, budget=None):
    return json.loads(_open(urllib.request.Request(url, headers=headers),
                            budget).decode("utf-8", "replace"))


def _post_json(url, body, headers=H_TALEO, budget=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    return json.loads(_open(req, budget).decode("utf-8", "replace"))


# ---------------- shared helpers ----------------
_TAG   = re.compile(r"(?s)<[^>]+>")
_BLOCK = re.compile(r"(?is)</(p|div|li|tr|h[1-6]|br)\s*>|<br\s*/?>")


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = _BLOCK.sub("\n", s)
    s = _TAG.sub(" ", s)
    s = html.unescape(s)
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n\s*\n+", "\n\n", s)
    return s.strip()


_MON = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun",
     "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def to_iso(s):
    """Taleo renders posting dates in the career section's own locale format."""
    if not s:
        return None
    s = str(s).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)                      # 2026-08-31
    if m:
        return m.group(0)
    m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s+(\d{4})$", s)   # Aug 31, 2026
    if m and m.group(1)[:3].lower() in _MON:
        return "%04d-%02d-%02d" % (int(m.group(3)), _MON[m.group(1)[:3].lower()],
                                   int(m.group(2)))
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})$", s)   # 31 Aug 2026
    if m and m.group(2)[:3].lower() in _MON:
        return "%04d-%02d-%02d" % (int(m.group(3)), _MON[m.group(2)[:3].lower()],
                                   int(m.group(1)))
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)                 # 08/31/2026 (US)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(1)), int(m.group(2)))
    return None


_DATEISH = re.compile(
    r"^(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[A-Za-z]{3,9}\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+[A-Za-z]{3,9}\.?,?\s+\d{4})$")

_REMOTE = re.compile(r"\b(remote|work from home|telecommut|virtual|anywhere)\b", re.I)
_NOTREM = re.compile(r"\b(remote\s+(?:office|site|location|area)|not\s+remote|no\s+remote)\b", re.I)


def _is_remote(*parts):
    blob = " ".join(p for p in parts if p)
    if _NOTREM.search(blob):
        return False
    return bool(_REMOTE.search(blob))


try:
    import sal as _sal
except Exception:
    _sal = None


def _salary(text):
    if not text or _sal is None:
        return (None, None)
    try:
        return _sal.extract(text)
    except Exception:
        return (None, None)


# ---------------- Taleo classic ----------------
_PORTAL_RE = [re.compile(r"portalNo\s*:\s*'(\d+)'"),
              re.compile(r"portal=(\d{6,})")]
DEFAULT_PORTAL = "101430233"   # Oracle's stock portal id, shared by many boards


def _taleo_portal(host, cs, budget=None):
    url = f"https://{host}.taleo.net/careersection/{cs}/jobsearch.ftl"
    try:
        b = _open(urllib.request.Request(url, headers=H_HTML), budget).decode("utf-8", "replace")
    except Blocked:
        raise
    except Exception:
        return DEFAULT_PORTAL
    for rx in _PORTAL_RE:
        m = rx.search(b)
        if m:
            return m.group(1)
    return DEFAULT_PORTAL


def _taleo_cols(rec):
    """Column layout is configured per career section, so classify by shape
    rather than by index: title is linkedColumn, locations arrive as a JSON
    array string, and the date is whichever cell parses as a date."""
    cols = [c if isinstance(c, str) else "" for c in (rec.get("column") or [])]
    li = rec.get("linkedColumn")
    title = cols[li] if isinstance(li, int) and 0 <= li < len(cols) else (cols[0] if cols else "")
    loc, opened, extra = "", None, []
    for i, c in enumerate(cols):
        if i == li or not c:
            continue
        if c.startswith("[") and c.endswith("]"):
            try:
                loc = ", ".join(json.loads(c))
            except Exception:
                loc = c.strip('[]"')
            continue
        iso = to_iso(c) if _DATEISH.match(c) else None
        if iso and opened is None:
            opened = iso
            continue
        extra.append(c)
    if not loc:
        flat = []
        for x in (rec.get("locationsColumns") or []):
            if isinstance(x, str):
                flat.append(x)
            elif isinstance(x, list):
                flat += [y for y in x if isinstance(y, str)]
        loc = ", ".join(flat)
    return title, loc, opened, extra


def _fetch_taleo(host, cs, limit=None):
    budget = _Budget()
    portal = _taleo_portal(host, cs, budget)
    api = (f"https://{host}.taleo.net/careersection/rest/jobboard/searchjobs"
           f"?lang=en&portal={portal}")
    base = f"https://{host}.taleo.net/careersection/{cs}/jobdetail.ftl?job="
    out, page, seen = [], 1, set()
    while True:
        try:
            d = _post_json(api, {"pageNo": page}, budget=budget)
        except Blocked:
            break
        reqs = d.get("requisitionList") or []
        if not reqs:
            break
        for rec in reqs:
            cn = rec.get("contestNo") or rec.get("jobId")
            if not cn or cn in seen:
                continue
            seen.add(cn)
            title, loc, opened, extra = _taleo_cols(rec)
            # Taleo's list API is all that is reachable anonymously.
            desc = "\n".join([x for x in [title, loc] + extra if x])
            smin, smax = _salary(desc)
            out.append(dict(title=title, loc=loc, desc=desc[:DESC_CHARS], opened=opened,
                            url=base + urllib.parse.quote(str(cn)),
                            remote=_is_remote(title, loc), smin=smin, smax=smax))
        pg = d.get("pagingData") or {}
        total = pg.get("totalCount") or 0
        size = pg.get("pageSize") or len(reqs)
        if limit and len(out) >= limit:
            break
        if not size or page * size >= total:
            break
        page += 1
        time.sleep(0.25)
    return out[:limit] if limit else out


# ---------------- Oracle Cloud Recruiting ----------------
_ORC_FACETS = ("LOCATIONS;WORK_LOCATIONS;WORKPLACE_TYPES;TITLES;CATEGORIES;"
               "ORGANIZATIONS;POSTING_DATES;FLEX_FIELDS")


def _orc_list(host, site, limit, budget):
    out, offset, page = [], 0, 200
    while True:
        take = min(page, (limit - len(out)) if limit else page)
        finder = (f"findReqs;siteNumber={site},facetsList={_ORC_FACETS},"
                  f"limit={take},sortBy=POSTING_DATES_DESC,offset={offset}")
        q = urllib.parse.urlencode({
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations,flexFieldsFacet.values",
            "finder": finder})
        url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?{q}"
        try:
            d = _get_json(url, budget=budget)
        except Blocked:
            break
        items = d.get("items") or []
        reqs = (items[0].get("requisitionList") or []) if items else []
        total = (items[0].get("TotalJobsCount") or 0) if items else 0
        if not reqs:
            break
        out += reqs
        offset += len(reqs)
        if (limit and len(out) >= limit) or offset >= total:
            break
        time.sleep(0.2)
    return out[:limit] if limit else out


def _orc_detail(host, site, jid, budget):
    q = urllib.parse.urlencode({"expand": "all", "onlyData": "true",
                                "finder": f'ById;Id="{jid}",siteNumber={site}'})
    url = f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?{q}"
    try:
        d = _get_json(url, budget=budget)
    except Exception:
        return {}
    items = d.get("items") or []
    return items[0] if items else {}


def _fetch_orc(host, site, limit=None, want_desc=True):
    budget = _Budget()
    reqs = _orc_list(host, site, limit, budget)
    base = f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/"

    details = {}
    if want_desc and reqs and not budget.tripped():
        with cf.ThreadPoolExecutor(MAX_WORKERS) as ex:
            futs = {ex.submit(_orc_detail, host, site, r.get("Id"), budget): r.get("Id")
                    for r in reqs if r.get("Id")}
            for f in cf.as_completed(futs):
                try:
                    details[futs[f]] = f.result()
                except Exception:
                    pass

    out = []
    for r in reqs:
        jid = r.get("Id")
        det = details.get(jid) or {}
        locs = [r.get("PrimaryLocation") or det.get("PrimaryLocation") or ""]
        for s in (r.get("secondaryLocations") or det.get("secondaryLocations") or []):
            n = s.get("Name") or s.get("PrimaryLocation") or ""
            if n:
                locs.append(n)
        loc = ", ".join([x for x in dict.fromkeys(locs) if x])
        desc = strip_html("\n\n".join(x for x in [
            det.get("ExternalDescriptionStr") or r.get("ShortDescriptionStr") or "",
            det.get("ExternalResponsibilitiesStr") or "",
            det.get("ExternalQualificationsStr") or "",
            det.get("CorporateDescriptionStr") or "",
            det.get("OrganizationDescriptionStr") or "",
        ] if x))
        # PostedDate is the employer's own posted-on field ('YYYY-MM-DD').
        opened = to_iso(r.get("PostedDate")) or to_iso(det.get("ExternalPostedStartDate"))
        wt = (r.get("WorkplaceType") or det.get("WorkplaceType") or "")
        smin, smax = _salary(desc)
        out.append(dict(title=r.get("Title") or det.get("Title") or "", loc=loc,
                        desc=desc[:DESC_CHARS], opened=opened,
                        url=base + str(jid),
                        remote=("remote" in wt.lower()) or _is_remote(loc, wt),
                        smin=smin, smax=smax))
    return out


# ---------------- public entry point ----------------
def fetch(token, limit=None):
    """token: '<host>/<careersection>'  (Taleo classic, e.g. 'textron/textron')
              '<host>.oraclecloud.com/<siteNumber>'  (Oracle Cloud Recruiting)
    -> list of dicts with keys title, loc, desc, opened, url, remote, smin, smax
    """
    tok = re.sub(r"^https?://", "", str(token).strip()).strip("/")
    if "/" not in tok:
        raise ValueError("token must be '<host>/<careersection-or-siteNumber>'")
    host, rest = tok.split("/", 1)
    rest = rest.split("/")[0]
    if "oraclecloud.com" in host:
        return _fetch_orc(host, rest, limit)
    return _fetch_taleo(host.replace(".taleo.net", ""), rest, limit)


if __name__ == "__main__":
    import sys
    for t in sys.argv[1:]:
        try:
            js = fetch(t, limit=25)
            print(f"{t:52} {len(js):5} jobs  dated={sum(1 for j in js if j['opened'])}")
        except Exception as e:
            print(f"{t:52} ERROR {type(e).__name__}: {e}")
