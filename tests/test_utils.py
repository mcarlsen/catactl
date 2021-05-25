import pytest
import os
from pathlib import Path
from cddalib import chunked, chdir

a = list(range(100))


def test_chunks_of_equal_sizes():
    chunks = list(chunked(a, 50))
    assert chunks == [
        list(range(0, 50)),
        list(range(50, 100)),
    ]


def test_one_left_over_in_last_chunk():
    chunks = list(chunked(a, 33))
    assert chunks == [
        list(range(0, 33)),
        list(range(33, 66)),
        list(range(66, 99)),
        [99],
    ]


def test_empty_input_means_zero_chunks_in_output():
    assert list(chunked([], 99)) == []


def test_chdir_enters_and_exits_folder(tmpdir):
    cwd = Path(os.getcwd())
    tmp = Path(tmpdir)
    with chdir(tmp):
        assert os.getcwd() == str(tmp)
    assert os.getcwd() == str(cwd)


def test_chdir_exits_folder_on_exception(tmpdir):
    cwd = Path(os.getcwd())
    tmp = Path(tmpdir)

    with pytest.raises(Exception):
        try:
            with chdir(tmp):
                raise Exception()
        finally:
            assert os.getcwd() == str(cwd)
