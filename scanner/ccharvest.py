#!/usr/bin/env python3
"""Harvest ATS board tokens from the Common Crawl URL index.

    python ccharvest.py                 # newest crawl -> cc_candidates.json
    python ccharvest.py --crawl CC-MAIN-2026-30
    python ccharvest.py --keep-idx      # cache cluster.idx for reuse

probe.py is name-driven: it slugifies company names you already know and guesses.
Its ceiling is the name list, so it cannot find a company you have never heard of.
This is URL-driven instead - it reads an index of pages that actually exist on the
web and takes the slug straight out of the URL.

The index is sorted by SURT (reversed host), so every greenhouse.io URL is
contiguous and only the covering blocks need downloading: about 12 MB, not the
300 GB the full index would be. That is why this is a seconds-long job.

Output is CANDIDATES, not targets. The slugs are dirty - the index contains dead
boards, tracking junk and hex blobs - so validate.py has to confirm each one
answers with real postings before it earns a place in the scan.
"""
import argparse, gzip, io, json, os, re, sys, urllib.request
import concurrent.futures as cf

HERE = os.path.dirname(os.path.abspath(__file__))
UA = {"User-Agent": "Mozilla/5.0 (compatible; jobscanner/1.0)"}
BASE = "https://data.commoncrawl.org"

# SURT prefix -> (ats, regex pulling the slug out of the original URL)
SOURCES = [
    ("io,greenhouse,boards)/",     "greenhouse",
     re.compile(r'://boards\.greenhouse\.io/([^/?#\s"]+)', re.I)),
    ("io,greenhouse,job-boards)/", "greenhouse",
     re.compile(r'://job-boards(?:\.eu)?\.greenhouse\.io/([^/?#\s"]+)', re.I)),
    ("co,lever,jobs)/",            "lever",
     re.compile(r'://jobs\.lever\.co/([^/?#\s"]+)', re.I)),
    ("com,ashbyhq,jobs)/",         "ashby",
     re.compile(r'://jobs\.ashbyhq\.com/([^/?#\s"]+)', re.I)),
    ("com,smartrecruiters,jobs)/", "smartrecruiters",
     re.compile(r'://jobs\.smartrecruiters\.com/([^/?#\s"]+)', re.I)),
    ("com,workable,apply)/",       "workable",
     re.compile(r'://apply\.workable\.com/([^/?#\s"]+)', re.I)),
    # jobs.jobvite.com/careers/<company>/job/... - the scan has only 18 of these
    ("com,jobvite,jobs)/careers/", "jobvite",
     re.compile(r'://jobs\.jobvite\.com/careers/([^/?#\s"]+)', re.I)),
    # <company>.icims.com - the slug is the SUBDOMAIN, so it needs its own capture
    ("com,icims,",                 "icims",
     re.compile(r'://([a-z0-9][a-z0-9-]{1,50})\.icims\.com/', re.I)),
]

# Workday needs three parts, so it gets its own extractor rather than a slug
# regex. Same pattern wdtargets.py uses, so both paths agree on what a board is.
WD_PREFIX = "com,myworkdayjobs,"
WD_PAT = re.compile(r'https?://([a-z0-9][a-z0-9-]*)\.(wd\d+)\.myworkdayjobs\.com'
                    r'(?:/[a-z]{2}-[A-Z]{2})?/([A-Za-z0-9_\-]+)', re.I)
WD_SKIP_SITE = {'en-us', 'en-gb', 'fr-ca', 'es-es', 'de-de', 'ja-jp', 'zh-cn',
                'en-ca', 'pt-br', 'it-it', 'nl-nl', 'ko-kr', 'robots.txt',
                'wday', 'login', 'assets', 'static', 'robots', 'search',
                'sitemap', 'sitemap.xml', 'favicon.ico', 'img', 'images',
                'index.html', 'error', 'jobs', 'job', 'home'}


def harvest_workday(lines):
    """-> [{company, token: 'host|tenant|site', seen}], most-seen first."""
    import collections
    recs = blocks_for(lines, WD_PREFIX)
    if not recs:
        return [], 0.0
    size = sum(r[2] for r in recs) / 1e6
    with cf.ThreadPoolExecutor(min(8, len(recs))) as ex:
        texts = list(ex.map(fetch_block, recs))
    trip = collections.Counter()
    for t in texts:
        for m in WD_PAT.finditer(t):
            host_t, pod, site = m.group(1), m.group(2), m.group(3)
            sl = site.lower()
            # bare locale codes ("en", "es") and 1-2 char paths are never sites
            if sl in WD_SKIP_SITE or len(sl) <= 2:
                continue
            trip[('%s.%s.myworkdayjobs.com' % (host_t, pod), host_t, site)] += 1
    out = [dict(company=tenant, token='%s|%s|%s' % (host, tenant, site), seen=n)
           for (host, tenant, site), n in trip.most_common()]
    return out, size


# slugs that are a path segment of the board software, not a company
NOT_A_SLUG = {"embed", "jobs", "j", "api", "static", "assets", "favicon.ico",
              "robots.txt", "sitemap.xml", "search", "companies", "index.html",
              "login", "signup", "privacy", "terms", "css", "img", "_next"}
