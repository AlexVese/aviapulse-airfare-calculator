import math
from decimal import Decimal, InvalidOperation, localcontext
from forecast.models import LEVELS

def validate_price(value):
    try:
        price = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Цена должна быть конечным неотрицательным числом.") from None
    if not price.is_finite() or price < 0:
        raise ValueError("Цена должна быть конечным неотрицательным числом.")
    if price.is_zero():
        return Decimal(0)
    try:
        represented = float(price)
    except (OverflowError, ValueError):
        represented = math.inf
    if not math.isfinite(represented) or represented == 0:
        raise ValueError("Число слишком велико или мало для отображения на графике.")
    sign, digits, exponent = price.as_tuple()
    trimmed = list(digits)
    while len(trimmed) > 1 and trimmed[-1] == 0:
        trimmed.pop()
        exponent += 1
    return Decimal((sign, tuple(trimmed), exponent))

def calculate_forecast(*, base_demands, price, parameters, seats):
    price = validate_price(price)
    if seats < 0 or isinstance(seats, bool):
        raise ValueError("Некорректная вместимость.")
    if set(base_demands) != set(LEVELS):
        raise ValueError("Прогноз должен содержать все девять квантилей.")
    with localcontext() as context:
        values = [price, parameters.base_price, parameters.price_sensitivity, *base_demands.values()]
        span = max(value.adjusted() for value in values) - min(value.as_tuple().exponent for value in values) + 1
        context.prec = max(64, 2 * span + 16, len(price.as_tuple().digits) + 32)
        shift = parameters.price_sensitivity * (price - parameters.base_price)
        quantiles = [{"level": str(q), "demand": str(base_demands[q] - shift)} for q in LEVELS]
        nonnegative_quantiles = [{"level": point["level"], "demand": str(max(Decimal(0), Decimal(point["demand"])))} for point in quantiles]
        median = Decimal(quantiles[4]["demand"])
        sales = min(Decimal(seats), max(Decimal(0), median))
        free_seats = Decimal(seats) - sales
        load_factor = sales / Decimal(seats) if seats else Decimal(0)
        interpretation = "zero_sales" if sales == 0 else "above_capacity" if median > seats else "below_capacity" if median < seats else "at_capacity"
        return {"price": str(price), "base_price": str(parameters.base_price), "seats": seats,
                "median_demand": str(median), "sales": str(sales), "free_seats": str(free_seats),
                "load_factor": str(load_factor), "quantiles": quantiles,
                "nonnegative_median_demand": nonnegative_quantiles[4]["demand"],
                "nonnegative_quantiles": nonnegative_quantiles,
                "has_negative_quantiles": any(Decimal(point["demand"]) < 0 for point in quantiles),
                "negative_demand": median < 0, "interpretation": interpretation}
