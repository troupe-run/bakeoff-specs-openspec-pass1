"""Errors and the exit code each one maps to (the one place exit codes are decided)."""


class TroupeError(Exception):
    """Base class: a failure reported to the user as a message on stderr and an exit code."""

    exit_code = 1


class UsageError(TroupeError):
    """The command line is malformed (bad path syntax, unparseable VALUE, …)."""

    exit_code = 2


class WriteRefused(TroupeError):
    """`set` will not write this change; no file has been changed."""

    exit_code = 3


class LoadError(TroupeError):
    """The configuration cannot be loaded (missing/duplicate config file, bad YAML, bad include)."""

    exit_code = 4


class PathError(TroupeError):
    """The path does not exist, or is the wrong kind of node for the command."""

    exit_code = 5
