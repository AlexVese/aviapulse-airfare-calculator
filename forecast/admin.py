from django.contrib import admin
from forecast.models import ForecastDataset, ForecastQuantile, ForecastRouteParameters, FlightForecast, Route

class ImportedReadOnly(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(Route)
class RouteAdmin(ImportedReadOnly):
    list_display = ["code", "name", "origin", "destination"]
    search_fields = ["code", "name", "origin", "destination"]

@admin.register(ForecastDataset)
class DatasetAdmin(ImportedReadOnly):
    list_display = ["id", "forecast_filename", "imported_at", "is_active"]
    list_filter = ["is_active", "imported_at"]
    search_fields = ["forecast_filename", "routes_filename", "forecast_sha256", "routes_sha256"]

@admin.register(ForecastRouteParameters)
class ParametersAdmin(ImportedReadOnly):
    list_display = ["route", "dataset", "base_price", "price_sensitivity"]
    list_filter = ["dataset", "route"]
    search_fields = ["route__code", "route__name"]

@admin.register(FlightForecast)
class ForecastAdmin(ImportedReadOnly):
    list_display = ["route", "date", "dataset", "seats"]
    list_filter = ["route", "date", "dataset"]
    search_fields = ["route__code", "route__name"]
    date_hierarchy = "date"
    list_select_related = ["route", "dataset"]

@admin.register(ForecastQuantile)
class QuantileAdmin(ImportedReadOnly):
    list_display = ["forecast", "level", "base_demand", "optimal_price", "price_demand"]
    list_filter = ["level", "forecast__dataset", "forecast__route", "forecast__date"]
    search_fields = ["forecast__route__code", "forecast__route__name"]
    list_select_related = ["forecast__route"]
