def _money(cents: int) -> str:
    return "%.2f" % (cents / 100)


def monthly_report(rows: list) -> str:
    total = sum(r["amount_cents"] for r in rows)
    lines = ["%s: %s" % (r["day"], _money(r["amount_cents"])) for r in rows]
    lines.append("total: %s" % _money(total))
    return "\n".join(lines)
