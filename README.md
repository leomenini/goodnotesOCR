# goodnotesOCR

Turns a page of handwritten GoodNotes notes into compilable LaTeX.

Takes a page from the PDF GoodNotes exports, sends it to Gemini, and compiles
the result with `tectonic`. LaTeX that does not compile counts as a failure.

Personal tool for physics and maths notes.

## Setup

Needs Python 3.13, [uv](https://docs.astral.sh/uv/) and
[tectonic](https://tectonic-typesetting.github.io/). Run `uv sync`, then put
`GEMINI_API_KEY=...` in a `.env` file at the repo root.

## Usage

```python
from goodnotesocr import pipeline

result = pipeline.run_page("notebook.pdf", page_index=1)  # 0-indexed
print(result.compiled)      # True if the LaTeX compiled
print(result.tex_path)      # out/pipeline/notebook_p2.tex
print(result.pdf_out_path)  # out/pipeline/notebook_p2.pdf, only if it compiled
print(result.log_path)      # tectonic log, useful when it fails
```

## Architecture

Four modules in `src/goodnotesocr/`, one per step:

**`pdf_render.py`** — Rasterizes a PDF page to PNG with `pymupdf`, 200 DPI by
default.

**`vlm.py`** — Gemini client. Sends the image plus a fixed prompt that asks for
the document body only and explicitly forbids Markdown, preamble, opening
sentences and code fences. Without those rules the model returns Markdown with
embedded formulas, which does not compile. Diagrams are requested as a
one-line bracketed description.

**`verify.py`** — Wraps the body in a minimal preamble and compiles it with
`tectonic`, returning success, the log and the PDF bytes.

**`pipeline.py`** — Chains the three steps and writes `.tex`, `.pdf` and log
under `out/pipeline/`.

### Preamble notes

`tectonic` runs XeTeX, where two parts of the obvious preamble fail in
non-obvious ways:

- With `inputenc`/`fontenc`, `¿` renders as `£`. `fontspec` is used instead.
- Spanish `babel` makes the straight quote an active character, turning
  `"Conductor"` into `Çonductor"`. It is loaded with `es-noshorthands`.

## Limitations

- One page per call; there is no whole-notebook processing.
- A dense page costs around 30K output tokens.
- Diagrams are not reproduced, only described in a sentence.
- The Gemini free tier allows 15 calls per minute per model and returns 503
  often. Retry with a wait.

## License

MIT.
