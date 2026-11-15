import csv
import http.cookiejar
import json
import re
import sys
import urllib.request
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
base_url = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
html = opener.open(base_url + "/", timeout=10).read().decode()
token = re.search(r'name="csrfmiddlewaretoken" value="([A-Za-z0-9]+)"', html).group(1)
with (ROOT / "data/routes.csv").open(encoding="utf-8-sig", newline="") as file:
    parameters = {r["route"]: r for r in csv.DictReader(file)}
with (ROOT / "data/my_forecast.csv").open(encoding="utf-8-sig", newline="") as file:
    forecasts = list(csv.DictReader(file))
routes = json.load(opener.open(base_url + "/api/routes", timeout=10))
tested = 0
for route in routes["routes"]:
    row = next(r for r in forecasts if r["route"] == route["code"])
    params = parameters[route["code"]]
    dates = json.load(opener.open(base_url + f'/api/routes/{route["code"]}/dates', timeout=10))
    assert len(dates["dates"]) == sum(r["route"] == route["code"] for r in forecasts)
    for price in ["0", params["base_price"], "100000.125"]:
        request = urllib.request.Request(base_url + "/api/forecast", method="POST",
            headers={"Content-Type": "application/json", "X-CSRFToken": token, "Origin": base_url},
            data=json.dumps({"origin": route["origin"], "destination": route["destination"], "date": row["date"], "price": price}).encode())
        response = json.load(opener.open(request, timeout=10))
        with localcontext() as context:
            context.prec = 64
            expected = {str(i / 10): Decimal(row[f"{i / 10}_base_demand"]) - Decimal(params["price_sensitivity"]) * (Decimal(price) - Decimal(params["base_price"])) for i in range(1, 10)}
            assert {p["level"]: Decimal(p["demand"]) for p in response["quantiles"]} == expected
            assert Decimal(response["median_demand"]) == expected["0.5"]
            assert response["median_demand"] == response["quantiles"][4]["demand"]
            sales = min(Decimal(row["seats"]), max(Decimal(0), expected["0.5"]))
            assert Decimal(response["sales"]) == sales
            assert Decimal(response["free_seats"]) == Decimal(row["seats"]) - sales
        assert response["dataset"]["id"] == routes["dataset"]["id"]
        tested += 1
print(json.dumps({"status": "PASS", "routes": len(routes["routes"]), "real_api_calculations": tested,
                  "dataset_id": routes["dataset"]["id"], "browser_test": "not included"}, ensure_ascii=False))
