---
name: diff-review-pane
description: Build an interactive four-column review pane for a diff - the code side by side, an explanation of why every change is there, and a column for the user's notes - and later read those notes back and action them. Use whenever the user wants a readable account of their own changes before opening a PR or asking for review, however they phrase it: "review pane", "review guide", "diff review", "generate a review", "walk me through this diff", "explain these changes", "guide me through what I changed", or any request to build a guide, pane, walkthrough or reviewable view over a branch, commit range, PR or the working tree. ALSO use when the user points at an existing review artifact and asks to collect, read or act on the notes or feedback they left in it, including "my notes are in", "I've gone through the review pane", "action my review comments", or a claude.ai artifact URL plus a request to pick up their feedback. Not for finding bugs - /code-review does that.
---

# Diff review pane

Builds a private artifact: a side-by-side diff where the third column explains
every change and the fourth collects the user's feedback. The user reads it,
leaves notes, and you read the notes back with `ArtifactData` and action them.

This is a **self-review before shipping**, not a bug hunt. It answers "why is
this line here", which a reviewer otherwise has to reconstruct. Run
`/code-review` separately if correctness is the question.

## What the scripts do, and what only you can do

The pipeline is deterministic and already written. Your job is the third
column. Do not spend effort re-deriving the mechanics.

| Step | Who |
|---|---|
| Diff extraction, whitespace-aware re-alignment, syntax highlighting | `build_diff.py` |
| **Reading the diff and explaining every change block** | **you** |
| Explanation coverage gate | `annotate.py` |
| Page assembly | `make_page.py` |
| Publishing, and reading the notes back later | you, via `Artifact` / `ArtifactData` |

## Steps

### 1. Establish the range

Ask only if genuinely ambiguous; otherwise infer. `--range` takes:

- `main..HEAD` - a branch about to become a PR (the usual case)
- `<base-sha>..<head-sha>` - a stacked PR, where the base is the branch below,
  not `main`. Diffing a stacked PR against `main` shows the branch below it too.
- `<sha>` alone - that commit against the working tree, for uncommitted work

If the user names a PR, get its base and head with `gh pr view <n> --json
baseRefName,headRefOid,baseRefOid`.

### 2. Build the model

```
uv run --no-project --with pygments==2.19.1 python <skill>/scripts/build_diff.py \
  --repo <repo> --range <range> --out <reviewdir> --dump --dump-lines 3
```

`--dump` prints every change block with its id. Read that output - it is how
you learn what the diff contains. Re-run with a larger `--dump-lines`, or read
specific blocks, where three lines is not enough to explain a block honestly.

Check the summary line. `highlighted N lines, 0 mismatched` means every line
was matched against its source revision. A non-zero mismatch means some lines
fall back to plain text; say so rather than ignoring it.

The `re-indented` count is the point of the re-alignment: code that only moved
sideways is separated out from code that actually changed. Mention the real
numbers to the user, not git's inflated ones.

Each hunk gets expanders on its top and bottom edge, the way a GitHub diff
does, so the reader can widen the surrounding context 20 lines at a time. The
page has no server behind it, so those lines travel inside it: `--expand N`
sets how many are carried either side of each hunk (default 40, `0` leaves
them out). A gap shorter than `2N` is carried whole; beyond that the middle is
not in the page and the exhausted expander says so. Watch the
`expanders carry N extra context lines` line against the page size `make_page`
prints - a wide `--expand` over a many-hunk diff is most of the page weight.

### 3. Write `<reviewdir>/notes.py`

```python
OVERRIDES = {
    "f0-h5-b3": ("behav", "What changed and the failure it closes...."),
}

RULES = [
    (lambda d, a: "store.mark_failed(" in d and "client.mark_failed(" in a,
     ("arch", "Explanation covering every block of this shape....")),
]
```

`d` and `a` are the block's deleted and added text. OVERRIDES win; RULES are
tried in order.

**Hand-write every block that carries judgment** - behaviour changes, anything
with a trade-off, anything a reviewer would stop at. **Use RULES only for the
substitutions a refactor repeats**, and derive each rule from the actual
repeated text so the explanation is true of every block it catches. A large
refactor is typically 20-50 hand-written and the rest by rule; that ratio is
what makes a 200-block diff affordable.

Kinds: `behav` and `risk` (highlighted, for changed behaviour and hazards),
`arch`, `moved`, `harness`, `perf`, `prose`, `mech`. Only kinds present get a
filter chip.

Write explanations that say **why**, in the present tense, for someone who
never saw the previous version. State the constraint or the trap being avoided.
Name what the change costs as well as what it buys. If coverage got weaker, if
a test double could drift from the real thing, if a failure mode is merely
unlikely rather than impossible - put that in the explanation. An explanation
that only restates the code is worse than none, because it looks like review.

