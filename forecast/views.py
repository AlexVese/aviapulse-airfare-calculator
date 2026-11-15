import json
import logging
from decimal import Decimal, DecimalException
from functools import wraps
from django.core.exceptions import RequestDataTooBig
from django.db import DatabaseError
from django.db.models import Min, Max
from django.http import JsonResponse
from django.shortcuts import render
from forecast.forms import ForecastInputForm
from forecast.models import ForecastDataset, ForecastRouteParameters, FlightForecast, Route
from forecast.services.calculation import calculate_forecast

logger = logging.getLogger(__name__)

def api_error(message, status, fields=None):
    error = {"message": message}
    if fields:
        error["fields"] = fields
    return JsonResponse({"error": error}, status=status)

def api(method):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if request.method != method:
                response = api_error("Метод запроса не поддерживается.", 405)
                response["Allow"] = method
                return response
            try:
                dataset = ForecastDataset.objects.filter(is_active=True).first()
                if dataset is None:
                    return api_error("Прогнозы ещё не загружены. Попробуйте позже.", 503)
                return view(request, dataset, *args, **kwargs)
            except DatabaseError:
                logger.exception("Forecast database unavailable")
                return api_error("Сервис данных временно недоступен. Попробуйте позже.", 503)
        return wrapped
    return decorator

def calculator(request):
    return render(request, "forecast/calculator.html")

def dataset_metadata(dataset):
    return {"id": str(dataset.pk), "imported_at": dataset.imported_at.isoformat()}

@api("GET")
def routes_api(request, dataset):
    parameters = ForecastRouteParameters.objects.filter(dataset=dataset, route__flights__dataset=dataset).select_related("route").distinct().order_by("route__destination")
    rows = [{"code": p.route.code, "name": p.route.name, "origin": p.route.origin, "destination": p.route.destination,
             "base_price": str(p.base_price), "price_min": str(p.price_min) if p.price_min is not None else None,
             "price_max": str(p.price_max) if p.price_max is not None else None} for p in parameters]
    span = dataset.flights.aggregate(start=Min("date"), end=Max("date"))
    return JsonResponse({"routes": rows, "dataset": dataset_metadata(dataset),
                         "period": {key: value.isoformat() if value else None for key, value in span.items()}})

@api("GET")
def dates_api(request, dataset, route_code):
    rows = list(FlightForecast.objects.filter(dataset=dataset, route__code=route_code).order_by("date").values("date", "seats"))
    if not rows:
        return api_error("Для этого направления нет доступных прогнозов.", 404)
    return JsonResponse({"route": route_code, "dates": [{"date": r["date"].isoformat(), "seats": r["seats"]} for r in rows],
                         "dataset": dataset_metadata(dataset)})

def reject_constant(value):
    raise ValueError("Non-finite JSON number")

@api("POST")
def forecast_api(request, dataset):
    try:
        if request.content_type != "application/json":
            return api_error("Отправьте параметры в формате JSON.", 400)
        data = json.loads(request.body, parse_float=Decimal, parse_constant=reject_constant)
        if not isinstance(data, dict):
            return api_error("Ожидается JSON-объект с параметрами расчёта.", 400)
    except (ValueError, UnicodeDecodeError, RequestDataTooBig, RecursionError, DecimalException):
        return api_error("Не удалось прочитать параметры запроса.", 400)
    for field in ("origin", "destination", "date"):
        value = data.get(field)
        if value is not None and not isinstance(value, str):
            return api_error("Проверьте параметры расчёта.", 400, {field: ["Ожидается строка."]})
        try:
            if value is not None:
                value.encode("utf-8")
        except UnicodeEncodeError:
            return api_error("Проверьте параметры расчёта.", 400, {field: ["Строка содержит неподдерживаемые символы."]})
    form = ForecastInputForm(data)
    if not form.is_valid():
        return api_error("Проверьте параметры расчёта.", 400, {key: list(value) for key, value in form.errors.items()})
    values = form.cleaned_data
    routes = list(Route.objects.filter(origin=values["origin"], destination=values["destination"], flights__dataset=dataset).distinct())
    if not routes:
        return api_error("Для выбранного направления нет прогноза.", 404)
    if len(routes) != 1:
        return api_error("Направление неоднозначно. Уточните параметры маршрутов у администратора.", 400)
    route = routes[0]
    flight = FlightForecast.objects.filter(dataset=dataset, route=route, date=values["date"]).prefetch_related("quantiles").first()
    if flight is None:
        return api_error("На выбранную дату нет прогноза. Выберите дату из списка.", 404)
    parameters = ForecastRouteParameters.objects.get(dataset=dataset, route=route)
    try:
        result = calculate_forecast(base_demands={q.level: q.base_demand for q in flight.quantiles.all()},
                                    price=values["price"], parameters=parameters, seats=flight.seats)
    except (ValueError, DecimalException):
        return api_error("Не удалось рассчитать прогноз для указанной цены.", 400)
    return JsonResponse({**result, "route": {"code": route.code, "name": route.name, "origin": route.origin, "destination": route.destination},
                         "date": flight.date.isoformat(), "dataset": dataset_metadata(dataset)})
