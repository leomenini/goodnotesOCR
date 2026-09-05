# CLAUDE.md

Project context for agents. Read all of it before writing code.

## What this is

A personal tool that turns handwritten notes taken on an iPad with GoodNotes
into usable text and LaTeX. Personal use, not a product.

The long-term goal is to stop typing up exercises and notes by hand.

**This is not a classic OCR project.** See "Decisions already made".

## State

An end-to-end pipeline works: exported PDF → Gemini → LaTeX → compiled with
`tectonic` as verification. See `README.md` for architecture, usage and
current limitations.

The mandatory baseline has been run and **it changed the project's direction**.
Read "Baseline results" below before proposing anything.

## Available inputs

Each notebook syncs to Nextcloud in two formats:

- `*.goodnotes` — native format, keeps the strokes
- `*.pdf` — rasterized export of the same notebook

The real working corpus is in
`/home/leo/Desktop/Files/ING/goodnotes/Backup 07-26/PDFS/`: dozens of
`.goodnotes`/`.pdf` pairs from Physics 3, Newtonian Mechanics and
Programming 1. The exported PDF has one page per notebook page, in the same
order.

**Careful with the sample**: not every page is native ink. Some pages have
their maths content as a pasted image (PNG attachment) and only the title as
strokes. Before using a page to test stroke parsing, check `len(page.strokes)`
and `len(page.image_elements)`.

## What is already known about the `.goodnotes` format

No need to research this again:

- It is a **standard ZIP**. Ordinary tools open it.
- Inside: `schema.pb`, `index.notes.pb` (pages → `notes/<UUID>`),
  `index.attachments.pb`, `index.events.pb`, and `notes/` with a stream of
  Protobuf records per page.
- Stroke data comes wrapped in **Apple's proprietary Framed LZ4** (`bv41` /
  `bv4$`), and inside it a **TPL** memory image holds the points.
- Per stroke you can recover: UUID, colour, alpha, width, and points with
  pressure.

**Do not implement this parsing from scratch.**
`Kaih1825/parser-for-goodnotes` exists (pure Python, MIT, CLI `gn-inspect`,
`gn-dump`, `gn-export-json`, `gn-export-svg`, plus a `GoodNotesDocument` API).
It was validated against the author's own files: it reads real notebooks
correctly.

`hudsonmp/goodnotes-mcp` runs Apple Vision over the thumbnail or the PDF, **not**
over the strokes. It only serves as a reference for what is not enough; it is
not a dependency of this project.

### Two real bugs found while rendering strokes

If strokes are ever rendered again, this is already diagnosed (the code lives
on the `experiment/stroke-figures` branch):

1. **Corrupt pressure.** Some strokes decode with an absurd pressure value
   (287 was observed where the range is 0-1). Since ribbon width comes from
   `width * pressure`, the stroke inflates and covers half the page. The
   parser ships a precomputed vector path in `stroke.native_cgpaths` for those
   cases: use it when present, and sanitize pressure with `is_valid_pressure`
   everywhere else. Reproducible in `Fis3 Pr3.goodnotes`, page 2, stroke 135.
2. **Double scaling.** Point coordinates are in 132 DPI and must be multiplied
   by `72/132`. `page.dimensions` is **already** in 72 DPI: scaling it too
   shrinks the canvas and crops content.

## Baseline results (already run, do not repeat)

Over 5 real pages from different notebooks, with dense maths:

1. **GoodNotes native conversion** (lasso → "Convert to text"): fails
   completely on maths. Returns the image without converting anything.
2. **Raw PDF → VLM**: complete and correct transcription.
3. **Clean SVG rendered from strokes → same VLM**: equivalent to (2).
   Sometimes a tie, sometimes worse (less faithful notation, truncations).

**Conclusion, already applied: stroke parsing is not justified.** The exported
PDF performs just as well for a fraction of the work. The current pipeline
does not open the `.goodnotes` file at all.

## Decisions already made

Do not reopen without discussing:

1. **Tesseract is ruled out.** Printed text, line by line, no 2D structure.
   Useless for fractions, integrals, subscripts and handwriting.
2. **There is no viable open source online recognizer.** Having the strokes
   does NOT give you a recognizer. Serious handwritten maths recognition today
   is MyScript, and it is proprietary.
3. **The pipeline starts from the exported PDF, not from strokes.** Reversed
   from the original idea, because of the baseline above.
4. **Mechanical verification.** LaTeX output that does not compile is failed
   output. `tectonic` is used for this.
5. **Granularity: whole page, one call per page.** Segmenting into
   exercise-sized units and calling once per unit was tried: it cuts cost by an
   order of magnitude but **makes quality worse**, because the crop loses
   context and a lot of malformed LaTeX shows up. It lives on the
   `experiment/stroke-figures` branch; do not go back to it without a new
   reason.
6. **No figures extracted from strokes.** Tried on the same branch: Gemini
   locates the diagram, the strokes in that box get embedded as a vector PDF.
   It works, but the boxes swallow neighbouring prose and the overall result is
   worse than describing the diagram in one line of text.

## Open decisions — ask, do not settle them alone

- **Indexable text** as a second output (searching the notebooks). Today only
  LaTeX is produced. It could be derived by flattening the LaTeX; not done.
- **Quality metric.** Today: a compile gate plus eyeballing against the source
  page on a small fixed set. There is no automatic fidelity metric; building
  one needs hand-written reference transcriptions.
- **Cost.** A dense page costs around 30K output tokens with
  `gemini-3.6-flash`, largely thinking tokens. Reducing that without losing
  quality is unsolved (lowering granularity was tried and made quality worse).
- **Whole-notebook processing.** Today pages are run one at a time by hand.

## How to work here

- Environment: WSL, Python 3.13 with `uv`. The author already uses
  pandas/matplotlib/scipy and `tectonic`.
- Ask before settling architecture or adding heavy dependencies. The author
  prefers discussing alternatives and constraints over receiving a finished
  implementation.
- Start with the smallest thing that produces evidence. One real page is worth
  more than a complete pipeline over invented data.
- Do not generate synthetic test data: the corpus is the real notebooks.
- Nothing counts as "done" without verification: if the output is LaTeX, it has
  to compile.
- The Gemini key lives in `.env` (git-ignored). The free tier allows 15 calls
  per minute per model and returns 503 often: retry.
