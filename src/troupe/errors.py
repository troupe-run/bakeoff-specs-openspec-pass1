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


class ThroughAlias(WriteRefused):
    """`set` would write through an alias (`*name`), which would change the anchor and every other alias.

    `alias_path` is where the alias is written. `set --expand-alias` replaces it with a copy and retries.
    """

    def __init__(
        self,
        path: str,
        alias_at: tuple[str, ...],
        name: str,
        anchor_path: str | None,
        at_anchor: str | None,
        *,
        in_flow: bool,
    ) -> None:
        self.alias_at = alias_at  # the path of the alias, for `set --expand-alias`
        alias_path = ".".join(alias_at)
        self.name = name
        self.in_flow = in_flow
        where = f"&{name} at {anchor_path}" if anchor_path is not None else f"&{name}"
        if in_flow:
            hint = f"--expand-alias cannot expand *{name} at {alias_path}: it is inside a flow collection"
        elif at_anchor is not None:
            hint = (
                f"Set {at_anchor} to change it everywhere, or use --expand-alias to give {alias_path} a copy"
            )
        else:
            hint = f"Use --expand-alias to give {alias_path} its own copy"
        super().__init__(
            f"{path}: {alias_path} is the alias *{name} of {where}, so this would change all its uses. {hint}"
        )


class MergeKeyWrite(WriteRefused):
    """`set` would have to add, change or delete a merge key (`<<`) or a value one supplies."""

    def __init__(self, path: str, holder_path: str, what: str) -> None:
        holder = f"{holder_path}.<<" if holder_path else "<<"
        super().__init__(
            f"{path}: {what} the merge key {holder}; troupe never writes merge keys (--expand-alias cannot "
            "help), so edit the file by hand"
        )
