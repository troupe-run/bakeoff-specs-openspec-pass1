"""Configuration source files held as text, with line and column helpers.

Files are read with `newline=''` so that offsets index the exact characters on disk (CRLF stays two
characters, which is also how the YAML parser counts them). Columns count Unicode code points.
"""

from dataclasses import dataclass
from pathlib import Path

from troupe.errors import LoadError


@dataclass(eq=False)
class SourceFile:
    path: Path
    text: str

    @property
    def newline(self) -> str:
        """The line ending used for lines we insert: that of the file's first line break."""
        i = self.text.find("\n")
        return "\r\n" if i > 0 and self.text[i - 1] == "\r" else "\n"

    def line_start(self, pos: int) -> int:
        return self.text.rfind("\n", 0, pos) + 1

    def line_end(self, pos: int) -> int:
        """Offset of the line break ending the line containing `pos` (or end of text)."""
        i = self.text.find("\n", pos)
        if i < 0:
            return len(self.text)
        return i - 1 if i > 0 and self.text[i - 1] == "\r" else i

    def next_line(self, pos: int) -> int:
        """Offset of the start of the line after the one containing `pos` (or end of text)."""
        i = self.text.find("\n", pos)
        return len(self.text) if i < 0 else i + 1

    def column(self, pos: int) -> int:
        return pos - self.line_start(pos)

    def line_text(self, pos: int) -> str:
        return self.text[self.line_start(pos) : self.line_end(pos)]


def read_source(path: Path) -> SourceFile:
    try:
        with path.open(encoding="utf-8", newline="") as f:
            return SourceFile(path, f.read())
    except FileNotFoundError:
        raise LoadError(f"{path}: file not found") from None
    except UnicodeDecodeError as e:
        raise LoadError(f"{path}: not valid UTF-8 ({e.reason})") from None
    except OSError as e:
        raise LoadError(f"{path}: cannot read ({e.strerror})") from None
