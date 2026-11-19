"""Shipping cost in cents."""


def shipping_cost(region, weight_kg, express=False):
    if weight_kg <= 0:
        raise ValueError("weight must be positive")
    if region == "local":
        if weight_kg <= 1:
            cost = 500
        elif weight_kg <= 5:
            cost = 900
        else:
            cost = 900 + int((weight_kg - 5) * 150)
        if express:
            cost = cost * 2
    elif region == "national":
        if weight_kg <= 1:
            cost = 800
        elif weight_kg <= 5:
            cost = 1400
        else:
            cost = 1400 + int((weight_kg - 5) * 250)
        if express:
            cost = cost * 2
    elif region == "international":
        if express:
            raise ValueError("no express for international")
        if weight_kg <= 1:
            cost = 2500
        elif weight_kg <= 5:
            cost = 4000
        else:
            cost = 4000 + int((weight_kg - 5) * 700)
    else:
        raise KeyError(region)
    return cost
