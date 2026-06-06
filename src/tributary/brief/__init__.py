"""
Package: tributary.brief
Layer: brief
Purpose: Brief assembly — combines engine-filled templates with AI narrative to produce
    per-jurisdiction filing briefs and the cross-border conflict report.
Public surface: BriefAssembler, render_brief_markdown, render_report_markdown
"""
from __future__ import annotations

from .assembler import BriefAssembler
from .renderer import render_brief_markdown, render_report_markdown

__all__ = [
    "BriefAssembler",
    "render_brief_markdown",
    "render_report_markdown",
]
