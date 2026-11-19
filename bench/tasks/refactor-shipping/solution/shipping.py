"""Shipping cost in cents."""

# region: (up to 1 kg, up to 5 kg, per extra kg above 5, express allowed)
RATES = {"local": (500, 900, 150, True), "national": (800, 1400, 250, True), "international": (2500, 4000, 700, False)}


def shipping_cost(region, weight_kg, express=False):
    if weight_kg <= 0:
        raise ValueError("weight must be positive")
    small, medium, per_kg, express_ok = RATES[region]
    if express and not express_ok:
        raise ValueError("no express for %s" % region)
    cost = small if weight_kg <= 1 else medium if weight_kg <= 5 else medium + int((weight_kg - 5) * per_kg)
    return cost * 2 if express else cost
