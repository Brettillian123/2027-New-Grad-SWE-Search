"""Eligibility test for a May-2027 graduate applying through ordinary junior
postings, not just requisitions labelled new-grad or campus.

Tiers:
  A  title says new grad / university / campus / 2027
  B  body says new grad, recent graduate, 0-2 years, entry level
  C  ordinary junior-or-unlevelled posting a 2027 grad can apply to:
     entry-shaped title, and no stated experience floor of 2+ years
"""
import re
import ats

# titles that are entry-shaped
ENTRY_TITLE = re.compile(r"(\b(software|backend|back[\s-]end|full[\s-]?stack|platform|systems|"
                         r"infrastructure|data|ml|machine learning|ai|application|product)\s+"
                         r"(engineer|developer)\s*(i|1)\b"
                         r"|\bengineer\s*(i|1)\b|\bdeveloper\s*(i|1)\b"
                         r"|\bjunior\b|\bjr\.?\b|\bassociate\s+(software|engineer|developer|data)"
                         r"|\bentry[\s-]level\b|\bearly[\s-]career\b)", re.I)

# a plain unlevelled engineering title ("Software Engineer", "Backend Engineer")
PLAIN_TITLE = re.compile(r"^\s*(senior\s+)?(software|backend|back[\s-]end|full[\s-]?stack|platform|"
                         r"systems|infrastructure|data|ml|machine learning|ai|application)?\s*"
                         r"(engineer|developer|programmer)\b", re.I)

SENIOR_TITLE = re.compile(r"(senior|\bsr\.?\b|staff|principal|\blead\b|manager|director|head of|"
                          r"architect|\bii\b|\biii\b|\biv\b|\bvp\b|distinguished|fellow|"
                          # a level ABOVE entry: GitLab ships "Intermediate Backend
                          # Engineer", which states no year floor and so read as unlevelled.
                          r"intermediate|mid[\s-]?level|mid[\s-]?senior|experienced)", re.I)

# "5+ years", "minimum of 3 years", "3-5 years of experience"
YEARS = re.compile(r"(\d{1,2})\s*(?:\+|-|\u2013|to)?\s*(\d{1,2})?\s*\+?\s*years?[^.]{0,40}"
                   r"(experience|industry|professional|building|developing|working)", re.I)
WORD_YEARS = re.compile(r"\b(two|three|four|five|six|seven|eight|ten)\s+(or more\s+)?years?\b", re.I)
WORDNUM = dict(two=2, three=3, four=4, five=5, six=6, seven=7, eight=8, ten=10)


def min_years(body):
    """Lowest experience floor the posting states, or None if it states none."""
    vals = []
    for m in YEARS.finditer(body or ''):
        try:
            vals.append(int(m.group(1)))
        except Exception:
            pass
    for m in WORD_YEARS.finditer(body or ''):
        vals.append(WORDNUM.get(m.group(1).lower(), 99))
    return min(vals) if vals else None


# Wording that makes a figure optional rather than required. Checked in the
# clause around the match and in the nearest preceding heading, because postings
# put "Preferred Qualifications" once and then list bare bullets under it.
PREFERRED_CTX = re.compile(
    r"(preferred|preferrable|nice[\s-]to[\s-]have|bonus|a plus|"
    r"plus(?:es)?\b|desired|desirable|ideally|would be great|"
    r"not required|helpful|advantageous|we'd love|nice if)", re.I)

# "1+ years OR a bachelor's degree" - a degree satisfies it, so it is not a floor
# for a graduating senior. Deliberately scoped to the enclosing clause.
DEGREE_ALT = re.compile(r"\bor\b[^.;]{0,90}\b(associate|bachelor|master|b\.?s\.?|"
                        r"m\.?s\.?|degree|equivalent|coursework)", re.I)


