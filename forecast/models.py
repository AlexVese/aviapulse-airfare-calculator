import uuid
from decimal import Decimal
from django.db import models
from django.db.models import Q

LEVELS = tuple(Decimal(i) / 10 for i in range(1, 10))

class Route(models.Model):
    code = models.CharField("Код", max_length=32, unique=True)
    name = models.CharField("Название", max_length=160)
    origin = models.CharField("Откуда", max_length=80)
    destination = models.CharField("Куда", max_length=80)

    class Meta:
        ordering = ["code"]
        verbose_name = "Маршрут"
        verbose_name_plural = "Маршруты"

    def __str__(self):
        return f"{self.code} · {self.name}"

class ForecastDataset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    imported_at = models.DateTimeField("Дата импорта", auto_now_add=True)
    forecast_filename = models.CharField("Файл прогноза", max_length=255)
    routes_filename = models.CharField("Файл маршрутов", max_length=255)
    forecast_sha256 = models.CharField(max_length=64)
    routes_sha256 = models.CharField(max_length=64)
    is_active = models.BooleanField("Активная версия", default=False)
    route_snapshot = models.JSONField("Исходные параметры маршрутов")

    class Meta:
        ordering = ["-imported_at"]
        verbose_name = "Версия прогноза"
        verbose_name_plural = "Версии прогнозов"
        constraints = [
            models.UniqueConstraint(fields=["forecast_sha256", "routes_sha256"], name="unique_source_pair"),
            models.UniqueConstraint(fields=["is_active"], condition=Q(is_active=True), name="one_active_dataset"),
        ]

    def __str__(self):
        return f"{str(self.pk)[:8]} · {self.forecast_filename}"

class ForecastRouteParameters(models.Model):
    dataset = models.ForeignKey(ForecastDataset, on_delete=models.PROTECT, related_name="route_parameters")
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="parameters")
    base_price = models.DecimalField("Базовая цена", max_digits=24, decimal_places=8)
    cost_per_passenger = models.DecimalField("Расход на пассажира", max_digits=24, decimal_places=8)
    price_sensitivity = models.DecimalField("Чувствительность", max_digits=24, decimal_places=12)
    price_min = models.DecimalField("Рекомендуемая цена от", max_digits=24, decimal_places=8, null=True, blank=True)
    price_max = models.DecimalField("Рекомендуемая цена до", max_digits=24, decimal_places=8, null=True, blank=True)
    extra_numeric = models.JSONField("Дополнительные параметры", default=dict)

    class Meta:
        verbose_name = "Параметры маршрута в версии"
        verbose_name_plural = "Параметры маршрутов в версиях"
        constraints = [models.UniqueConstraint(fields=["dataset", "route"], name="unique_version_parameters"),
                       models.CheckConstraint(condition=Q(base_price__gte=0) & Q(cost_per_passenger__gte=0) & Q(price_sensitivity__gt=0), name="valid_route_parameters")]

    def __str__(self):
        return f"{self.route.code} · {str(self.dataset_id)[:8]}"

class FlightForecast(models.Model):
    dataset = models.ForeignKey(ForecastDataset, on_delete=models.PROTECT, related_name="flights")
    route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name="flights")
    date = models.DateField("Дата")
    seats = models.PositiveIntegerField("Вместимость")

    class Meta:
        ordering = ["route__code", "date"]
        verbose_name = "Прогноз на дату"
        verbose_name_plural = "Прогнозы на даты"
        constraints = [models.UniqueConstraint(fields=["dataset", "route", "date"], name="unique_flight_forecast")]

    def __str__(self):
        return f"{self.route.code} · {self.date}"

class ForecastQuantile(models.Model):
    forecast = models.ForeignKey(FlightForecast, on_delete=models.PROTECT, related_name="quantiles")
    level = models.DecimalField("Квантиль", max_digits=2, decimal_places=1, choices=[(q, str(q)) for q in LEVELS])
    base_demand = models.DecimalField("Спрос при базовой цене", max_digits=30, decimal_places=12)
    optimal_price = models.DecimalField("Цена из CSV", max_digits=24, decimal_places=8)
    price_demand = models.DecimalField("Спрос при цене из CSV", max_digits=30, decimal_places=12)

    class Meta:
        ordering = ["level"]
        verbose_name = "Квантиль"
        verbose_name_plural = "Квантили"
        constraints = [models.UniqueConstraint(fields=["forecast", "level"], name="unique_forecast_quantile"),
                       models.CheckConstraint(condition=Q(level__in=LEVELS), name="nine_allowed_quantiles")]

    def __str__(self):
        return f"{self.forecast} · {self.level}"
