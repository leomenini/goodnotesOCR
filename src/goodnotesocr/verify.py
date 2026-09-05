"""Mechanical verification: LaTeX that does not compile is a failed output."""
from __future__ import annotations

import re
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
\usepackage{amsmath,amssymb,amsthm,mathtools}
\usepackage{graphicx}
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


# --- per-unit repair ----------------------------------------------------------
#
# The lite model's one recurring defect is bare math outside math mode: a
# paragraph like `\vec{a} = \vec{a}' + \vec{a}_c` with no $ or \[ around it.
# That is mechanical to detect and fix, so it is fixed mechanically; anything
# else that still fails is kept verbatim so the content survives for a
# manual pass and the failure stays visible in the output.

_MATH_CMD_RE = re.compile(
    r"\\(?:vec|frac|hat|widehat|dot|ddot|sqrt|wedge|land|times|cdot|boxed|underbrace|overbrace"
    r"|left|right|partial|int|oint|iint|iiint|sum|prod|infty|neq|leq|geq|perp|parallel|to"
    r"|rightarrow|Rightarrow|longrightarrow|implies|iff|mathbf|operatorname|sin|cos|tan"
    r"|alpha|beta|gamma|delta|theta|omega|varphi|phi|rho|sigma|tau|lambda|mu|nu|pi|varepsilon|epsilon)\b"
    r"|[_^]\{"
)
_HAS_MATH_MODE_RE = re.compile(r"\$|\\\[|\\\(|\\begin\{(?:align|equation|gather|multline|eqnarray|array|cases)")


_ENV_DELIM_RE = re.compile(r"\\begin\{|\\end\{|\\\[|\\\]|\\\(|\\\)")


def repair_math_mode(body: str) -> str:
    """Wrap lines that hold math commands but sit outside any math mode in
    \\[ ... \\]. Works line by line so a single bare `\\boxed{...}` next to
    well-formed display math still gets fixed; lines inside environments or
    display math are left alone by tracking open delimiters."""
    out = []
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        opens = len(re.findall(r"\\begin\{|\\\[|\\\(", stripped))
        closes = len(re.findall(r"\\end\{|\\\]|\\\)", stripped))
        if (
            depth == 0
            and stripped
            and not _ENV_DELIM_RE.search(stripped)
            and "$" not in stripped
            and _MATH_CMD_RE.search(stripped)
            and not stripped.startswith(("\\section", "\\underline{", "\\textbf{", "\\noindent", "\\item"))
        ):
            line = "\\[ " + stripped + " \\]"
        depth = max(0, depth + opens - closes)
        out.append(line)
    return "\n".join(out)


def verbatim_fallback(body: str, label: str) -> str:
    return f"\\textbf{{[{label}: no compila, se deja tal cual]}}\n\\begin{{verbatim}}\n{body}\n\\end{{verbatim}}"


def ensure_compiles(body: str, label: str) -> tuple[str, str]:
    """Return (body that compiles, status) with status in ok | repaired | verbatim."""
    if compile_latex(body).success:
        return body, "ok"
    repaired = repair_math_mode(body)
    if repaired != body and compile_latex(repaired).success:
        return repaired, "repaired"
    return verbatim_fallback(body, label), "verbatim"


def compile_latex(body: str, workdir: Path | None = None, timeout: int = 120) -> CompileResult:
    """Compile `body` as main.tex. With `workdir`, compile there so relative
    \\includegraphics paths resolve; otherwise use a throwaway directory."""
    if workdir is None:
        with tempfile.TemporaryDirectory() as tmp:
            return _compile_in(Path(tmp), body, timeout)
    workdir.mkdir(parents=True, exist_ok=True)
    return _compile_in(workdir, body, timeout)


def _compile_in(workdir: Path, body: str, timeout: int) -> CompileResult:
    tex = wrap_document(body)
    tex_path = workdir / "main.tex"
    tex_path.write_text(tex, encoding="utf-8")
    proc = subprocess.run(
        ["tectonic", "--keep-logs", "main.tex"],
        cwd=workdir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    log = proc.stdout + proc.stderr
    pdf_path = workdir / "main.pdf"
    if proc.returncode == 0 and pdf_path.exists():
        return CompileResult(True, log, tex, pdf_path.read_bytes())
    return CompileResult(False, log, tex, None)
