---
name: flow-map
description: Build a flow map artifact for a pull request, branch or feature - a drawn user flow diagram from every entry point to every outcome, plus a table of the terms the code introduces and the existing terms it relies on. Use when the user wants to understand how a change behaves for a user rather than why each line is there, however they phrase it: "flow map", "map this PR", "flow map for PR 1234", "map the flow", "user flow diagram", "draw the user flow", "flow and glossary", "terms and flow", "table of terms", "define the new concepts", "what are the new concepts in this PR", or any request for a diagram of the user journey together with definitions. Most useful for frontend work with several entry points, dialogs, confirmations and error states. Not a line-by-line account of a diff - diff-review-pane does that, and owns "review guide", "review pane" and "walk me through this diff". Not for finding bugs - /code-review does that.
---

# Flow map

Builds a private artifact that lets someone who has not read the code see what
a change does for a user: one drawn flow from every entry point to every
outcome, the terms the code introduces, and the things that are easy to miss.

It answers "what happens when the user does this, and what is this thing
called". It does not explain the diff line by line and it is not a bug hunt,
though reading for the flow often turns up questions worth raising.

## Steps

### 1. Read the change and the code it runs through

For a PR:

```
gh pr view <n> --json title,body,headRefName,baseRefName,files
gh pr diff <n> > <scratchpad>/pr.diff
git fetch -q origin <headRefName>
git show "origin/<headRefName>:<path>"
```

Quote the `ref:path` argument. In zsh an unquoted `$B:src/...` applies a
history modifier to the variable and the path comes out mangled.

Read in this order, and read whole files rather than diff hunks for the first
two groups:

1. The pure logic the change adds (rules, plans, reducers, selectors).
2. The hooks and components that drive it, and every place it is opened from.
3. The pre-existing code the flow passes through: the queue, router, cache
   invalidation or parent screen that decides what the user sees next. The
   answer to "what happens after success" is usually here and not in the diff.
4. The API function, the mutation hook and its `onSuccess` and `onError`.
5. Test names, as evidence of intended behaviour. Skip the test bodies unless
   a behaviour is unclear.

For a branch or a feature with no PR, do the same from `git diff <base>...HEAD`
or from the feature's entry components.

### 2. Extract the flow

Write down, before drawing anything:

- **Entry points.** Every place the user can start, with the flag or
  permission that gates it.
- **The shared core.** The steps every entry point converges on.
- **Choices.** What the user can change, and what each choice changes
  downstream. Name the choice that has a non-obvious effect.
- **Exits that do nothing.** Each Cancel, and what state it keeps or drops.
- **The point of no return.** The confirmation and the request, with the
  method, path and what the body carries.
- **Outcomes.** Success and each distinct error, with the exact toast or
  message text and whether the screen stays open.
- **What each entry point does after success.** Navigation, a closed dialog, a
  row leaving a list, a queue moving on.
- **Server follow-ups the UI does not wait for.** Background tasks, eventual
  counts, anything the user could see as stale.

### 3. Extract the terms

Two tables, kept apart:

- **New terms**: every concept the change introduces. A term is a concept, not
  a file. One or two plain sentences, then the symbol or file where it lives.
- **Existing terms the flow relies on**: only the ones a reader needs in order
  to follow the diagram.

Add a small mapping table when UI names and wire names differ, or when a set
of fields, states or variants is central to the change.

Define each term in the user's language first and the code's second. Use the
same word for the same thing in the diagram, the tables and the notes.

### 4. Say how each claim was established

Nothing in a flow map is run unless you ran it, so say so in the lede. Then,
for every statement about behaviour:

- If it comes from code you read end to end, state it plainly.
- If it depends on a file you have not read, read the file. Do not publish
  "inferred" where five minutes of reading would settle it.
- If it depends on timing, on a server you cannot see, or on a browser, put it
  in "Easy to miss" and say it was not verified.

"Easy to miss" holds three to five notes: a flow with no way back, a choice
with a hidden effect, a stale number, a guard that covers the first load but
not a refetch. Each note is a short claim and one or two sentences.

### 5. Build the page

Copy `<skill>/assets/template.html` to the scratchpad as
`<feature>-flow-map.html` and fill it in. Keep its `<style>` block: it carries
the theme tokens for light and dark, the diagram classes and the table styles.

Diagram rules, learned the hard way:

- Hand-author the SVG at `viewBox` width 960 and set the height for the
  content. The page scrolls the figure sideways on a phone.
- Lay it out on a grid. Rows about 130px apart, boxes 56 to 120px tall, all
  left edges on a few shared x values.
- Entry points across the top, the shared core as wide accent boxes
  (`box-main`), the confirmation and the request as `box-warn`, outcomes
  across the bottom. Existing behaviour the change leaves alone is dashed
  (`box-aside`, `edge-aside`).
- Text is about 6.2px per character at the sub-line size. A 250px box holds
  about 34 characters per line. Count before you write; split long lines.
- Box title at `y + 26`, sub lines every 18px after that, text inset 16px.
- Put an edge label beside its line, 10px to the right, never on top of it.
  Label every edge with the button or event that causes it.
- Keep sentences out of the drawing. What each entry point does after success
  goes in the HTML cards under the figure, not in the SVG.
- One marker definition, `fill` through the `head` class, no `<style>` or
  `<foreignObject>` inside the SVG.

Page rules:

- Title the page `<Feature> Flow Map`, two to four words. Avoid "guide" and
  "review" in the title, which belong to other artifacts.
- The eyebrow carries the repo, PR number and ticket.
- Diagram first, then "After success", then "Easy to miss", then the tables.
- No emojis. Plain sentences. Exact UI copy in quotation marks.

### 6. Publish and report

Publish with the `Artifact` tool: the page's file path, an `icon` of one
generic word, and a one-sentence `description`. It is private until the user
shares it.

In the reply, give the link, one sentence on what the page holds, and whatever
is not verified, including that the rendered layout was not previewed if it
was not. Do not repeat the tables in the terminal.

### 7. Follow-up questions

The user will ask about the flow after reading it. For each question:

- Answer from the code, reading whatever file settles it.
- If the answer corrects or sharpens the page, edit the same file and publish
  it again in the same turn, so the link stays current.
- If the answer is a gap in the change itself, name the file and line where a
  review comment belongs. Post a comment only when asked.
