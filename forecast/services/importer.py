import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import connection, transaction
from forecast.models import ForecastDataset, ForecastQuantile, ForecastRouteParameters, FlightForecast, LEVELS, Route

ROUTE_CITIES = {
    "MOW-AER": ("Москва", "Сочи"), "MOW-LED": ("Москва", "Санкт-Петербург"),
    "MOW-KGD": ("Москва", "Калининград"), "MOW-OVB": ("Москва", "Новосибирск"),
    "MOW-MRV": ("Москва", "Минеральные Воды"),
}
ROUTE_COLUMNS = {"route", "name", "base_price", "cost_per_passenger", "price_sensitivity"}
FORECAST_COLUMNS = {"route", "date", "seats"} | {f"{q}_{suffix}" for q in LEVELS for suffix in ("base_demand", "price", "price_demand")}

class ImportValidationError(ValueError):
    pass

def fail(filename, line, column, message):
    raise ImportValidationError(f"{filename}: строка {line}, колонка «{column}»: {message}")

def read_rows(content, filename, required):
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportValidationError(f"{filename}: требуется кодировка UTF-8.") from error
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    try:
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)):
            fail(filename, 1, "заголовок", "повторяются названия колонок")
        missing = required - set(headers)
        if missing:
            fail(filename, 1, "заголовок", "нет колонок: " + ", ".join(sorted(missing)))
        rows = []
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                fail(filename, reader.line_num, "строка", "число значений не совпадает с заголовком")
            rows.append((reader.line_num, {k: v.strip() for k, v in row.items()}))
    except csv.Error as error:
        fail(filename, reader.line_num, "строка", f"некорректный CSV: {error}")
    if not rows:
        fail(filename, 2, "строка", "файл не содержит данных")
    return rows

def number(value, filename, line, column, *, whole=18, fraction=12, nonnegative=False):
    try:
        if not re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", value):
            raise InvalidOperation
        result = Decimal(value)
    except (InvalidOperation, TypeError):
        fail(filename, line, column, "ожидается конечное число с точкой как десятичным разделителем")
    if not result.is_finite():
        fail(filename, line, column, "число должно быть конечным")
    if nonnegative and result < 0:
        fail(filename, line, column, "значение не может быть отрицательным")
    digits = list(result.as_tuple().digits)
    exponent = result.as_tuple().exponent
    while digits and digits[-1] == 0:
        digits.pop()
        exponent += 1
    fractional_digits = max(0, -exponent) if digits else 0
    if result and result.adjusted() >= whole or fractional_digits > fraction:
        fail(filename, line, column, f"поддерживается до {whole} цифр до точки и {fraction} после")
    return result

