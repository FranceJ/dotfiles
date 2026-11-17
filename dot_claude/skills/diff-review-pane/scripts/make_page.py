"""Assemble the review page: diff.json + ann.json + meta.json into one HTML file."""

import argparse, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def embed(path):
    s = open(path).read()
    # U+2028/9 are line terminators in JS source; "</" would end the script early.
    return s.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029").replace("</", "<\\/")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", help="output html (default <dir>/review.html)")
    args = ap.parse_args()

    d = args.dir
    meta_path = os.path.join(d, "meta.json")
    if not os.path.exists(meta_path):
        sys.exit("meta.json missing in " + d)
    meta = json.load(open(meta_path))
    for key in ("title", "heading", "intro"):
        if not meta.get(key):
            sys.exit("meta.json needs a non-empty %r" % key)

    tpl = open(os.path.join(HERE, "page.tpl.html")).read()
    out = (tpl
           .replace("__TITLE__", meta["title"])
           .replace("__META__", embed(meta_path))
           .replace("__DIFF__", embed(os.path.join(d, "diff.json")))
           .replace("__ANN__", embed(os.path.join(d, "ann.json"))))
    for ph in ("__TITLE__", "__META__", "__DIFF__", "__ANN__"):
        assert ph not in out, ph

    dest = args.out or os.path.join(d, "review.html")
    open(dest, "w").write(out)
    print("%s  (%d KB)" % (dest, round(len(out) / 1024)))


main()
