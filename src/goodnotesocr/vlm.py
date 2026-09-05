"""Thin client over the Gemini API for transcribing a page image to LaTeX."""
from __future__ import annotations

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

_PROMPT = """Transcribe the handwritten content in this image to LaTeX.

Rules:
- Output ONLY the body of a LaTeX document. It will be pasted verbatim between
  \\begin{document} and \\end{document} of a document that already loads
  amsmath, amssymb and amsthm. Do not emit \\documentclass, \\usepackage,
  \\begin{document} or \\end{document}.
- No Markdown of any kind: no ###, no **bold**, no bullets with * or -, no
  horizontal rules, no code fences, no HTML tags.
- No introductory or closing sentences. Start directly with the content.
- Use \\section*{...} for headings, \\textbf{...} / \\underline{...} for
  emphasis, and itemize/enumerate environments for lists.
- Use display math (\\[ ... \\] or align*) for standalone equations and
  inline math ($...$) for math within prose.
- Keep the original language of the prose (do not translate).
- For diagrams or drawings, write a one-line description in square brackets
  inside \\textit{...} at the corresponding position instead of trying to
  reproduce them.
- Transcribe what is written; do not add explanations or corrections that
  are not on the page.
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        load_dotenv(dotenv_path=".env")
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def transcribe_to_latex(png_bytes: bytes, model: str = "gemini-3.6-flash") -> str:
    response = _get_client().models.generate_content(
        model=model,
        contents=[
            types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
            _PROMPT,
        ],
        config=types.GenerateContentConfig(max_output_tokens=16384),
    )
    return response.text
