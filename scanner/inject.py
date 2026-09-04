"""Inject final.json into template.html -> target_board.html"""
import json, html, os
from estpay import parse_range

OUT = r"C:\Users\Brett\OneDrive\Documents\JobSearch\target_board.html"

F = json.load(open('final.json'))
STATS = json.load(open('stats.json')) if os.path.exists('stats.json') else {}
NOPROG = json.load(open('no_program.json')) if os.path.exists('no_program.json') else []



def ascii_safe(text):
    """Numeric character references for anything non-ASCII, so the page is
    byte-identical under any charset the host might apply."""
    return ''.join(c if ord(c) < 128 else '&#%d;' % ord(c) for c in text)


def clean(text):
    """Some ATS feeds carry a mangled dash that decodes to U+FFFD."""
    return (text or '').replace(chr(0xFFFD), '-').replace('  ', ' ').strip()


def where(r):
    """Human-readable location. Agent rows carry prose in `loc`, so anything that
    reads like a sentence is discarded in favour of the plain flag label."""
    import re as _re
    t = clean(r.get('loc') or '')
    # a multi-part location ("Remote, Canada; Remote, United States") should show
    # the segment that matters to a US candidate, not whichever came first
    segs = [x.strip() for x in _re.split(r'[;|]', t) if x.strip()]
    if len(segs) > 1:
        us = [x for x in segs
              if _re.search(r'\b(united states|usa?|chicago|illinois|il)\b', x, _re.I)]
        t = us[0] if us else segs[0]
    else:
        t = segs[0] if segs else ''
    t = _re.split(r'\(', t)[0]
    t = _re.split(r'\b(?:based on|historically|is a listed|expected|plausible)\b', t)[0]
    t = _re.sub(r'\s+', ' ', t).strip(' ,-')
    looks_like_prose = (' is ' in t) or (' are ' in t) or len(t.split()) > 6
    if not t or looks_like_prose:
        if r.get('chicago') and r.get('remote'):
            return 'Chicago / Remote - US'
        return 'Chicago area' if r.get('chicago') else ('Remote - US' if r.get('remote') else '')
    if len(t) > 40:
        t = t[:37].rstrip(' ,') + '...'
    return t


def soft_pay(r):
    """True when the band's top clears $95k but its midpoint does not."""
    lo, hi = r.get('smin'), r.get('smax')
    if not hi:
        lo, hi = parse_range(r.get('est_base') or '')
    if not hi:
        return False
    return ((lo or hi) + hi) / 2 < 95000


def _locchip(r):
    """Blank when the location text adds nothing beyond the Chicago/Remote badge."""
    t = where(r)
    flat = t.lower().replace('-', ' ').replace('.', '').replace(',', '').strip()
    if flat in ('remote', 'remote us', 'chicago', 'chicago il', 'chicago area',
                'chicago illinois', 'any location / remote', 'chicago / remote us'):
        return ''
    return t