def validate_sources(forecast_content, routes_content, forecast_name, routes_name):
    parsed_routes = {}
    for line, row in read_rows(routes_content, routes_name, ROUTE_COLUMNS):
        code = row["route"]
        if code not in ROUTE_CITIES:
            fail(routes_name, line, "route", "неизвестный код; добавьте проверенное соответствие городам в ROUTE_CITIES")
        if code in parsed_routes:
            fail(routes_name, line, "route", "маршрут повторяется")
        if not row["name"] or len(row["name"]) > 160:
            fail(routes_name, line, "name", "ожидается непустое название до 160 символов")
        numeric = {}
        for column, value in row.items():
            if column in {"route", "name"} or not value:
                continue
            is_money = column in {"base_price", "cost_per_passenger", "price_min", "price_max"}
            numeric[column] = number(value, routes_name, line, column,
                                     whole=16 if is_money else 12 if column == "price_sensitivity" else 18,
                                     fraction=8 if is_money else 12,
                                     nonnegative=column in {"base_price", "cost_per_passenger", "price_min", "price_max"})
        for column in ROUTE_COLUMNS - {"route", "name"}:
            if column not in numeric:
                fail(routes_name, line, column, "значение обязательно")
        if numeric["price_sensitivity"] <= 0:
            fail(routes_name, line, "price_sensitivity", "чувствительность должна быть положительной")
        if "price_min" in numeric and "price_max" in numeric and numeric["price_min"] > numeric["price_max"]:
            fail(routes_name, line, "price_max", "меньше price_min")
        parsed_routes[code] = {"name": row["name"], "numeric": numeric}
    forecasts = []
    seen = set()
    for line, row in read_rows(forecast_content, forecast_name, FORECAST_COLUMNS):
        code = row["route"]
        if code not in parsed_routes:
            fail(forecast_name, line, "route", "маршрут отсутствует в справочнике")
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]):
                raise ValueError
            day = date.fromisoformat(row["date"])
        except ValueError:
            fail(forecast_name, line, "date", "ожидается существующая дата YYYY-MM-DD")
        key = (code, day)
        if key in seen:
            fail(forecast_name, line, "route/date", "повторяется маршрут и дата")
        seen.add(key)
        seats = number(row["seats"], forecast_name, line, "seats", whole=10, fraction=0, nonnegative=True)
        if seats != seats.to_integral_value() or seats > 2147483647:
            fail(forecast_name, line, "seats", "ожидается целая неотрицательная вместимость не более 2147483647")
        quantiles = []
        previous = None
        for q in LEVELS:
            base = number(row[f"{q}_base_demand"], forecast_name, line, f"{q}_base_demand")
            if previous is not None and base < previous:
                fail(forecast_name, line, f"{q}_base_demand", "квантили спроса пересекаются")
            previous = base
            price = number(row[f"{q}_price"], forecast_name, line, f"{q}_price", whole=16, fraction=8, nonnegative=True)
            demand = number(row[f"{q}_price_demand"], forecast_name, line, f"{q}_price_demand")
            quantiles.append((q, base, price, demand))
        forecasts.append((code, day, int(seats), quantiles))
    return parsed_routes, forecasts

@dataclass(frozen=True)
class ImportResult:
    dataset: ForecastDataset
    created: bool
    forecasts: int

def import_dataset(forecast_path, routes_path):
    forecast_path, routes_path = Path(forecast_path), Path(routes_path)
    forecast_content, routes_content = forecast_path.read_bytes(), routes_path.read_bytes()
    route_data, forecast_data = validate_sources(forecast_content, routes_content, forecast_path.name, routes_path.name)
    hashes = {"forecast_sha256": hashlib.sha256(forecast_content).hexdigest(),
              "routes_sha256": hashlib.sha256(routes_content).hexdigest()}
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [831809521482])
        existing = ForecastDataset.objects.filter(**hashes).first()
        if existing:
            ForecastDataset.objects.filter(is_active=True).exclude(pk=existing.pk).update(is_active=False)
            ForecastDataset.objects.filter(pk=existing.pk).update(is_active=True)
            existing.refresh_from_db()
            return ImportResult(existing, False, existing.flights.count())
        dataset = ForecastDataset.objects.create(**hashes, forecast_filename=forecast_path.name,
            routes_filename=routes_path.name, is_active=False,
            route_snapshot={code: {k: str(v) for k, v in entry["numeric"].items()} for code, entry in route_data.items()})
        routes = {}
        for code, entry in route_data.items():
            origin, destination = ROUTE_CITIES[code]
            route, _ = Route.objects.update_or_create(code=code, defaults={"name": entry["name"], "origin": origin, "destination": destination})
            routes[code] = route
            values = entry["numeric"]
            fields = {key: values.get(key) for key in ("base_price", "cost_per_passenger", "price_sensitivity", "price_min", "price_max")}
            ForecastRouteParameters.objects.create(dataset=dataset, route=route, **fields,
                extra_numeric={k: str(v) for k, v in values.items() if k not in fields})
        flights = FlightForecast.objects.bulk_create([FlightForecast(dataset=dataset, route=routes[code], date=day, seats=seats)
                                                      for code, day, seats, _ in forecast_data])
        ForecastQuantile.objects.bulk_create([ForecastQuantile(forecast=flight, level=q, base_demand=base, optimal_price=price, price_demand=demand)
            for flight, (_, _, _, quantiles) in zip(flights, forecast_data, strict=True) for q, base, price, demand in quantiles])
        ForecastDataset.objects.filter(is_active=True).update(is_active=False)
        dataset.is_active = True
        dataset.save(update_fields=["is_active"])
        return ImportResult(dataset, True, len(flights))
