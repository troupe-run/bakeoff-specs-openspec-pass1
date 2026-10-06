"""Command-line entry point: `troupe config <get|show|set|history|watch> [--theatre DIR] …`."""

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from troupe import commands
from troupe.errors import TroupeError, UsageError
from troupe.lineage import actor_from_env
from troupe.paths import parse_path
from troupe.values import parse_value


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(f"{self.prog}: {message}")


def _parser() -> argparse.ArgumentParser:
    theatre = _Parser(add_help=False)
    theatre.add_argument(
        "--theatre",
        default=argparse.SUPPRESS,
        help="theatre directory (default: $TROUPE_THEATRE, else current)",
    )

    parser = _Parser(prog="troupe", parents=[theatre])
    groups = parser.add_subparsers(dest="group", required=True, parser_class=_Parser)
    config = groups.add_parser("config", parents=[theatre], help="read and change the configuration")
    sub = config.add_subparsers(dest="command", required=True, parser_class=_Parser)

    get = sub.add_parser("get", parents=[theatre], help="print a scalar setting's value")
    get.add_argument("path")
    show = sub.add_parser("show", parents=[theatre], help="print a value or a section as YAML")
    show.add_argument("path", nargs="?")
    show.add_argument("--sources", action="store_true", help="say which file each value comes from")
    set_ = sub.add_parser("set", parents=[theatre], help="change a setting and write it back")
    set_.add_argument("path")
    set_.add_argument("value")
    set_.add_argument("--reason", metavar="TEXT", help="why the change is made (recorded in the history)")
    set_.add_argument(
        "--in-include",
        action="store_true",
        help="write new keys into the included file itself, not as overrides in the including file",
    )
    set_.add_argument(
        "--expand-alias",
        action="store_true",
        help="replace an alias on the way with a copy of its anchored value, then set the value in the copy",
    )
    history = sub.add_parser("history", parents=[theatre], help="list configuration changes as JSON Lines")
    history.add_argument("path", nargs="?")
    sub.add_parser("watch", parents=[theatre], help="record hand edits to the files as they happen")
    return parser


def run(argv: Sequence[str]) -> str:
    """Run a command and return what it prints; raises TroupeError on failure."""
    args = _parser().parse_args(argv)
    # Checked for every command, before anything is loaded, so a bad TROUPE_ACTOR records nothing.
    actor = actor_from_env(os.environ)
    given: str | None = getattr(args, "theatre", None) or os.environ.get("TROUPE_THEATRE") or None
    theatre = Path(given or ".")
    if args.command == "get":
        return commands.get(theatre, parse_path(args.path))
    if args.command == "show":
        path = parse_path(args.path) if args.path is not None else None
        return commands.show(theatre, path, args.sources)
    if args.command == "set":
        path = parse_path(args.path)
        commands.set_value(
            theatre,
            path,
            parse_value(args.value),
            actor,
            args.reason,
            in_include=args.in_include,
            expand_alias=args.expand_alias,
        )
        return ""
    if args.command == "watch":
        # Shown as given (not resolved, which would turn macOS /var/… into /private/var/…).
        commands.watch(theatre, given or os.getcwd(), sys.stdout)
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