def required_years(body):
    """-> (required_floor, preferred_floor)

    required_floor is the largest number of years the posting actually demands;
    None when it demands none. preferred_floor is the largest figure that is only
    wanted, which is reported for context and never gated on.
    """
    body = body or ''
    req, pref = [], []
    for m in list(YEARS.finditer(body)) + list(WORD_YEARS.finditer(body)):
        g = m.group(1)
        try:
            n = int(g)
        except ValueError:
            n = WORDNUM.get(g.lower())
        if n is None:
            continue
        # the clause the figure sits in, plus the heading that governs it
        clause = body[max(0, m.start() - 160):m.end() + 160]
        heading = body[max(0, m.start() - 600):m.start()]
        optional = bool(PREFERRED_CTX.search(clause))
        if not optional:
            # a "Preferred/Nice to have" heading closer than any "Required" one
            hp = max(heading.lower().rfind(w) for w in
                     ('preferred', 'nice to have', 'bonus', 'a plus', 'desired'))
            hr = max(heading.lower().rfind(w) for w in
                     ('required', 'requirement', 'qualification', 'must have',
                      'what you', 'you bring', 'basic '))
            optional = hp > hr
        # A degree only excuses the years when it is an ALTERNATIVE to them
        # ("1+ years or a bachelor's"). Iambic writes "Master's ... or a
        # Bachelor's WITH 2+ years", where the degree path still demands the
        # years, so an additive join before the figure keeps it binding.
        before = body[max(0, m.start() - 70):m.start()]
        additive = re.search(r"(bachelor|master|b\.?s\.?|m\.?s\.?|degree)[^.;]{0,40}"
                             r"\b(with|plus|and)\b[^.;]{0,25}$", before, re.I)
        if DEGREE_ALT.search(clause) and not additive:
            continue                     # a degree genuinely satisfies it
        (pref if optional else req).append(n)
    return (max(req) if req else None), (max(pref) if pref else None)


# a title that names the class outright is trusted over a stray years mention
EXPLICIT_TITLE = re.compile(r"(new\s*grad|new college|university (grad|hire)|campus|"
                            r"class of 20|20\s?27|graduate (software|engineer|developer|program)|"
                            r"early[\s-]career|entry[\s-]level)", re.I)


def eligibility(job):
    """-> (tier, floor, stretch) where tier is 'A'|'B'|'C' or None.

    The stated experience floor is authoritative over an encouraging title: a req
    titled "Junior Backend Engineer" that demands 2+ years is not a new-grad role.
    A floor of 3+ years disqualifies. A floor of exactly 2 is kept but marked a
    stretch - by May 2027 Brett has the Ensemble internship plus two years running
    Crestwell, so it is arguable rather than absurd.
    """
    t = (job.get('title') or '').strip()
    body = (job.get('desc') or '')[:12000]
    if not t or ats.EXCLUDE.search(t) or ats.DISCIPLINE_BAD.search(t):
        return None, None, False
    if not ats.SWE.search(t):
        return None, None, False
    floor = min_years(body)
    explicit = bool(EXPLICIT_TITLE.search(t))
    gated = floor is not None and floor >= 3
    stretch = floor == 2
    if gated and not explicit:
        return None, floor, stretch
    strict = ats.classify(job)
    if strict:
        return strict['tier'], floor, stretch
    if SENIOR_TITLE.search(t):
        return None, floor, stretch
    entry = bool(ENTRY_TITLE.search(t))
    plain = bool(PLAIN_TITLE.match(t))
    if not (entry or plain):
        return None, floor, stretch
    return 'C', floor, stretch


# advocacy / evangelism / docs roles are not backend engineering
DEVREL = re.compile(r"(developer relations|developer advocate|devrel|evangelist|"
                    r"community engineer|documentation|technical writer|solutions engineer|"
                    r"sales engineer|customer engineer|support engineer|"
                    r"forward deployed.*(sales|account)|growth engineer)", re.I)

# an unlevelled title needs the body to show it is reachable
JUNIOR_SIGNAL = re.compile(r"(new grad|recent graduate|early[\s-]career|entry[\s-]level|"
                           r"junior|0[\s-]*(to|-)\s*[123]\s*years|1[\s-]*(to|-)\s*[23]\s*years|"
                           r"\b(0|1|one)\+?\s*years?|no prior (professional )?experience|"
                           r"from coursework|recent (grad|degree)|bachelor'?s degree (in|or)|"
                           r"graduating|internship experience|academic projects)", re.I)

# expectations that only make sense for an experienced hire
SENIOR_BODY = re.compile(r"(you will (lead|own|define|drive) the|own the (architecture|roadmap|technical)|"
                         r"mentor (and coach |)?(junior|other|less experienced)|set the technical direction|"
                         r"zero to one|0 to 1|founding engineer|technical leadership|"
                         r"proven track record of (leading|delivering|shipping)|deep expertise)", re.I)


