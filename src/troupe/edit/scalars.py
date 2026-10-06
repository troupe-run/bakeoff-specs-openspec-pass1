"""Writing scalars in flow styles (plain, single-quoted, double-quoted) and choosing among them."""

from troupe.schema import Scalar, plain_text, resolve_plain

QUOTE_STYLES = (None, "'", '"')
_INDICATORS = "!&*|>'\"%@`#,[]{}"
_FLOW_INDICATORS = ",[]{}"
_ESCAPES = {
    "\0": "\\0",
    "\a": "\\a",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\v": "\\v",
    "\f": "\\f",
    "\r": "\\r",
    "\x1b": "\\e",
    "\x85": "\\N",
    "\\": "\\\\",
    '"': '\\"',
}


def is_control(ch: str) -> bool:
    """C0, DEL and C1 control characters: the only characters a double-quoted scalar escapes."""
    code = ord(ch)
    return code < 0x20 or 0x7F <= code <= 0x9F


def is_printable(ch: str) -> bool:
    """YAML's c-printable, minus the byte-order mark."""
    code = ord(ch)
    if ch in "\t\n\r":
        return True
    if ch == "\ufeff":
        return False
    return (
        0x20 <= code <= 0x7E
        or code == 0x85
        or 0xA0 <= code <= 0xD7FF
        or 0xE000 <= code <= 0xFFFD
        or 0x10000 <= code <= 0x10FFFF
    )


def can_plain(text: str, *, flow: bool) -> bool:
    if text == "" or text != text.strip(" \t"):
        return False
    if any(ch in "\t\n\r" or not is_printable(ch) for ch in text):
        return False
    if text[0] in _INDICATORS:
        return False
    if text[0] in "-?:" and (len(text) == 1 or text[1] == " " or (flow and text[1] in _FLOW_INDICATORS)):
        return False
    if ": " in text or text.endswith(":") or " #" in text:
        return False
    if flow and any(ch in text for ch in _FLOW_INDICATORS + ":"):
        return False
    if text.startswith(("---", "...")):
        return False
    resolved = resolve_plain(text)
    return resolved == text and isinstance(resolved, str)


def can_single(text: str) -> bool:
    return all(is_printable(ch) and ch not in "\n\r" for ch in text)


def single(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def double(text: str) -> str:
    out = []
    for ch in text:
        if ch in _ESCAPES:
            out.append(_ESCAPES[ch])
        elif is_control(ch):
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _render(text: str, preferred: str | None, *, flow: bool) -> str:
    order = [preferred] if preferred in QUOTE_STYLES else []
    for style in [*order, None, "'", '"']:
        if style is None and can_plain(text, flow=flow):
            return text
        if style == "'" and can_single(text):
            return single(text)
        if style == '"':
            return double(text)
    raise AssertionError("double quotes can represent any string")


def render_scalar(value: Scalar, preferred: str | None, *, flow: bool) -> str:
    """A scalar in the preferred quoting style if it can hold the value, else plain, single, double."""
    if not isinstance(value, str):
        return plain_text(value)
    return _render(value, preferred, flow=flow)


def render_key(key: str, preferred: str | None, *, flow: bool) -> str:
    """A new mapping key; like a string value, it is quoted when plain would read back as another type.

    A `<<` key is quoted too: written plain, it would be a merge key (and troupe never writes those).
    """
    if key == "<<" and preferred is None:
        preferred = "'"
    return _render(key, preferred, flow=flow)
