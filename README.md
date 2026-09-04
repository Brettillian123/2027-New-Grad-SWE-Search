# 2027 New Grad SWE Search

A job scanner that reads **3,886 employer job boards across 11 applicant-tracking
systems** directly through their APIs, because the only trustworthy posting date
is the employer's own field.

Built to answer one question twice a week: *what backend or AI engineering role,
open to a May 2027 graduate, went live in the last 48 hours and is remote or in
Chicago?*

```
python scanner/refresh.py --fast     # ~4 min, the boards that produce
python scanner/refresh.py --all      # ~45 min, every board
python scanner/refresh.py --no-scan  # ~10 s, re-gate the last scan
```

## Why not just use an aggregator

Aggregators report when *they* first saw a posting, not when the employer opened
it. Applying inside 48 hours matters more than almost anything else in a new-grad
search, so a date that drifts by a week is worse than no date.

Every platform here is read at the source:

| ATS | Boards | Authoritative date field |
|---|---|---|
| Greenhouse | 896 | `first_published` |
| Ashby | 554 | `publishedAt` (+ structured compensation) |
| Workday | 1,314 | `jobPostingInfo.startDate` |
| Lever | 283 | `createdAt` |
| SmartRecruiters | 218 | `releasedDate` |
| Workable | 97 | `published_on` |
| Taleo / Oracle Cloud | 170 | `PostedDate` |
| SuccessFactors | 72 | schema.org `datePosted` |
| iCIMS | 50 | `posted_date` |
| Jobvite | 18 | JSON-LD `datePosted` |
| Eightfold | 8 | `postedTs` |

## How it works

**Discovery.** `probe.py` takes a company name, slugifies it, and probes five ATS
endpoints. Feeding it 3,050 known company names found 238 boards we had no token
for, including Palantir, Waymo, Toast and Esri. `wdtargets.py` mines Workday
host/tenant/site triples out of harvested posting URLs — Workday needs three
parts and a POST, which is why it is usually under-covered.

**Eligibility.** `openelig.py` decides on the *stated experience floor*, not the
title. Three-plus years is out, two is kept and flagged a stretch, and an
unlevelled "Software Engineer" with no stated floor is in.

**Gates.** Remote-or-Chicago, posted within 14 days, published band clearing a
salary floor. All dates computed from `date.today()`, never hardcoded.

**Tiering.** `tiers.py` — of 3,680 boards, 1,573 produce something and 1,854 are
reachable but silent. Silent boards are checked every 4th run and dead ones every
8th, cutting a routine run to 43% of the work with no measured loss (verified by
same-day A/B against a full sweep: 0 postings lost).

## Things that turned out to be true, and the bugs behind them

Most of the interesting work here was finding out the scanner was lying.

**A pre-filter was discarding 87% of eligible postings.** Every platform was
screened through a rule requiring an explicit "new grad" signal in the title or
body. Measured against a corpus collected without it: 2,440 of 2,789 postings
dropped, including 343 plain `Software Engineer` reqs.

**Workday is the largest ATS in the market and was 2.4% of the scan.** In a
19,178-row sample of live postings Workday appears 8,621 times against
Greenhouse's 1,533 — and 1,314 valid Workday board addresses were already sitting
in harvested data, never read back out.

**A $500 office stipend was published as a $500,000 salary band.** `sal.py`
scaled any bare figure under 1,000 by a thousand, so "New Hire Home-Office Setup:
One-time USD $500" became a band on an entry-level req. It also read "$400
million in funding" as compensation. Both fixed, with the funding check scoped to
the enclosing sentence so a real range in the next sentence still parses.

**Every Illinois location counted as Chicago.** The geography rule matched
`illinois` and a bare `IL`, so Peoria, Springfield, Rockford and Shiloh — a
St. Louis suburb 280 miles away — all flagged as Chicago.

**A remote job whose location says "Colorado".** A posting's location field often
names an office while the body says the role is remote nationwide.
`geo.remote_in_text()` now reads the full description *before* truncation,
deliberately strict: it accepts "Workplace flexibility: Remote" and rejects
"we're a remote-friendly company".

**The date-walk that was slower.** Workday returns an empty search newest-first,
so paging until you leave the window looks like an obvious optimisation. On an
even sample it is 2.5x *slower* than keyword queries — but finds 2.4x more. It
is kept behind `--walk` as a coverage option, not a speed one. The first
benchmark said the opposite because it sampled the head of the target file, which
is ordered by harvest frequency and therefore contains the largest boards.

## Performance

Individual requests cost ~0.4 s of server latency; connection reuse only buys
1.2x, so throughput is concurrency and request count.

| change | effect |
|---|---|
| 8 -> 32 workers | 8.1 -> 16.0 req/s (measured; 64 gives 18.6) |
| skip stale detail fetches | 699 requests avoided per 24 boards |
| board tiering | 43% of the boards per run |

## What the market actually looks like

The most useful output was not a job. Of US software postings in a 14-day window,
**6-8% are remote-eligible**, and that rate holds steady across 2, 7, 14 and
30-day windows — which is what tells you it is a property of the market rather
than a sampling artifact.

| window | posted | US | remote | Chicago |
|---|---|---|---|---|
| 48 hours | 402 | 151 | 9 | 1 |
| 14 days | 1,902 | 853 | 52 | 20 |
| 30 days | 3,360 | 1,579 | 83 | 45 |

Remote entry-level backend hiring is genuinely scarce. Chicago runs about 1.4
postings a day. Scanning harder does not change that; it just tells you the truth
sooner.

## Layout

```
scanner/     fetchers, eligibility, geo and salary extraction, the refresh runner
audits/      the scripts that found the bugs above - profiling, benchmarks, A/Bs
data/        discovered board tokens, and the current board output
```

`audits/` is kept deliberately. Every claim in this README came out of one of
those scripts, and they are how you would check the next one.

## Notes

Scanners are polite: timeouts with backoff, capped concurrency, and 429 handling.
Nothing here bypasses a login, a captcha, or a bot check — iCIMS' own
`careers-*.icims.com` hosts sit behind an AWS WAF captcha and are simply reported
as unreachable rather than worked around.

Board output in `data/` and `target_board.html` is a snapshot. Requisitions close
without notice; verify on the linked page before applying.