def _fmt(lo, hi, dash):
    if not hi:
        return None
    if not lo or lo == hi:
        return '$%dk' % (hi // 1000)
    return '$%dk%s%dk' % (lo // 1000, dash, hi // 1000)


def band(r):
    """Display band. Agent rows carry prose like 'Base Salary Range $150,000 - ...',
    so the numbers are parsed out rather than truncating the sentence."""
    t = _fmt(r.get('smin'), r.get('smax'), '&ndash;')
    if t:
        return t
    t = _fmt(*parse_range(r.get('est_base') or ''), dash='&ndash;')
    return t or '&mdash;'


def band_plain(r):
    """Plain-ASCII band for the clipboard payload."""
    t = _fmt(r.get('smin'), r.get('smax'), '-')
    if t:
        return t
    return _fmt(*parse_range(r.get('est_base') or ''), dash='-') or ''


def tier(r):
    if r['status'] != 'LIVE':
        return 'watch'
    return 'window' if r.get('opened','') >= '2026-08-25' else 'live'


data = []
for i, r in enumerate(F, 1):
    data.append(dict(
        n=i, co=clean(r['company']), role=clean(r['title']),
        chi=bool(r['chicago']), rem=bool(r['remote']), ai=bool(r['ai']),
        pay=band(r), payt=band_plain(r), smax=r.get('smax') or 0,
        date=r.get('opened') or '', t=tier(r),
        url=r.get('url') or '', why=(r.get('why') or '').replace('; ', ' &middot; ')[:180],
        roles=r.get('n_roles', 1), loc=_locchip(r), soft=soft_pay(r),
        new48=bool(r.get('new48')),
    ))

n_chi = sum(1 for d in data if d['chi'])
n_rem = sum(1 for d in data if d['rem'])

FINDINGS = [
    ("01",
     "Three coverage bugs found and fixed &mdash; the board was missing most of the market",
     "Brett noticed almost every application he had submitted was on Greenhouse. That was right, and the "
     "cause was worse than a Greenhouse bias. <b>The scanner pre-filtered every platform with a rule that "
     "required an explicit <em>new grad</em> signal in the title or body.</b> Measured against a corpus "
     "collected without it, that filter discards <b>87%% of eligible postings</b> &mdash; 2,440 of 2,789, "
     "including 343 plain <em>Software Engineer</em> reqs, plus Full Stack, Data, SRE, Platform, ML and "
     "Forward Deployed Engineer. Every board scanned before today was missing them."),
    ("02",
     "Workday was 2.4%% of the scan and is the largest ATS in the market",
     "In a 19,178-row sample of live postings, <b>Workday appears 8,621 times against Greenhouse's 1,533</b> "
     "&mdash; yet the original scan covered 336 Greenhouse companies and only 22 on Workday. The cause was "
     "token discovery: Greenhouse needs one guessable slug, Workday needs a tenant, a numbered pod and an "
     "arbitrary site path, and its job list is a POST. <b>1,314 valid Workday board addresses were already "
     "sitting in harvested data and had never been read back out.</b> Re-scanning them returned "
     "<b>2,789 eligible postings across 466 companies</b>, against 59 across 22 before."),
    ("03",
     "Every Illinois location counted as Chicago",
     "The geography rule matched <span class=\"mono\">illinois</span> and a bare <span class=\"mono\">IL</span>, "
     "so Peoria, Springfield, Rockford, Champaign and Shiloh &mdash; a St. Louis suburb 280 miles away &mdash; "
     "all flagged as Chicago, and so did Normal. It is now a 51-term Chicago-metro list verified against 14 "
     "cases. The Chicago column on the previous board was inflated by the width of the whole state."),
    ("04",
     "Salary bands were being thrown away before they could be read",
     "Descriptions were truncated to 1,500 characters at collection time, and pay bands sit at the <em>end</em> "
     "of a posting. Only Ashby survived, because it returns structured compensation as a separate field. "
     "Extracting pay from the full text before truncating recovered a band on <b>53 of 120</b> re-scanned "
     "postings that had shown none."),
    ("05",
     "What the gates cost, and where the board now stands",
     "Across <b>%s postings</b> from <b>%s boards</b>, 9,702 cleared eligibility. The two-week freshness rule "
     "removed 7,968 of them &mdash; by far the largest single cut &mdash; and the remote-or-Chicago rule removed "
     "1,617 more. <b>%d companies</b> survive everything. A dash in the pay column means the employer published "
     "no band, which is common on Workday and is not the same as paying badly; those rows are kept."),
]


n_live = sum(1 for d in data if d['t'] != 'watch')
n_watch = len(data) - n_live
FINDINGS[0] = (FINDINGS[0][0], FINDINGS[0][1], FINDINGS[0][2] % ())
FINDINGS[1] = (FINDINGS[1][0], FINDINGS[1][1] % (), FINDINGS[1][2])
FINDINGS[4] = (FINDINGS[4][0], FINDINGS[4][1],
               FINDINGS[4][2] % (STATS.get('posts', '135,000+'), STATS.get('boards', '2,100+'), len(data)))

CAVEATS = [
    "Several top quant firms screen on GPA, commonly at 3.5. Akuna, Belvedere, Chicago Trading Company, Old Mission, "
    "TransMarket, Wolverine, SpiderRock and Optiver are the more accessible entries; Citadel, Jane Street, HRT, Two Sigma "
    "and Jump are the tightest.",
    "Trading firms hire on a rolling basis and close requisitions once a class fills. In this segment, applying in the first "
    "two weeks matters more than a perfectly tailored resume.",
    "Citadel and Citadel Securities auto-refresh the <span class=\"mono\">datePosted</span> field on their own pages daily, so "
    "their dates are a freshness stamp rather than a real open date. Both requisitions are genuinely live.",
    "A dash in the pay column means the employer published no band, not that it pays poorly. Any role with a published band "
    "below $95,000 was filtered out; a handful of ranges shown start lower but top out well above the floor.",
    "Nothing here records work authorization or sponsorship, and several quant and defense-adjacent firms have hard "
    "restrictions. Confirm before investing time.",
    "Dates are the employer's own <span class=\"mono\">first_published</span> / <span class=\"mono\">publishedAt</span> / "
    "<span class=\"mono\">startDate</span> field read from its applicant-tracking system, or a quoted first-party page. "
    "Requisitions still close without notice &mdash; confirm on the linked page before applying.",
]

np_html = "\n".join(
    '<div class="np"><b>%s</b><span>%s</span></div>'
    % (html.escape(x['company'][:44]), html.escape((x['reason'] or '')[:150]))
    for x in sorted(NOPROG, key=lambda x: x['company'].lower()))

t = open('template.html', encoding='utf-8').read()

find_html = '\n'.join(
    '<article class="find"><div class="num">%s</div><div><h3>%s</h3><p>%s</p></div></article>'
    % (n, h, p) for n, h, p in FINDINGS)
cav_html = '\n'.join('<li>%s</li>' % c for c in CAVEATS)

def _top(r):
    if r.get('smax'):
        return r['smax']
    return parse_range(r.get('est_base') or '')[1] or 0
top = max((_top(r) for r in F), default=0)
repl = {
    '__DATA__': json.dumps(data, ensure_ascii=True),
    '__FINDINGS__': find_html,
    '__CAVEATS__': cav_html,
    '__NOPROG__': np_html or '<div class="np"><b>None recorded</b><span>No employers were ruled out.</span></div>',
    '__NCO__': str(len(data)),
    '__NCHI__': str(n_chi),
    '__NREM__': str(n_rem),
    '__NAI__': str(sum(1 for d in data if d['ai'])),
    '__NWIN__': str(sum(1 for d in data if d['t'] == 'window')),
    '__TOPPAY__': ('$%dk' % (top // 1000)) if top else '&mdash;',
    '__NBOARDS__': str(STATS.get('boards', '1,800+')),
    '__NPOST__': str(STATS.get('posts', '125,000+')),
    '__NCLASS__': str(STATS.get('classified', '800+')),
}
for k, v in repl.items():
    t = t.replace(k, v)

t = ascii_safe(t)
open(OUT, 'w', encoding='utf-8').write(t)
print('wrote', OUT, len(data), 'companies,', len(t), 'bytes')
leftover = [k for k in repl if k in t]
if leftover:
    print('WARNING unreplaced:', leftover)