def eligibility2(job):
    """Stricter successor to eligibility().

    An explicitly entry-shaped title (Engineer I, Junior, Associate, Entry-level)
    stands on its own. A plain unlevelled title must additionally show a junior
    signal in the body and no senior-shaped expectations - a bare "Software
    Engineer" at a startup is usually a mid-level req that simply omits a number.
    """
    t = (job.get('title') or '').strip()
    body = (job.get('desc') or '')[:12000]
    if not t or DEVREL.search(t):
        return None, None, False
    if ats.EXCLUDE.search(t) or ats.DISCIPLINE_BAD.search(t) or not ats.SWE.search(t):
        return None, None, False
    if SENIOR_TITLE.search(t):
        return None, None, False

    floor = min_years(body)
    explicit = bool(EXPLICIT_TITLE.search(t))
    entry = bool(ENTRY_TITLE.search(t))
    plain = bool(PLAIN_TITLE.match(t))

    if explicit:
        return (ats.classify(job) or {}).get('tier', 'A'), floor, False
    if floor is not None and floor >= 3:
        return None, floor, False
    if entry:
        if floor == 2:
            return 'C', floor, True          # reachable, flagged as a stretch
        return 'C', floor, False
    if plain:
        if floor is not None and floor >= 2:
            return None, floor, False
        if SENIOR_BODY.search(body):
            return None, floor, False
        if not JUNIOR_SIGNAL.search(body):
            return None, floor, False
        return 'C', floor, False
    return None, floor, False


# clinical / lab / imaging roles that share the word "engineer" or "technologist"
CLINICAL = re.compile(r"(technologist|radiolog|mammograph|\bmri\b|cytotech|neurodiagnostic|"
                      r"sonograph|phlebotom|\bnurse\b|cath lab|perfusion|respiratory therap|"
                      r"surgical tech|pharmac|clinical lab)", re.I)

# only unambiguous experienced-hire framing - narrow on purpose, because the
# previous version rejected genuinely open reqs at Cribl, GitLab and Torc
# Only unambiguous experienced-hire OWNERSHIP framing. Phrases describing the
# team ("engineers with deep expertise in ML") or collaborative work ("help set
# the technical direction ... with an existing team") are not requirements, and
# rejecting on them wrongly killed the Torc and Cribl reqs.
SENIOR_BODY_STRICT = re.compile(r"(founding engineer|"
                                r"you will lead the team|lead a team of|manage a team of|"
                                r"own the technical roadmap|principal[- ]level|staff[- ]level|"
                                r"recognized (expert|authority)|"
                                r"hire and (grow|build) (a|the|your) team)", re.I)


def eligibility3(job):
    """Is this posting open to a May-2027 graduate applying normally?

    Decided by the stated experience floor, not by title shape. Title patterns
    proved brittle in both directions - they rejected IMC's "Graduate Performance
    Engineer", Torc's "ML Engineer, I" and Cribl's plain "Software Engineer",
    all of which a 2027 grad can apply to.

    Reject: senior/staff/lead titles, DevRel and advocacy, clinical roles,
    a floor of 3+ years, or unmistakable experienced-hire framing.
    Keep:   everything else. A floor of exactly 2 is kept and flagged a stretch.
    """
    t = (job.get('title') or '').strip()
    body = (job.get('desc') or '')[:12000]
    if not t:
        return None, None, False
    if DEVREL.search(t) or CLINICAL.search(t):
        return None, None, False
    if ats.EXCLUDE.search(t) or ats.DISCIPLINE_BAD.search(t) or not ats.SWE.search(t):
        return None, None, False
    if SENIOR_TITLE.search(t):
        return None, None, False

    floor, _pref = required_years(body)
    explicit = bool(EXPLICIT_TITLE.search(t))
    if explicit:
        return (ats.classify(job) or {}).get('tier', 'A'), floor, False
    # Brett's rule: anything REQUIRING two years or more is out. Figures that are
    # only preferred never reach here - required_years puts them aside.
    if floor is not None and floor >= 2:
        return None, floor, False
    if SENIOR_BODY_STRICT.search(body):
        return None, floor, False
    tier = 'B' if (ats.classify(job) or {}).get('tier') else 'C'
    return tier, floor, floor == 2


