import re

# Any explicit floor of 1.5 years or more is out of reach for a May-2027 grad.
# A "1+ year" floor is kept only when a degree is offered as an alternative,
# which is how Microsoft/GitHub-style Software Engineer I reqs are written.
HARD_FLOOR = re.compile(r"\b(1\.5|[2-9]|1[0-9]|two|three|four|five|six|seven|eight)\s*\+?\s*"
                        r"(?:-|to|\u2013)?\s*\d*\s*\+?\s*years?\b", re.I)
SOFT_FLOOR = re.compile(r"\b(0|1|one)\s*\+?\s*(?:-|to|\u2013)?\s*\d*\s*\+?\s*years?\b", re.I)
DEGREE_SUB = re.compile(r"\bor\b[^.]{0,80}\b(associate|bachelor|master|degree|equivalent)\b", re.I)

# the agent's own hedges - checked before any positive signal, because a sentence
# like "NO explicit new-grad language" contains the phrase it is denying
WEAK = re.compile(r"(\bweak\b|no explicit|\bno\b[^.]{0,30}new[-\s]grad|"
                  r"absence of any years|above a pure new[-\s]grad|"
                  r"not (a )?new[-\s]grad|could not (confirm|verify))", re.I)
SENIOR_SHAPE = re.compile(r"(zero to one|0 to 1|leading a high-impact|"
                          r"lead(ing)? (a|the) team|own(ing)? the architecture|"
                          r"mentor(ing)? (junior|other) engineers|set the technical direction)", re.I)
GOOD = re.compile(r"(new grad|new-grad|recent graduate|early[-\s]career|entry[-\s]level|"
                  r"university (grad|hire)|campus|class of 20|graduating|"
                  r"from coursework|no prior professional experience)", re.I)
LEVEL_II = re.compile(r"\bengineer\s*(ii|iii|2|3)\b", re.I)


def newgrad_ok(evidence, title=''):
    """Judge an agent's newgrad_evidence string for a May-2027 graduate."""
    e = evidence or ''
    if WEAK.search(e):
        return False
    if SENIOR_SHAPE.search(e):
        return False
    m = HARD_FLOOR.search(e)
    if m:
        return False
    if LEVEL_II.search(title or ''):
        return False
    if GOOD.search(e):
        return True
    m = SOFT_FLOOR.search(e)
    if m:
        tail = e[m.start():m.start() + 200]
        return bool(DEGREE_SUB.search(tail))
    return True
