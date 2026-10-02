"""Command-line entry point: `troupe config <show|set|history> [--theatre DIR] …`."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from troupe import commands
from troupe.errors import TroupeError, UsageError
from troupe.paths import parse_path
from troupe.values import parse_value


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{self.prog}: {message}")


def _parser() -> argparse.ArgumentParser:
    theatre = _Parser(add_help=False)
    theatre.add_argument("--theatre", default=argparse.SUPPRESS, help="theatre directory (default: current)")

    parser = _Parser(prog="troupe", parents=[theatre])
    groups = parser.add_subparsers(dest="group", required=True, parser_class=_Parser)
    config = groups.add_parser("config", parents=[theatre], help="read and change the configuration")
    sub = config.add_subparsers(dest="command", required=True, parser_class=_Parser)

    show = sub.add_parser("show", parents=[theatre], help="print a setting's value")
    show.add_argument("path")
    set_ = sub.add_parser("set", parents=[theatre], help="change a setting and write it back")
    set_.add_argument("path")
    set_.add_argument("value")
    history = sub.add_parser("history", parents=[theatre], help="list configuration changes as JSON Lines")
    history.add_argument("path", nargs="?")
    return parser


def run(argv: Sequence[str]) -> str:
    """Run a command and return what it prints; raises TroupeError on failure."""
    args = _parser().parse_args(argv)
    theatre = Path(getattr(args, "theatre", "."))
    if args.command == "show":
        return commands.show(theatre, parse_path(args.path))
    if args.command == "set":
        path = parse_path(args.path)
        commands.set_value(theatre, path, parse_value(args.value))
        return ""
    prefix = parse_path(args.path) if args.path is not None else None
    return commands.history(theatre, prefix)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        output = run(sys.argv[1:] if argv is None else argv)
    except TroupeError as e:
        print(f"troupe: {e}", file=sys.stderr)
        return e.exit_code
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
