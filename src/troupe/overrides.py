"""Mapping-form includes: the `$ref` syntax and how overrides merge with included content.

`coder: {$ref: file:agents/coder.yaml, temperature: 0.3}` is the included mapping deep-merged with the
overrides: mappings on both sides merge recursively, anything else in the override replaces. Included keys
keep their order, and keys only the overrides have follow, in their order.
"""

from troupe.tree import Entry, Include, MappingNode, ScalarNode, include_target

REF_KEY = "$ref"


def ref_entry(mapping: MappingNode) -> Entry | None:
    """The `$ref` entry that makes `mapping` an include, or None if `mapping` is an ordinary mapping."""
    entry = mapping.get(REF_KEY)
    if entry is not None and isinstance(entry.value, ScalarNode) and include_target(entry.value) is not None:
        return entry
    return None


def override_entries(mapping: MappingNode) -> list[Entry]:
    """The overrides of a mapping-form include: every entry but `$ref`."""
    ref = ref_entry(mapping)
    return [e for e in mapping.entries if e is not ref]


def is_bare(include: Include, value: object) -> bool:
    """Whether `value` is the include's own string and the include has no overrides, so it means the same."""
    no_overrides = include.overrides is None or not override_entries(include.overrides)
    return no_overrides and isinstance(value, str) and value == include.string.value


def merge(base: MappingNode, override: MappingNode, entries: list[Entry]) -> MappingNode:
    """`base` deep-merged with `entries`, the overriding entries of `override`. The inputs are not changed."""
    by_key = {e.key: e for e in entries}
    merged_entries: list[Entry] = []
    for entry in base.entries:
        over = by_key.pop(entry.key, None)
        if over is None:
            merged_entries.append(entry)
        elif isinstance(entry.value, MappingNode) and isinstance(over.value, MappingNode):
            value = merge(entry.value, over.value, over.value.entries)
            # The nearest include wins: an included override value, else an included base value.
            value.include = over.value.include or entry.value.include
            alias = entry.alias or over.alias  # a write below either side would go through it
            merged_entries.append(Entry(key=entry.key, key_node=entry.key_node, value=value, alias=alias))
        else:
            merged_entries.append(over)
    merged_entries.extend(by_key.values())
    return MappingNode(
        file=base.file,
        start=base.start,
        end=base.end,
        in_flow=base.in_flow,
        owner_col=base.owner_col,
        flow_style=base.flow_style,
        entries=merged_entries,
        layers=[*(base.layers or [base]), *(override.layers or [override])],
    )
