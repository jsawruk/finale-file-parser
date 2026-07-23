"""Decoding score.dat into EnigmaXML."""

from __future__ import annotations

from finale_file_parser.enigma.crypt import decrypt
from finale_file_parser.enigma.models import CorruptScoreError
from finale_file_parser.enigma.score import MAX_INFLATED, score_xml

__all__ = ["MAX_INFLATED", "CorruptScoreError", "decrypt", "score_xml"]
