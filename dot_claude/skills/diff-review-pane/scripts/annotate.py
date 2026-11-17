"""Attach one explanation to every change block, and refuse to finish if any
block would be left without one.

Reads a review-local `notes.py` defining:

    OVERRIDES = {"f0-h4-b1": ("behav", "Why this block is here...."), ...}
    RULES = [(lambda d, a: <predicate on the block's deleted/added text>,
              ("mech", "Explanation for every block matching that shape.")), ...]

OVERRIDES win. RULES are tried in order and exist for the substitutions a
refactor repeats dozens of times, so those get a real explanation derived
from their actual content instead of filler. A block matching neither is a
hard failure: a review pane whose third column sometimes says nothing is
worse than no review pane.
"""

import argparse, importlib.util, json, os, sys

sys.dont_write_bytecode = True
from collections import Counter

KINDS = {"behav", "arch", "moved", "harness", "prose", "mech", "perf", "risk"}


def load(path):
    spec = importlib.util.spec_from_file_location("review_notes", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, "OVERRIDES", {}), getattr(mod, "RULES", [])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="review directory (diff.json, notes.py)")
    ap.add_argument("--allow-uncovered", action="store_true",
                    help="escape hatch: write ann.json anyway (the page will show blanks)")
    args = ap.parse_args()

    d = json.load(open(os.path.join(args.dir, "diff.json")))
    overrides, rules = load(os.path.join(args.dir, "notes.py"))

    ann, uncovered = {}, []
    for f in d["files"]:
        for h in f["hunks"]:
            bl = {}
            for r in h["rows"]:
                if "b" in r:
                    bl.setdefault(r["b"], []).append(r)
            for bid, rows in bl.items():
                dt = "\n".join(r["l"] for r in rows if "l" in r)
                at = "\n".join(r["r"] for r in rows if "r" in r)
                if bid in overrides:
                    k, t = overrides[bid]; src = "hand"
                else:
                    hit = None
                    for pred, val in rules:
                        try:
                            ok = pred(dt, at)
                        except Exception as e:
                            sys.exit("RULE raised on %s: %s" % (bid, e))
                        if ok:
                            hit = val; break
                    if hit:
                        k, t = hit; src = "rule"
                    else:
                        k, t, src = "mech", "", "none"
                        uncovered.append((bid, f["path"], dt.strip()[:70], at.strip()[:70]))
                if k not in KINDS:
                    sys.exit("unknown kind %r on %s (expected one of %s)" %
                             (k, bid, ", ".join(sorted(KINDS))))
                ann[bid] = {"k": k, "t": t, "s": src}

    print(dict(Counter(v["k"] for v in ann.values())))
    print(dict(Counter(v["s"] for v in ann.values())))
    if uncovered:
        print("\nUNCOVERED %d block(s) - add an OVERRIDE or widen a RULE:" % len(uncovered))
        for bid, path, dt, at in uncovered:
            print("  %-14s %s\n      - %s\n      + %s" % (bid, path, dt, at))
        if not args.allow_uncovered:
            sys.exit(1)

    json.dump(ann, open(os.path.join(args.dir, "ann.json"), "w"))
    print("\nwrote ann.json (%d blocks)" % len(ann))


main()
