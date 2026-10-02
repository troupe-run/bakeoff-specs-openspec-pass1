"""Layout of block scalars (`|` and `>`) in source text: header, content lines and the value they spell.

The parser's marks for a block scalar include trailing blank lines whatever the chomping, so the extent
that belongs to the value is worked out here from the text.
"""

from dataclasses import dataclass

from troupe.source import SourceFile


@dataclass
class BlockLayout:
    indicator: str  # "|" or ">"
    chomp: str  # "", "-" or "+"
    indent_digit: int | None
    start: int  # offset of the indicator
    header_end: int  # offset just past the indicator characters
    body_start: int  # start of the first line after the header
    content_indent: int
    body: list[str]  # lines (indentation removed) from body_start through the last non-blank line
    trailing_blanks: int  # blank lines after the last non-blank line, before the scalar ends
    final_break: bool  # whether the last body line is followed by a line break
    content_end: int  # end of the last non-blank line (excluding its line break), or header_end
    region_end: int  # end of everything the value owns (line breaks and, for keep, trailing blanks)

    @property
    def more_indented(self) -> bool:
        return any(line[:1] in (" ", "\t") for line in self.body)

    def value(self) -> str:
        core = "\n".join(self.body) if self.indicator == "|" else fold(self.body)
        if not self.body:
            return "\n" * self.trailing_blanks if self.chomp == "+" else ""
        if self.chomp == "-" or not self.final_break:
            return core
        if self.chomp == "+":
            return core + "\n" + "\n" * self.trailing_blanks
        return core + "\n"


def fold(lines: list[str]) -> str:
    """Folded-scalar content for lines without more-indented ones: single breaks become spaces."""
    out = ""
    started = False
    empties = 0
    for line in lines:
        if line == "":
            empties += 1
            continue
        if not started:
            out += "\n" * empties + line
            started = True
        else:
            out += (" " if empties == 0 else "\n" * empties) + line
        empties = 0
    return out


def parse_block(src: SourceFile, start: int, owner_col: int) -> BlockLayout:
    text = src.text
    indicator = text[start]
    i = start + 1
    chomp = ""
    digit: int | None = None
    while i < len(text) and i < start + 3 and text[i] in "+-123456789":
        if text[i] in "+-":
            chomp = text[i]
        else:
            digit = int(text[i])
        i += 1
    header_end = i
    body_start = src.next_line(start)

    lines: list[tuple[int, int]] = []  # (start, end-excluding-break) of each following line
    pos = body_start
    while pos < len(text):
        end = src.line_end(pos)
        lines.append((pos, end))
        pos = src.next_line(pos)

    def is_blank(s: int, e: int) -> bool:
        return text[s:e].strip(" ") == ""

    if digit is not None:
        indent = max(owner_col, 0) + digit
    else:
        indent = owner_col + 1
        for s, e in lines:
            if not is_blank(s, e):
                line = text[s:e]
                indent = max(len(line) - len(line.lstrip(" ")), owner_col + 1)
                break

    body: list[str] = []
    trailing = 0
    content_end = header_end
    last_break = False
    owned_end = body_start
    for s, e in lines:
        line = text[s:e]
        if is_blank(s, e) and len(line) <= indent:
            trailing += 1
            continue
        if len(line) - len(line.lstrip(" ")) < indent:
            break
        body.extend([""] * trailing)
        trailing = 0
        body.append(line[indent:])
        content_end = e
        owned_end = src.next_line(s)
        last_break = owned_end > e
    region_end = owned_end
    if chomp == "+":
        # Trailing blank lines are part of a kept value.
        region_end = owned_end
        for _ in range(trailing):
            region_end = src.next_line(region_end)
    return BlockLayout(
        indicator=indicator,
        chomp=chomp,
        indent_digit=digit,
        start=start,
        header_end=header_end,
        body_start=body_start,
        content_indent=indent,
        body=body,
        trailing_blanks=trailing,
        final_break=last_break,
        content_end=content_end,
        region_end=region_end,
    )
