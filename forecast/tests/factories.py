import csv
from pathlib import Path
from forecast.models import LEVELS

def write_sources(directory, *, base_price="1000", start=70):
    directory = Path(directory)
    routes = directory / "routes.csv"
    with routes.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["route", "name", "base_price", "cost_per_passenger", "price_sensitivity", "price_min", "price_max"])
        writer.writeheader()
        writer.writerow({"route": "MOW-AER", "name": "Москва — Сочи", "base_price": base_price,
                         "cost_per_passenger": "500", "price_sensitivity": "0.1", "price_min": "600", "price_max": "2000"})
    forecast = directory / "forecast.csv"
    columns = ["route", "date", "seats"] + [f"{q}_{suffix}" for q in LEVELS for suffix in ("base_demand", "price", "price_demand")]
    with forecast.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for day, seats in [("2026-06-01", 100), ("2026-06-02", 0)]:
            row = {"route": "MOW-AER", "date": day, "seats": seats}
            for i, q in enumerate(LEVELS):
                row.update({f"{q}_base_demand": str(start + i * 10), f"{q}_price": "1000", f"{q}_price_demand": str(start + i * 10)})
            writer.writerow(row)
    return forecast, routes
