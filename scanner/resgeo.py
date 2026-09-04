import re
from geo import geo

NOT_A_COMPANY = re.compile(r"(career fair|job fair|university of|college of|handshake|"
                           r"symplicity|career center|megathread|r/cs|blind\b)", re.I)

# explicit denials, plus "Chicago office is sales only" style disqualifiers
NEG_CHI = re.compile(r"(\b(not|no|never|isn'?t)\s+(in\s+)?(chicago|illinois)\b"
                     r"|(chicago|illinois)[^.]{0,40}\b(is sales|sales only|non-?engineering))", re.I)
NEG_REM = re.compile(r"\b(not|no|never|isn'?t)\s+(a\s+)?remote\b", re.I)
# " (Stripe also has a Chicago office)" - a corporate aside, not the job's location
PAREN = re.compile(r"\([^)]*\)")
HEDGE = re.compile(r"\b(based on|plausible|expected|historically|likely|presumably|"
                   r"team anywhere|office is sales)\b.*$", re.I | re.S)
ASIDE = re.compile(r"\b(also has|has an?|maintains an?)\b.*$", re.I | re.S)


def research_geo(location, rc, title, notes=''):
    """Geography for agent-sourced rows.

    Only the explicit `location` field and the requisition title are trusted -
    agents wrote prose into `remote_or_chicago` and `notes`. Within `location`,
    parentheticals, hedges and corporate asides are stripped first: a phrase like
    "Seattle, WA (Stripe also has a Chicago office)" names Seattle as the job's
    location and Chicago only as an aside about the company.
    """
    raw = ' '.join([location or '', title or ''])
    text = ASIDE.sub(' ', HEDGE.sub(' ', PAREN.sub(' ', raw)))
    g = geo(text)
    chicago = bool(g['chicago']) and not NEG_CHI.search(raw)
    remote = bool(g['remote']) and not NEG_REM.search(raw)
    return chicago, remote
