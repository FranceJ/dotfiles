"""Turn a git diff into an aligned, syntax-highlighted JSON model.

Two things make this different from reading `git diff`:

1. Hunks are re-aligned on whitespace-insensitive matching, so code that only
   moved left or right (a dedent after an `if` or `with` block is removed)
   is reported as "re-indented" rather than as deleted-and-re-added. On a
   refactor that unwraps nesting this is the difference between a reviewable
   diff and a wall of green.
2. Highlighting runs over the COMPLETE file at each revision and is sliced
   back onto the diff by line number, with an assertion that each line's text
   matches its source. Highlighting diff lines in isolation mislexes anything
   spanning lines - docstrings, block comments, template literals.
"""

import argparse, difflib, json, os, re, subprocess, sys

try:
    from pygments import highlight as _hl
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_for_filename
    from pygments.util import ClassNotFound
    HAVE_PYGMENTS = True
except ImportError:
    HAVE_PYGMENTS = False


def git(repo, *args):
    r = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def norm(s):
    return re.sub(r"\s+", " ", s.strip())


def parse(diff_text):
    files, cur, hunk = [], None, None
    lines = diff_text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            cur = {"path": m.group(2), "old_path": m.group(1), "hunks": []}
            files.append(cur)
            hunk = None
        elif line.startswith("@@") and cur is not None:
            m = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@(.*)", line)
            if m:
                hunk = {"label": m.group(3).strip(), "lstart": int(m.group(1)),
                        "rstart": int(m.group(2)), "lines": []}
                cur["hunks"].append(hunk)
        elif hunk is not None and line[:1] in (" ", "-", "+") and line != "":
            if not line.startswith("--- ") and not line.startswith("+++ "):
                hunk["lines"].append(line)
        elif hunk is not None and line == "" and i + 1 < len(lines) \
                and not lines[i + 1].startswith("diff --git"):
            hunk["lines"].append(" ")
        i += 1
    return files


def align(files):
    """Pair old and new lines by normalized text, so a pure re-indent reads
    as one row with both sides present rather than a delete plus an add."""
    out = []
    for fi, f in enumerate(files):
        adds = dels = indent = 0
        hunks = []
        for hi, h in enumerate(f["hunks"]):
            old, new = [], []
            ln, rn = h["lstart"], h["rstart"]
            for raw in h["lines"]:
                tag, text = raw[0], raw[1:]
                if tag in (" ", "-"):
                    old.append((text, ln)); ln += 1
                if tag in (" ", "+"):
                    new.append((text, rn)); rn += 1
            sm = difflib.SequenceMatcher(None, [norm(t) for t, _ in old],
                                         [norm(t) for t, _ in new], autojunk=False)
            rows, bn = [], 0
            for tag, i1, i2, j1, j2 in sm.get_opcodes():
                if tag == "equal":
                    for k in range(i2 - i1):
                        lt, lno = old[i1 + k]
                        rt, rno = new[j1 + k]
                        t = "ctx" if lt == rt else "ind"
                        if t == "ind":
                            indent += 1
                        rows.append({"t": t, "l": lt, "ln": lno, "r": rt, "rn": rno})
                else:
                    bid = "f%d-h%d-b%d" % (fi, hi, bn); bn += 1
                    dl, nl = old[i1:i2], new[j1:j2]
                    for k in range(max(len(dl), len(nl))):
                        d = dl[k] if k < len(dl) else None
                        a = nl[k] if k < len(nl) else None
                        row = {"b": bid}
                        if d and a:
                            row.update(t="chg", l=d[0], ln=d[1], r=a[0], rn=a[1])
                            dels += 1; adds += 1
                        elif d:
                            row.update(t="del", l=d[0], ln=d[1]); dels += 1
                        else:
                            row.update(t="add", r=a[0], rn=a[1]); adds += 1
                        rows.append(row)
            hunks.append({"label": h["label"], "lstart": h["lstart"],
                          "rstart": h["rstart"], "rows": rows})
        out.append({"path": f["path"], "adds": adds, "dels": dels,
                    "indent": indent, "hunks": hunks})
    return out


