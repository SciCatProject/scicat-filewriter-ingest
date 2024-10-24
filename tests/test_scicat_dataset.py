# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2024 ScicatProject contributors (https://github.com/ScicatProject)
import pytest
from scicat_dataset import convert_to_type


def test_dtype_string_converter() -> None:
    assert convert_to_type("test", "string") == "test"
    assert convert_to_type(123, "string") == "123"
    assert convert_to_type(123.456, "string") == "123.456"


def test_dtype_string_array_converter() -> None:
    assert convert_to_type("'test'", "string[]") == ["t", "e", "s", "t"]
    assert convert_to_type("['test']", "string[]") == ["test"]
    assert convert_to_type("['test', 'test2']", "string[]") == ["test", "test2"]
    assert convert_to_type([1, 2, 3], "string[]") == ["1", "2", "3"]
    assert convert_to_type([1.1, 2.2, 3.3], "string[]") == ["1.1", "2.2", "3.3"]


def test_dtype_integer_converter() -> None:
    assert convert_to_type("123", "integer") == 123
    assert convert_to_type(123, "integer") == 123
    assert convert_to_type(123.456, "integer") == 123


def test_dtype_float_converter() -> None:
    assert convert_to_type("123.456", "float") == 123.456
    assert convert_to_type(123, "float") == 123.0
    assert convert_to_type(123.456, "float") == 123.456


def test_dtype_date_converter() -> None:
    import datetime

    test_datetime_isoformat = "1994-06-28T10:20:30+00:00"
    test_datetime = datetime.datetime.fromisoformat(test_datetime_isoformat)
    assert convert_to_type("1994-06-28T10:20:30Z", "date") == test_datetime_isoformat
    assert convert_to_type(test_datetime.timestamp(), "date") == test_datetime_isoformat
    assert convert_to_type(object(), "date") is None


def test_dtype_converter_invalid_dtype_raises() -> None:
    with pytest.raises(ValueError, match="Invalid dtype description."):
        convert_to_type("test", "invalid_type")
