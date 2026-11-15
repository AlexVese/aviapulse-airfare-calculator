import csv
import tempfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from django.db import IntegrityError, transaction, connections, close_old_connections
from django.test import TestCase, TransactionTestCase
from forecast.models import ForecastDataset, ForecastQuantile, ForecastRouteParameters, FlightForecast
from forecast.services.importer import ImportValidationError, import_dataset
from forecast.tests.factories import write_sources

class ImportTests(TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.forecast, self.routes = write_sources(self.folder.name)
        self.original = import_dataset(self.forecast, self.routes).dataset

    def mutate(self, field, value):
        with self.forecast.open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            columns, rows = reader.fieldnames, list(reader)
        rows[0][field] = value
        with self.forecast.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def test_identical_import_is_idempotent(self):
        result = import_dataset(self.forecast, self.routes)
        self.assertFalse(result.created)
        self.assertEqual(result.dataset.pk, self.original.pk)
        self.assertEqual(ForecastDataset.objects.count(), 1)
        self.assertEqual(FlightForecast.objects.count(), 2)
        self.assertEqual(ForecastQuantile.objects.count(), 18)

    def test_new_version_snapshots_and_reactivation(self):
        original_routes = self.routes.read_bytes()
        write_sources(self.folder.name, base_price="1200")
        latest = import_dataset(self.forecast, self.routes).dataset
        self.assertNotEqual(latest.pk, self.original.pk)
        self.assertEqual(ForecastRouteParameters.objects.get(dataset=self.original).base_price, Decimal(1000))
        self.assertEqual(ForecastRouteParameters.objects.get(dataset=latest).base_price, Decimal(1200))
        self.routes.write_bytes(original_routes)
        old = import_dataset(self.forecast, self.routes)
        self.assertFalse(old.created)
        self.assertEqual(ForecastDataset.objects.get(is_active=True).pk, self.original.pk)
        self.assertEqual(ForecastDataset.objects.count(), 2)

    def test_invalid_csv_keeps_active_dataset(self):
        original_content = self.forecast.read_bytes()
        cases = [("0.6_base_demand", "1"), ("seats", "1.5"), ("seats", "-1"),
                 ("date", "2026-02-30"), ("route", "UNKNOWN"), ("0.5_base_demand", "NaN"),
                 ("0.5_base_demand", "10.1234567890123")]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                self.forecast.write_bytes(original_content)
                self.mutate(field, value)
                with self.assertRaisesRegex(ImportValidationError, "строка 2, колонка"):
                    import_dataset(self.forecast, self.routes)
                self.assertEqual(ForecastDataset.objects.get(is_active=True).pk, self.original.pk)
                self.assertEqual(ForecastDataset.objects.count(), 1)

    def test_duplicate_missing_quantile_and_bad_sensitivity(self):
        original_forecast, original_routes = self.forecast.read_bytes(), self.routes.read_bytes()
        lines = original_forecast.splitlines(keepends=True)
        self.forecast.write_bytes(original_forecast + lines[1])
        with self.assertRaisesRegex(ImportValidationError, "повторяется"):
            import_dataset(self.forecast, self.routes)
        self.forecast.write_bytes(original_forecast.replace(b"0.9_base_demand", b"missing"))
        with self.assertRaisesRegex(ImportValidationError, "нет колонок"):
            import_dataset(self.forecast, self.routes)
        self.forecast.write_bytes(original_forecast)
        self.routes.write_bytes(original_routes.replace(b",0.1,", b",0,"))
        with self.assertRaisesRegex(ImportValidationError, "положительной"):
            import_dataset(self.forecast, self.routes)

    def test_database_failure_rolls_back_entire_version(self):
        write_sources(self.folder.name, start=80)
        with patch("forecast.services.importer.ForecastQuantile.objects.bulk_create", side_effect=RuntimeError("database failure")):
            with self.assertRaises(RuntimeError):
                import_dataset(self.forecast, self.routes)
        self.assertEqual(ForecastDataset.objects.get(is_active=True).pk, self.original.pk)
        self.assertEqual(ForecastDataset.objects.count(), 1)
        self.assertEqual(ForecastQuantile.objects.count(), 18)

    def test_database_enforces_single_active_version(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ForecastDataset.objects.create(forecast_filename="x", routes_filename="y", forecast_sha256="a" * 64,
                routes_sha256="b" * 64, is_active=True, route_snapshot={})

class ConcurrentImportTests(TransactionTestCase):
    def test_parallel_identical_import_creates_one_active_version(self):
        with tempfile.TemporaryDirectory() as directory:
            forecast, routes = write_sources(directory)
            def load():
                close_old_connections()
                try:
                    result = import_dataset(forecast, routes)
                    return str(result.dataset.pk), result.created
                finally:
                    connections.close_all()
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(lambda _: load(), range(2)))
        self.assertEqual(len({pk for pk, _ in results}), 1)
        self.assertEqual(sum(created for _, created in results), 1)
        self.assertEqual(ForecastDataset.objects.filter(is_active=True).count(), 1)
        self.assertEqual(ForecastQuantile.objects.count(), 18)
