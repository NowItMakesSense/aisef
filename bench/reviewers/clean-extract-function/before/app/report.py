def monthly_report(rows: list) -> str:
    total = 0
    for r in rows:
        total += r["amount_cents"]
    lines = ["%s: %.2f" % (r["day"], r["amount_cents"] / 100) for r in rows]
    lines.append("total: %.2f" % (total / 100))
    return "\n".join(lines)
