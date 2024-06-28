import pytest
from scicat_metadata import load_metadata_extractors


@pytest.mark.parametrize(
    ("extractor_name", "expected_result"), [("max", 5), ("min", 1), ("mean", 3)]
)
def test_metadata_extractor(extractor_name: str, expected_result: int):
    """Test if the metadata extractor can be loaded."""
    test_data = [1, 2, 3, 4, 5]
    assert load_metadata_extractors(extractor_name)(test_data) == expected_result
