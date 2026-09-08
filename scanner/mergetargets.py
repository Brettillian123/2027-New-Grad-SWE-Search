#!/usr/bin/env python3
"""Merge validated harvest results into the scan's target list.

    python mergetargets.py rescan_nonwd.json cc_targets.json [...] -o targets_all.json

Keeps the first spelling of a company seen for a given (ats, token) so the
curated names in rescan_nonwd.json win over the raw slugs the harvester produces.
"""
import argparse, collections, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--out", default="targets_all.json")
    a = ap.parse_args()

    seen, out, per_file = {}, [], []
    for f in a.files:
        p = os.path.join(HERE, f)
        if not os.path.exists(p):
            print("  skip %s (missing)" % f)
            continue
        rows = json.load(open(p, encoding="utf-8"))
        added = 0
        for t in rows:
            ats, tok = t.get("ats"), (t.get("token") or "").lower()
            if not ats or not tok:
                continue
            k = (ats, tok)
            if k in seen:
                continue
            seen[k] = True
            out.append({"company": t.get("company") or tok, "ats": ats, "token": t["token"]})
            added += 1
        per_file.append((f, len(rows), added))

    for f, n, added in per_file:
        print("  %-28s %6d rows -> %6d new" % (f, n, added))
    c = collections.Counter(t["ats"] for t in out)
    print()
    for k in sorted(c):
        print("  %-16s %6d" % (k, c[k]))
    json.dump(out, open(os.path.join(HERE, a.out), "w"), indent=1)
    print("\ntotal %d boards -> %s" % (len(out), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
