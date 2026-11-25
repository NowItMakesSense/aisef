import pytest

from app.pagination import page


def test_second_page_has_the_next_items():
    assert page(list(range(50)), 2, size=20) == list(range(20, 40))


def test_last_page_is_partial():
    assert page(list(range(50)), 3, size=20) == list(range(40, 50))


def test_page_zero_is_rejected():
    with pytest.raises(ValueError):
        page([1, 2, 3], 0)
