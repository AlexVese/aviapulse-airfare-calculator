import tempfile
from decimal import Decimal
from django.test import Client, TestCase
from forecast.models import ForecastDataset
from forecast.services.importer import import_dataset
from forecast.tests.factories import write_sources

class ApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with tempfile.TemporaryDirectory() as directory:
            files = write_sources(directory)
            import_dataset(*files)

    def calculate(self, **overrides):
        return self.client.post("/api/forecast", data={"origin": "Москва", "destination": "Сочи", "date": "2026-06-01", "price": "1000.25", **overrides}, content_type="application/json")

    def test_routes_dates_and_median_match_chart(self):
        self.assertEqual(self.client.get("/api/routes").json()["routes"][0]["code"], "MOW-AER")
        dates = self.client.get("/api/routes/MOW-AER/dates").json()["dates"]
        self.assertEqual(dates, [{"date": "2026-06-01", "seats": 100}, {"date": "2026-06-02", "seats": 0}])
        result = self.calculate().json()
        self.assertEqual(result["median_demand"], result["quantiles"][4]["demand"])
        self.assertEqual(Decimal(result["median_demand"]), Decimal("109.975"))
        self.assertEqual(len(result["quantiles"]), 9)
        self.assertEqual(result["dataset"]["id"], str(ForecastDataset.objects.get(is_active=True).pk))

    def test_errors_and_arbitrary_nonnegative_price(self):
        for price in ["-1", "NaN", "Infinity", "not-a-price", True, "", "1e100000000", "1e-100000000"]:
            with self.subTest(price=price):
                response = self.calculate(price=price)
                self.assertEqual(response.status_code, 400)
                self.assertIn("message", response.json()["error"])
        self.assertEqual(self.calculate(date="2026-07-15").status_code, 404)
        self.assertEqual(self.calculate(date="not-a-date").status_code, 400)
        self.assertEqual(self.calculate(destination="Несуществующий город").status_code, 404)
        for price in ["0", "100000.125", "0e-100000000", "1e100"]:
            with self.subTest(price=price):
                self.assertEqual(self.calculate(price=price).status_code, 200)
        negative = self.calculate(price="100000").json()
        self.assertLess(Decimal(negative["median_demand"]), 0)
        self.assertEqual(Decimal(negative["sales"]), 0)
        self.assertEqual(Decimal(negative["nonnegative_median_demand"]), 0)
        self.assertEqual(negative["nonnegative_median_demand"], negative["nonnegative_quantiles"][4]["demand"])
        self.assertTrue(all(Decimal(point["demand"]) >= 0 for point in negative["nonnegative_quantiles"]))
        self.assertEqual(Decimal(self.calculate(date="2026-06-02").json()["load_factor"]), 0)

    def test_missing_data_methods_and_malformed_json(self):
        self.assertEqual(self.client.post("/api/routes").status_code, 405)
        self.assertEqual(self.client.post("/api/forecast", data="[]", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.post("/api/forecast", data="{", content_type="application/json").status_code, 400)
        self.assertEqual(self.client.get("/api/routes/UNKNOWN/dates").status_code, 404)
        ForecastDataset.objects.update(is_active=False)
        for url in ["/api/routes", "/api/routes/MOW-AER/dates"]:
            self.assertEqual(self.client.get(url).status_code, 503)
        self.assertEqual(self.calculate().status_code, 503)

    def test_csrf_is_required_and_guest_calculation_works(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/api/forecast", data={}, content_type="application/json").status_code, 403)
        client.get("/")
        token = client.cookies["csrftoken"].value
        response = client.post("/api/forecast", data={"origin": "Москва", "destination": "Сочи", "date": "2026-06-01", "price": "1000"},
                               content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 200)

    def test_deep_json_and_invalid_unicode_are_rejected(self):
        response = self.client.post("/api/forecast", data="[" * 15000 + "0" + "]" * 15000, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.json()["error"])
        self.assertEqual(self.calculate(origin="\ud800").status_code, 400)
        self.assertEqual(self.calculate(origin={"city": "Москва"}).status_code, 400)
