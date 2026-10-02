"""Rewriting a folded (`>`) block scalar: unchanged paragraphs keep their bytes, changed ones re-wrap.

A folded value's lines (split on newline) are its paragraphs. Old and new paragraphs are aligned with
difflib; paragraphs in a replaced run are paired by position and each re-wraps at the width of its old
counterpart's longest line. Paragraphs with no counterpart wrap at the old value's longest line.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from troupe.blockscalar import BlockLayout

DEFAULT_WIDTH = 80
_BREAK = re.compile(r"(?<=[^ ]) (?=[^ ])")


class MoreIndented(Exception):
    """The new value would need a more-indented line, which a rewrite of a folded scalar refuses."""


@dataclass
class Paragraph:
    text: str
    source: list[str] | None  # the old body lines (indentation removed) spelling it, if it came from the file


def paragraphs(body: list[str]) -> list[Paragraph]:
    """The folded value's lines, each with the source lines that spell it."""
    out: list[Paragraph] = []
    group: list[str] = []
    empties = 0
    started = False
    for line in [*body, None]:
        if line is not None and line != "":
            group.append(line)
            continue
        if group:
            if started:
                out.extend(Paragraph("", None) for _ in range(max(empties - 1, 0)))
            else:
                out.extend(Paragraph("", None) for _ in range(empties))
            out.append(Paragraph(" ".join(group), group))
            started = True
            group = []
            empties = 0
        if line == "":
            empties += 1
    return out


def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap; words split at single spaces between non-space characters."""
    lines: list[str] = []
    current: str | None = None
    for word in _BREAK.split(text):
        if current is None:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    lines.append(current or "")
    return lines


def refold(layout: BlockLayout, new_core: str) -> list[str]:
    """Body lines (indentation removed) for the folded value `new_core` (trailing newlines excluded)."""
    new_texts = new_core.split("\n") if new_core else []
    if any(t[:1] in (" ", "\t") for t in new_texts):
        raise MoreIndented
    old = paragraphs(layout.body)
    widths = [len(line) for p in old if p.source for line in p.source]
    overall = max(widths, default=DEFAULT_WIDTH)

    def width_of(p: Paragraph | None) -> int:
        if p is None or not p.source:
            return overall
        return max(len(line) for line in p.source)

    result: list[Paragraph] = []
    matcher = SequenceMatcher(None, [p.text for p in old], new_texts, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            result.extend(old[i1:i2])
            continue
        for k, text in enumerate(new_texts[j1:j2]):
            counterpart = old[i1 + k] if op == "replace" and i1 + k < i2 else None
            result.append(Paragraph(text, wrap(text, width_of(counterpart)) if text else None))

    lines: list[str] = []
    for index, p in enumerate(result):
        if index > 0:
            lines.append("")
        if p.text:
            assert p.source is not None
            lines.extend(p.source)
    return lines