# a real token: lowercase-ish slug, no spaces, not a bare number, not a hex blob
OK = re.compile(r"^[a-z0-9][a-z0-9._-]{1,60}$")
HEXBLOB = re.compile(r"^[0-9a-f]{16,}$")


def http(url, rng=None, tries=3):
    h = dict(UA)
    if rng:
        h["Range"] = "bytes=%d-%d" % rng
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception as e:
            last = e
    raise last


def newest_crawl():
    d = json.loads(http("https://index.commoncrawl.org/collinfo.json"))
    return d[0]["id"]


def load_cluster(crawl, keep):
    """cluster.idx: one line per compressed index block, sorted by SURT."""
    path = os.path.join(HERE, "cluster_%s.idx" % crawl)
    if os.path.exists(path):
        return open(path, "rb").read()
    raw = http("%s/cc-index/collections/%s/indexes/cluster.idx" % (BASE, crawl))
    if keep:
        open(path, "wb").write(raw)
    return raw


def blocks_for(lines, prefix):
    """Every index block that can contain URLs starting with `prefix`.

    Blocks are ranges, so the one that CONTAINS the prefix usually starts before
    it - taking only lines that start with the prefix silently drops smaller
    domains entirely (this is why a naive prefix match finds no Lever at all).
    """
    out, prev = [], None
    for ln in lines:
        p = ln.split("\t")
        if len(p) < 5:
            continue
        surt = p[0].split(" ")[0]
        rec = (p[1], int(p[2]), int(p[3]))
        if surt < prefix:
            prev = rec                      # candidate covering block
            continue
        if surt.startswith(prefix) or (prev and not out):
            if prev and not out:
                out.append(prev)            # the block the prefix starts inside
            if surt.startswith(prefix):
                out.append(rec)
            continue
        if out:
            out.append(rec)                 # first block past the range, then stop
            break
    return out


def fetch_block(rec):
    name, off, ln = rec
    try:
        raw = http("%s/cc-index/collections/%s/indexes/%s" % (BASE, CRAWL, name),
                   rng=(off, off + ln - 1))
        return gzip.GzipFile(fileobj=io.BytesIO(raw)).read().decode("utf-8", "replace")
    except Exception:
        return ""


def clean(tok):
    t = (tok or "").strip().lower()
    if not t or t in NOT_A_SLUG or HEXBLOB.match(t) or t.isdigit():
        return None
    if not OK.match(t) or "." in t and not t.endswith(("-inc", "-ai")):
        if "." in t:
            return None
    return t


def main():
    global CRAWL
    ap = argparse.ArgumentParser()
    ap.add_argument("--crawl", default=None)
    ap.add_argument("--keep-idx", action="store_true")
    ap.add_argument("--out", default="cc_candidates.json")
    ap.add_argument("--wd-out", default="cc_wd_candidates.json")
    ap.add_argument("--no-workday", action="store_true")
    a = ap.parse_args()

    CRAWL = a.crawl or newest_crawl()
    print("crawl %s" % CRAWL, flush=True)

    lines = load_cluster(CRAWL, a.keep_idx).decode("utf-8", "replace").split("\n")
    print("cluster.idx %s blocks" % format(len(lines), ","), flush=True)

    found, mb = {}, 0
    for prefix, ats, pat in SOURCES:
        recs = blocks_for(lines, prefix)
        if not recs:
            print("  %-30s no blocks" % prefix)
            continue
        size = sum(r[2] for r in recs) / 1e6
        mb += size
        with cf.ThreadPoolExecutor(min(8, len(recs))) as ex:
            texts = list(ex.map(fetch_block, recs))
        n = 0
        for t in texts:
            for line in t.split("\n"):
                m = pat.search(line)
                if not m:
                    continue
                tok = clean(m.group(1))
                if tok:
                    found.setdefault(ats, set()).add(tok)
                    n += 1
        print("  %-30s %2d blocks %6.1f MB -> %6d urls, %6d distinct so far"
              % (prefix, len(recs), size, n, len(found.get(ats, ()))), flush=True)

    if not a.no_workday:
        wd, wdmb = harvest_workday(lines)
        mb += wdmb
        print("  %-30s %2s %6.1f MB -> %6d host|tenant|site triples"
              % (WD_PREFIX, "", wdmb, len(wd)), flush=True)
        if wd:
            json.dump(wd, open(os.path.join(HERE, a.wd_out), "w"), indent=1)
            print("     wrote %s (%d tenants)"
                  % (a.wd_out, len({t["token"].split("|")[1] for t in wd})))

    out = [{"ats": a_, "token": t} for a_ in sorted(found) for t in sorted(found[a_])]
    json.dump(out, open(os.path.join(HERE, a.out), "w"), indent=1)
    print()
    print("downloaded %.1f MB" % mb)
    for a_ in sorted(found):
        print("  %-16s %6d candidate tokens" % (a_, len(found[a_])))
    print("total %d -> %s" % (len(out), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
