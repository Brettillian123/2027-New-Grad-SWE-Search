import re

NUM = r"\$\s?(\d{2,3})(?:,(\d{3}))?(?:\.\d+)?\s?([kK])?"
RANGE = re.compile(NUM + r"\s*(?:-|–|—|to)\s*" + NUM)
SINGLE = re.compile(NUM)

CTX = re.compile(r"(salary|base pay|pay range|compensation|base salary|annual|per year|/yr|USD)", re.I)

# A bare "$400" followed by a magnitude word is a funding round, not a wage.
# This is what put a $500k band on an entry-level Alpaca req: the posting said
# "backed by $400 million in funding", and n < 1000 was being scaled to 400,000.
MAG = re.compile(r"^\s?(million|billion|bn|mm|m\b|b\b|trillion)", re.I)

# Money discussed in these terms is never the candidate's pay.
NEG = re.compile(r"(funding|funded|raised|raising|valuation|valued at|investors?|"
                 r"venture|series\s+[a-f]\b|revenue|ARR|market cap|assets under "
                 r"management|AUM|contract value|budget|savings|portfolio|"
                 r"transaction volume|processed over|grant|stipend|one-time|per month|monthly|setup|reimburse\w*|allowance|voucher|credit)", re.I)

SENT_ENDS = '.!?' + chr(10)


def _v(m, i):
    a, b, k = m.group(i), m.group(i + 1), m.group(i + 2)
    if b:
        return int(a + b)
    n = int(a)
    # Scale ONLY on an explicit 'k'. The old rule scaled any bare figure under
    # 1000, which turned "New Hire Home-Office Setup: One-time USD $500" into a
    # $500,000 band on an entry-level Alpaca req. Real salaries are written
    # "$120k" or "$120,000"; a bare "$500" is a stipend, a fee, or a price.
    if k:
        n *= 1000
    return n


def _bad_ctx(text, m):
    """Reject funding/valuation figures and anything scaled by a magnitude word."""
    if MAG.match(text[m.end():m.end() + 12]):
        return True
    # Scope the funding check to the ENCLOSING SENTENCE. A wide character window
    # lets "processed $500 million in transaction volume." in a previous sentence
    # poison a real salary range in the next one.
    a = max((text.rfind(c, 0, m.start()) for c in SENT_ENDS), default=-1) + 1
    ends = [x for x in (text.find(c, m.end()) for c in SENT_ENDS) if x != -1]
    b = min(ends) if ends else len(text)
    return bool(NEG.search(text[a:b]))


def extract(text):
    """-> (min,max) annual USD, or (None,None)"""
    if not text:
        return (None, None)
    best = None
    for m in RANGE.finditer(text):
        lo, hi = _v(m, 1), _v(m, 4)
        if not (30000 <= lo <= 600000 and lo <= hi <= 900000):
            continue
        w = text[max(0, m.start() - 160):m.end() + 160]
        if not CTX.search(w):
            continue
        if re.search(r"(per hour|hourly|/hr|an hour)", w, re.I):
            continue
        if _bad_ctx(text, m):
            continue
        if best is None or hi > best[1]:
            best = (lo, hi)
    if best:
        return best
    for m in SINGLE.finditer(text):
        n = _v(m, 1)
        if not (60000 <= n <= 600000):
            continue
        w = text[max(0, m.start() - 160):m.end() + 160]
        if not CTX.search(w) or re.search(r"(per hour|hourly|/hr)", w, re.I):
            continue
        if _bad_ctx(text, m):
            continue
        return (n, n)
    return (None, None)
