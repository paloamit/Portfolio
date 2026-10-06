#!/usr/bin/env python3
"""Lightweight ATS compliance checker for resume.tex / resume.pdf."""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import pypdf
except ImportError:
    pypdf = None

ROOT = Path(__file__).resolve().parent
TEX = ROOT / "resume.tex"
PDF = ROOT / "resume.pdf"

STANDARD_SECTIONS = {
    "professional summary",
    "summary",
    "profile",
    "professional experience",
    "work experience",
    "experience",
    "employment",
    "technical skills",
    "skills",
    "core competencies",
    "education",
    "academic background",
}

ACTION_VERBS = {
    "led", "built", "developed", "designed", "implemented", "architected",
    "delivered", "improved", "reduced", "increased", "created", "enhanced",
    "drove", "shipped", "integrated", "partnered", "recognized",
}

METRIC_PATTERN = re.compile(
    r"\d+\s*%|\d+\s*(s|ms|sec|seconds|minutes|hours|days|weeks|months|years|x|\+)|"
    r"\d+\.\d+\s*to\s*\d+\.\d+|\d+\s*to\s*\d+|\d+\+|\$\d+",
    re.I,
)


def score_tex(text: str) -> tuple[int, list[str], list[str]]:
    checks: list[tuple[str, int, bool]] = []
    notes: list[str] = []
    issues: list[str] = []

    lower = text.lower()

    # Structure
    checks.append(("Standard section headings present", 12, bool(re.search(r"\\section\{Professional Summary\}", text))))
    checks.append(("Experience section present", 12, bool(re.search(r"\\section\{Professional Experience\}", text))))
    checks.append(("Skills section present", 10, bool(re.search(r"\\section\{Technical Skills\}", text))))
    checks.append(("Education section present", 8, bool(re.search(r"\\section\{Education\}", text))))

    # ATS-unfriendly LaTeX constructs
    bad = [
        ("tabular", "tables can break ATS parsing"),
        ("minipage", "multi-column minipage layouts"),
        ("multicol", "multi-column layout"),
        ("tikzpicture", "graphics/diagrams"),
        ("includegraphics", "images"),
        ("fancyhdr", "headers/footers with critical info"),
    ]
    bad_hits = [name for name, _ in bad if name in lower]
    checks.append(("No ATS-unfriendly layout primitives", 10, len(bad_hits) == 0))
    if bad_hits:
        issues.append(f"Avoid: {', '.join(bad_hits)}")

    checks.append(("Single-column article class", 8, "\\documentclass" in text and "article" in text))
    checks.append(("Contact email present", 6, "palo.amit@gmail.com" in lower))
    checks.append(("Phone number present", 4, re.search(r"\+?\d{2}[-\s]?\d{6,}", text) is not None))
    checks.append(("LinkedIn URL present", 4, "linkedin.com" in lower))

    # Content quality
    bullets = re.findall(r"\\resumeItem\{([^}]+)\}", text, re.S)
    action_count = sum(
        1 for b in bullets if any(b.strip().lower().startswith(v) for v in ACTION_VERBS)
    )
    checks.append(("Action-verb bullet openings", 8, action_count >= max(3, len(bullets) // 2)))
    notes.append(f"Action-verb bullets: {action_count}/{len(bullets)}")

    metric_bullets = sum(1 for b in bullets if METRIC_PATTERN.search(b))
    checks.append(("Quantified impact in bullets", 10, metric_bullets >= 3))
    notes.append(f"Metric bullets: {metric_bullets}/{len(bullets)}")

    keyword_groups = [
        ("swift", "objective-c", "ios"),
        ("node.js", "restful", "api"),
        ("react native", "mvvm", "solid"),
        ("ci/cd", "agile", "scrum"),
        ("firebase", "sentry", "amplitude"),
    ]
    kw_score = sum(1 for group in keyword_groups if any(k in lower for k in group))
    checks.append(("Core keyword coverage", 8, kw_score >= 4))
    notes.append(f"Keyword groups matched: {kw_score}/{len(keyword_groups)}")

    checks.append(("No duplicate Personal Links section", 4, "personal links" not in lower))
    checks.append(("Concise summary (<= 120 words)", 6, len(re.findall(r"\w+", re.search(r"Professional Summary.*?\\section", text, re.S).group())) <= 120 if re.search(r"Professional Summary.*?\\section", text, re.S) else False))

    total = sum(w for _, w, _ in checks)
    earned = sum(w for _, w, ok in checks if ok)
    pct = round(100 * earned / total)
    detail = [f"{'PASS' if ok else 'FAIL'} ({w}): {label}" for label, w, ok in checks]
    return pct, detail, issues + notes


def score_pdf_text(text: str) -> tuple[int, list[str]]:
    lower = text.lower()
    checks: list[tuple[str, int, bool]] = []

    sections_found = sum(1 for s in STANDARD_SECTIONS if s in lower)
    checks.append(("Extractable standard sections", 20, sections_found >= 3))
    checks.append(("Email parseable in PDF text", 10, "palo.amit@gmail.com" in lower))
    checks.append(("Experience content extractable", 15, "jio platforms" in lower))
    checks.append(("Skills content extractable", 10, "swift" in lower and "node.js" in lower))
    checks.append(("Metrics present in PDF text", 15, len(METRIC_PATTERN.findall(text)) >= 5))
    checks.append(("No garbled-only extraction", 10, len(text.strip()) > 1500))

    total = sum(w for _, w, _ in checks)
    earned = sum(w for _, w, ok in checks if ok)
    pct = round(100 * earned / total)
    detail = [f"{'PASS' if ok else 'FAIL'} ({w}): {label}" for label, w, ok in checks]
    return pct, detail


def main() -> int:
    if not TEX.exists():
        print("resume.tex not found")
        return 1

    tex_text = TEX.read_text(encoding="utf-8")
    tex_pct, tex_detail, notes = score_tex(tex_text)

    print("=== ATS Check: resume.tex ===")
    print(f"Score: {tex_pct}%")
    for line in tex_detail:
        print(f"  {line}")
    for note in notes:
        print(f"  note: {note}")

    if PDF.exists() and pypdf:
        reader = pypdf.PdfReader(str(PDF))
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        pdf_pct, pdf_detail = score_pdf_text(pdf_text)
        print("\n=== ATS Check: resume.pdf (text extraction) ===")
        print(f"Score: {pdf_pct}%")
        for line in pdf_detail:
            print(f"  {line}")
        if PDF.stat().st_mtime < TEX.stat().st_mtime:
            print("\nNote: resume.pdf is older than resume.tex — recompile to refresh PDF.")
    elif not PDF.exists():
        print("\nresume.pdf not found — compile resume.tex with pdflatex.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
