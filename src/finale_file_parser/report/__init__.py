"""Inspecting one document: what the parser saw, and how far it got."""

from __future__ import annotations

from finale_file_parser.report.ladder import Stage
from finale_file_parser.report.model import Inspection, inspect_document

__all__ = ["Inspection", "Stage", "inspect_document"]
