from unittest import mock

from app import tax


def test_tax_for_sp():
    with mock.patch.object(tax, "compute_tax", return_value=1800):
        assert tax.compute_tax(10000, state="SP") == 1800
