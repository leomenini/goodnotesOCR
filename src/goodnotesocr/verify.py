"""Mechanical verification: LaTeX that does not compile is a failed output."""
from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# tectonic runs XeTeX: fontspec gives full Unicode text (¿, accents) without
# inputenc/fontenc, and es-noshorthands stops babel from turning a plain
# double quote into an active character (which mangled "Conductor" into
# Çonductor").
_PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage{fontspec}
\usepackage[spanish,es-noshorthands]{babel}
\usepackage{amsmath,amssymb,amsthm}
\usepackage{geometry}
\geometry{margin=2cm}
\setlength{\parindent}{0pt}
\setlength{\parskip}{6pt}
\begin{document}
"""

_POSTAMBLE = "\n\\end{document}\n"


@dataclass
class CompileResult:
    success: bool
    log: str
    tex: str
    pdf_bytes: bytes | None


def wrap_document(body: str) -> str:
    return _PREAMBLE + body + _POSTAMBLE


def compile_latex(body: str, timeout: int = 120) -> CompileResult:
    tex = wrap_document(body)
    with tempfile.TemporaryDirectory() as tmp:
        tex_path = Path(tmp) / "main.tex"
        tex_path.write_text(tex, encoding="utf-8")
        proc = subprocess.run(
            ["tectonic", "--keep-logs", str(tex_path)],
            cwd=tmp,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        log = proc.stdout + proc.stderr
        pdf_path = Path(tmp) / "main.pdf"
        if proc.returncode == 0 and pdf_path.exists():
            return CompileResult(True, log, tex, pdf_path.read_bytes())
        return CompileResult(False, log, tex, None)