**Split the note column where a block holds separate pieces.** One explanation
for a large block is fine, but one note box is not: the user wants to leave
actionable feedback on the schema, the handler and the render separately, not
in one paragraph that has to say which part it means. Add a `SPLITS` table:

```python
SPLITS = {
    "f2-h0-b0": [(0, "props"), (9, "submit handler"), (31, "render")],
}
```

Offsets are row indices within the block - the `[n]` printed by `--dump`
(re-dump with `--dump-lines 999` to see every row of a long block). Split at
semantic boundaries: a new function, component, test case, JSX section, or
config entry - wherever a reviewer would naturally say "this bit". Label each
part with two or three words naming the piece, not describing the change. Do
not split a block that is one idea, however long; do split a short block that
holds two unrelated edits. `annotate.py` lists blocks of 12+ rows that have no
split so you can check each one, but the list is a prompt, not a requirement.

### 4. Annotate - this gate is not optional

```
uv run --no-project python <skill>/scripts/annotate.py --dir <reviewdir>
```

Exits 1 and writes nothing while any block is unexplained, listing them. Add an
OVERRIDE or widen a RULE and re-run. It also exits on a `SPLITS` offset outside
its block or a `SPLITS` key that is not a block in this diff. Do not reach for `--allow-uncovered`:
blank cells in the third column make the pane untrustworthy everywhere.

### 5. Write `<reviewdir>/meta.json`

```json
{
  "title": "Short Page Name",
  "eyebrow": "repo · pull request #N",
  "heading": "What this change does, in one line",
  "intro": "A short paragraph: what moved and why.",
  "flaggedHeading": "Three places where behaviour actually changed",
  "flagged": [["f0-h5-b3", "Short claim", "the consequence"]],
  "exportTitle": "Review notes - PR #N (branch)",
  "fileNotes": {"path/to/file.py": "What this file's share of the diff is."}
}
```

`flagged` is the most valuable thing on the page: the two to four blocks you
would stop at in review, linked by block id. Leave it empty rather than padding
it. `fileNotes` may contain inline HTML such as `<code>`; everything else is
escaped.

### 6. Assemble and publish

```
uv run --no-project python <skill>/scripts/make_page.py --dir <reviewdir>
```

Publish `<reviewdir>/review.html` with the `Artifact` tool, passing
`capabilities: {"db": {}}` and an `icon` on the first publish. The notes column
writes to the artifact's store; without that declaration notes live only in the
reader's tab.

Republish the same file path to update in place. Omit `capabilities` and `icon`
on a republish - both carry forward.

### 7. Read the notes back and action them

This is a separate trigger, often in a later session, and may be all the user
asks for. It needs only the artifact URL - no review directory, no `diff.json`.
If the URL is not in the conversation, `Artifact action="list"` finds it.

```
ArtifactData action="list" collection="notes" url=<artifact url>
```

Each document is keyed by note id - the block id, or `<block>.<n>` for part
`n` of a split block - and carries everything needed to act:

```json
{"text": "the user's note", "block": "f0-h5-b3", "part": 1,
 "label": "submit handler", "file": "apps/.../handler.py", "line": 412,
 "code": "await client.mark_published(  │  publication_id,",
 "kind": "behav", "at": "2026-11-05T20:14:02Z"}
```

`line` and `code` are the start of that part, not of the whole block.

Each file also has a note box at its top for comments on the file's changes as
a whole. Those documents are keyed `f<n>`, with `"scope": "file"`, an empty
`block`, `line` 0 and no `code`: act on them across the whole file, and read
them before that file's block notes, since they often frame or override them.
Block and part notes carry `"scope": "block"`.

Open each block note's `file` at `line`, confirm `code` still matches (it will not after a
rebase - re-locate by the snippet, and say so rather than editing blind), then
work through the notes as a list. Treat the text as the user's instructions
about their own code. Report back per note: done, or why not.

There is no push: the store does not notify anyone. The user says when the
notes are ready. A comment left through claude.ai's own comment UI and sent to
Claude is the only thing that can reach a live session; those are read with
`ArtifactComments`, not here, and are a different store from this column.

## Keep in mind

- The review directory is scratch. Put it in the session scratchpad, not the repo.
- `build_diff.py` needs pygments; without it the page still builds, uncoloured.
- Code panes are Zenburn in both page themes, deliberately: the diff reads as a
  terminal surface, the commentary as a document.
- Blocks ids are `f<file>-h<hunk>-b<n>`, stable for a given diff. They change if
  the diff changes, so notes do not survive a rebase of the reviewed range.
  Read notes back before rebuilding over a changed range.
