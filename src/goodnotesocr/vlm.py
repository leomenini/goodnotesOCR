"""Thin client over the Gemini API.

Two calls: transcribe a small fragment image to a LaTeX body, and locate a
diagram inside a fragment (a normalized box, or nothing). Cost controls: a
lite model, thinking at the minimum level (thinking tokens are billed as
output and were the bulk of the spend before), per-unit crops rather than
whole pages, and a tiny output budget for the locate call. Every call
returns its token usage so the pipeline logs real spend.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

DEFAULT_MODEL = "gemini-3.5-flash-lite"

_TRANSCRIBE_PROMPT = """This image is one fragment of a handwritten page: a single equation,
a short derivation, or a short paragraph with inline math.

Transcribe it to LaTeX. Rules:
- Output ONLY LaTeX body text. It will be pasted verbatim inside a document
  that already loads amsmath, amssymb and amsthm. No \\documentclass, no
  \\usepackage, no \\begin{document}.
- No Markdown of any kind (no #, no **, no bullet asterisks, no code fences).
- No introductory or closing sentences; start directly with the content.
- Standalone equations go in \\[ ... \\] or an align* environment; math inside
  prose goes in $...$. Use \\boxed{} for boxed results, \\underline{} for
  underlined words.
- Keep the original language of the prose; do not translate.
- Transcribe what is written; do not add explanations or corrections.
"""

_LOCATE_PROMPT = """This image is a crop of a handwritten page. Does it contain a diagram,
sketch or plot (a figure with axes, curves, vectors, geometric shapes, or a
drawn picture)? Equations, formulas, boxed formulas, underlines, braces,
arrows between formulas and integral signs are NOT diagrams.

Answer with JSON only, no other text:
{"diagram": false}
or
{"diagram": true, "box": [ymin, xmin, ymax, xmax]}
where the box coordinates are integers from 0 to 1000 relative to the image
(0,0 top-left), tightly enclosing the diagram together with its labels.
"""

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class Usage:
    text: str
    prompt_tokens: int
    output_tokens: int
    thought_tokens: int
    model: str


_client: genai.Client | None = None

# Free tier allows 15 requests/minute/model; space calls so a sequential run
# never trips it, and honor the retry delay the API sends when it does.
MIN_CALL_INTERVAL_S = 4.5
_last_call_at = 0.0
_RETRY_DELAY_RE = re.compile(r"retry in (\d+(?:\.\d+)?)s", re.IGNORECASE)


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        load_dotenv(dotenv_path=".env")
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def _throttle() -> None:
    global _last_call_at
    wait = MIN_CALL_INTERVAL_S - (time.monotonic() - _last_call_at)
    if wait > 0:
        time.sleep(wait)
    _last_call_at = time.monotonic()


def _call(png_bytes: bytes, prompt: str, model: str, max_output_tokens: int, retries: int) -> Usage:
    config = types.GenerateContentConfig(
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
    )
    contents = [types.Part.from_bytes(data=png_bytes, mime_type="image/png"), prompt]

    for attempt in range(retries):
        _throttle()
        try:
            response = _get_client().models.generate_content(model=model, contents=contents, config=config)
            break
        except errors.ServerError:
            if attempt == retries - 1:
                raise
            time.sleep(5 * (attempt + 1))
        except errors.ClientError as e:
            if e.code != 429 or attempt == retries - 1:
                raise
            m = _RETRY_DELAY_RE.search(str(e))
            time.sleep(float(m.group(1)) + 1 if m else 60)

    u = response.usage_metadata
    return Usage(
        text=response.text or "",
        prompt_tokens=u.prompt_token_count or 0,
        output_tokens=u.candidates_token_count or 0,
        thought_tokens=u.thoughts_token_count or 0,
        model=model,
    )


def transcribe_to_latex(png_bytes: bytes, model: str = DEFAULT_MODEL, max_output_tokens: int = 4096, retries: int = 4) -> Usage:
    return _call(png_bytes, _TRANSCRIBE_PROMPT, model, max_output_tokens, retries)


def locate_drawing(png_bytes: bytes, model: str = DEFAULT_MODEL, retries: int = 4) -> tuple[list[int] | None, Usage]:
    """Returns ([ymin, xmin, ymax, xmax] in 0-1000, usage) or (None, usage)."""
    u = _call(png_bytes, _LOCATE_PROMPT, model, max_output_tokens=64, retries=retries)
    m = _JSON_RE.search(u.text)
    if not m:
        return None, u
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, u
    box = data.get("box") if data.get("diagram") else None
    if not (isinstance(box, list) and len(box) == 4):
        return None, u
    box = [max(0, min(1000, int(v))) for v in box]
    if box[2] <= box[0] or box[3] <= box[1]:
        return None, u
    return box, u