# The role must actually BE software engineering. Dropping the title-shape gate
# let in anything containing the word "Engineer" - power-plant stationary
# engineers, substrate engineers, an SVP of actuarial engineering, and a New York
# Times AI correspondent.
ROLE_OK = re.compile(r"(software\s+(engineer|develop)|"
                     r"\b(backend|back[\s-]end|full[\s-]?stack|fullstack)\b|"
                     r"platform\s+engineer|infrastructure\s+engineer|"
                     r"data\s+engineer|analytics\s+engineer|"
                     r"(machine learning|\bml\b|\bai\b|applied ai)\s*(engineer|scientist)|"
                     r"\bdeveloper\b|\bprogrammer\b|systems?\s+software|"
                     r"application\s+engineer|integrations?\s+engineer|"
                     r"performance\s+engineer|quantitative\s+(developer|technologist)|"
                     r"forward\s+deployed\s+engineer|reliability\s+engineer|"
                     r"compiler|api\s+develop)", re.I)

# role families that borrow the word "engineer" but are not software engineering
ROLE_BAD = re.compile(r"(sec[\s-]?ops|\bsoc\b|siem|incident response|detection engineer|"
                      r"threat|escalation|curriculum|trainer|demonstrat|correspondent|"
                      r"consultant|client value|\bpartner\b|administrator|"
                      r"project engineer|supplier|plant|stationary|"
                      r"brand team|product design|substrate|industry 4\.0|"
                      r"actuarial|\bsvp\b|\banalyst\b|network engineer|wireless|"
                      r"professional services|people systems|business systems|"
                      r"sales|account|scraping|"
                      r"\bgtm\b|go[\s-]to[\s-]market|\bfield\b|embedded|\bdsp\b|"
                      r"solutions architect|implementation)", re.I)


# Seniority stated without a number. ElevenLabs' GPU-cluster req says "Have run
# large GPU fleets in production ... or have deep systems experience" and names no
# figure at all, so min_years sees nothing and the posting reads as unlevelled.
# This is a FLAG, not a rejection: the same shape of rule, applied as a hard gate,
# is what previously killed the Torc and Cribl reqs, and a phrase in a "nice to
# have" list is not a floor. The board shows it and sorts on it; Brett decides.
IMPLICIT_SENIOR = re.compile(
    r"(deep\s+\w*\s*(?:experience|expertise|knowledge|understanding)|"
    r"extensive\s+(?:experience|background)|significant\s+experience|"
    r"substantial\s+experience|proven\s+track\s+record|"
    r"demonstrated\s+(?:experience|expertise|ability to lead)|"
    r"strong\s+background\s+in|seasoned|"
    r"(?:have|having)\s+(?:run|operated|scaled|managed)\s+[^.]{0,60}"
    r"(?:in\s+production|at\s+scale|fleets|clusters)|"
    r"production\s+experience|prior\s+industry\s+experience|"
    r"expert(?:ise)?\s+in\s+\w+|"
    r"you(?:'ve| have)\s+(?:built|shipped|owned|operated)\s+[^.]{0,50}"
    r"(?:at\s+scale|in\s+production))", re.I)

# Below this, there is no posting text worth judging - the fetcher failed, the ATS
# returns none, or it is a stub. Passing these through as "states no floor" is how
# 3,300 SmartRecruiters rows reached the board with an empty description.
MIN_BODY = 400


def senior_hints(body):
    """Distinct implicit-seniority phrases in the posting, for the board to show."""
    return sorted({m.group(1).lower().strip() for m in IMPLICIT_SENIOR.finditer(body or '')})


def eligibility4(job):
    """Final rule: a real software-engineering role, not senior-gated, open to a
    May-2027 graduate applying through an ordinary junior application."""
    t = (job.get('title') or '').strip()
    body = (job.get('desc') or '')[:12000]
    if not t:
        return None, None, False
    # No body means no evidence, and no evidence is not evidence of entry level.
    # An explicitly entry-shaped title still stands on its own.
    if len(body) < MIN_BODY and not EXPLICIT_TITLE.search(t) and not ENTRY_TITLE.search(t):
        return None, None, False
    if DEVREL.search(t) or CLINICAL.search(t) or ROLE_BAD.search(t):
        return None, None, False
    if ats.EXCLUDE.search(t) or ats.DISCIPLINE_BAD.search(t):
        return None, None, False
    if not ROLE_OK.search(t):
        return None, None, False
    if SENIOR_TITLE.search(t):
        return None, None, False

    floor = min_years(body)
    if EXPLICIT_TITLE.search(t):
        return (ats.classify(job) or {}).get('tier', 'A'), floor, False
    if floor is not None and floor >= 3:
        return None, floor, False
    if SENIOR_BODY_STRICT.search(body):
        return None, floor, False
    tier = 'B' if (ats.classify(job) or {}).get('tier') else 'C'
    return tier, floor, floor == 2
