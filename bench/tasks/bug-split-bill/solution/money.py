"""Money helpers. Amounts are integer cents."""


def split(total_cents, people):
    if people < 1 or total_cents < 0:
        raise ValueError("invalid split")
    base, extra = divmod(total_cents, people)
    return [base + 1 if i < extra else base for i in range(people)]
