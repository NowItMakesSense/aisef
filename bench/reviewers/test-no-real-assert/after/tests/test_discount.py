from app.pricing import discount


def test_discount_for_gold_customers():
    result = discount(total_cents=10000, tier="gold")
    assert result is not None