def side_text(repo, rev, path):
    """File contents at a revision; None for the working tree sentinel."""
    if rev is None:
        full = os.path.join(repo, path)
        try:
            with open(full, encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None
    return git(repo, "show", f"{rev}:{path}")


def add_highlighting(repo, files, old_rev, new_rev):
    if not HAVE_PYGMENTS:
        print("  (pygments missing - no syntax colour)", file=sys.stderr)
        return 0, 0
    fmt = HtmlFormatter(nowrap=True)
    checked = bad = 0
    for f in files:
        try:
            lexer = get_lexer_for_filename(f["path"], stripnl=False, ensurenl=False)
        except ClassNotFound:
            continue
        for rev, path, key_text, key_no, key_html in (
            (old_rev, f.get("old_path", f["path"]), "l", "ln", "lh"),
            (new_rev, f["path"], "r", "rn", "rh"),
        ):
            src = side_text(repo, rev, path)
            if src is None:
                continue
            plain = src.split("\n")
            lit = _hl(src, lexer, fmt).split("\n")
            for h in f["hunks"]:
                for r in h["rows"]:
                    if key_text not in r:
                        continue
                    n = r[key_no]
                    if not (0 < n <= len(lit)):
                        continue
                    checked += 1
                    if plain[n - 1] == r[key_text]:
                        r[key_html] = lit[n - 1]
                    else:
                        bad += 1
    return checked, bad


def dump(files, maxlines):
    for f in files:
        print("\n==== %s  +%d/-%d  (%d re-indented)" %
              (f["path"], f["adds"], f["dels"], f["indent"]))
        for h in f["hunks"]:
            bl = {}
            for r in h["rows"]:
                if "b" in r:
                    bl.setdefault(r["b"], []).append(r)
            for bid, rows in bl.items():
                dls = [r["l"] for r in rows if "l" in r]
                ads = [r["r"] for r in rows if "r" in r]
                print("### %s (-%d/+%d)" % (bid, len(dls), len(ads)))
                for x in dls[:maxlines]:
                    print("  -", x.strip()[:110])
                if len(dls) > maxlines:
                    print("  - ...%d more" % (len(dls) - maxlines))
                for x in ads[:maxlines]:
                    print("  +", x.strip()[:110])
                if len(ads) > maxlines:
                    print("  + ...%d more" % (len(ads) - maxlines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".")
    ap.add_argument("--range", help="OLD..NEW, or OLD alone to diff against the working tree")
    ap.add_argument("--out", required=True, help="directory for diff.json")
    ap.add_argument("--dump", action="store_true", help="print every change block")
    ap.add_argument("--dump-lines", type=int, default=40)
    ap.add_argument("--context", type=int, default=3)
    args = ap.parse_args()

    repo = os.path.abspath(os.path.expanduser(args.repo))
    spec = args.range or "HEAD"
    if ".." in spec:
        old_rev, new_rev = spec.split("..", 1)
        new_rev = new_rev or None
        diff_args = [f"-U{args.context}", old_rev] + ([new_rev] if new_rev else [])
    else:
        old_rev, new_rev = spec, None
        diff_args = [f"-U{args.context}", old_rev]

    text = git(repo, "diff", *diff_args)
    if text is None:
        sys.exit("git diff failed for: " + spec)
    if not text.strip():
        sys.exit("no changes in: " + spec)

    files = align(parse(text))
    checked, bad = add_highlighting(repo, files, old_rev, new_rev)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "diff.json"), "w") as fh:
        json.dump({"files": files}, fh)

    total = 0
    for f in files:
        nb = sum(len({r["b"] for r in h["rows"] if "b" in r}) for h in f["hunks"])
        total += nb
        print("%-62s real +%d/-%d  re-indented %d  hunks %d  blocks %d" %
              (f["path"][-62:], f["adds"], f["dels"], f["indent"], len(f["hunks"]), nb))
    print("TOTAL BLOCKS %d   highlighted %d lines, %d mismatched" % (total, checked, bad))
    if bad:
        print("WARNING: %d lines did not match their source revision; "
              "those lines fall back to plain text." % bad, file=sys.stderr)
    if args.dump:
        dump(files, args.dump_lines)


main()
