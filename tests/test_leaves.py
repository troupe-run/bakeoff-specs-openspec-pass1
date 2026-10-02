from troupe.leaves import leaves
from troupe.schema import Data


def test_leaves_are_dotted_paths_in_document_order() -> None:
    data: Data = {"b": [1, {"c": None}], "a": {"x": "s"}, "e": {}, "f": []}
    assert list(leaves(data).items()) == [("b.0", 1), ("b.1.c", None), ("a.x", "s")]


def test_empty_collections_have_no_leaves() -> None:
    assert leaves({"a": {}, "b": []}) == {}
