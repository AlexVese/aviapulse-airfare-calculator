from decimal import Decimal, localcontext
from types import SimpleNamespace
from django.test import SimpleTestCase
from forecast.models import LEVELS
from forecast.services.calculation import calculate_forecast

class CalculationTests(SimpleTestCase):
    def calculate(self, price="1000", seats=100):
        return calculate_forecast(base_demands={q: Decimal(70 + i * 10) for i, q in enumerate(LEVELS)},
                                  price=Decimal(price), parameters=SimpleNamespace(base_price=Decimal(1000), price_sensitivity=Decimal("0.1")), seats=seats)

    def test_base_price_and_shared_median(self):
        result = self.calculate()
        self.assertEqual([Decimal(p["demand"]) for p in result["quantiles"]], [Decimal(70 + i * 10) for i in range(9)])
        self.assertEqual(result["median_demand"], result["quantiles"][4]["demand"])

    def test_price_shift_keeps_fractional_precision(self):
        baseline, changed = self.calculate(), self.calculate("1000.25")
        for a, b in zip(baseline["quantiles"], changed["quantiles"], strict=True):
            self.assertEqual(Decimal(a["demand"]) - Decimal(b["demand"]), Decimal("0.025"))

    def test_capacity_and_zero_sales_do_not_clip_demand(self):
        over = self.calculate("0")
        self.assertGreater(Decimal(over["median_demand"]), 100)
        self.assertEqual(Decimal(over["sales"]), 100)
        self.assertEqual(Decimal(over["free_seats"]), 0)
        negative = self.calculate("100000")
        self.assertLess(Decimal(negative["median_demand"]), 0)
        self.assertLess(Decimal(negative["quantiles"][4]["demand"]), 0)
        self.assertEqual(Decimal(negative["sales"]), 0)
        self.assertEqual(Decimal(negative["free_seats"]), 100)

    def test_zero_capacity(self):
        result = self.calculate(seats=0)
        self.assertEqual(Decimal(result["load_factor"]), 0)
        self.assertEqual(Decimal(result["sales"]), 0)
        self.assertEqual(Decimal(result["free_seats"]), 0)

    def test_large_finite_price_does_not_lose_small_terms(self):
        result = self.calculate("1e100")
        with localcontext() as context:
            context.prec = 150
            expected = Decimal(210) - Decimal("1e99")
        self.assertEqual(Decimal(result["median_demand"]), expected)

    def test_unrepresentable_exponents_are_rejected_before_calculation(self):
        for value in ["1e100000000", "1e-100000000"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.calculate(value)
        self.assertEqual(self.calculate("0e-100000000")["price"], "0")

    def test_nonnegative_view_preserves_raw_formula(self):
        result = self.calculate("1850")
        raw = [Decimal(point["demand"]) for point in result["quantiles"]]
        physical = [Decimal(point["demand"]) for point in result["nonnegative_quantiles"]]
        self.assertLess(raw[0], 0)
        self.assertGreater(raw[4], 0)
        self.assertEqual(physical, [max(Decimal(0), value) for value in raw])
        self.assertEqual(result["nonnegative_median_demand"], result["nonnegative_quantiles"][4]["demand"])
        self.assertTrue(result["has_negative_quantiles"])
        self.assertFalse(result["negative_demand"])
        high = self.calculate("100000")
        self.assertLess(Decimal(high["median_demand"]), 0)
        self.assertEqual(Decimal(high["nonnegative_median_demand"]), 0)
        self.assertTrue(all(Decimal(point["demand"]) == 0 for point in high["nonnegative_quantiles"]))
