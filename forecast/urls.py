from django.urls import path
from forecast import views

urlpatterns = [
    path("", views.calculator, name="calculator"),
    path("api/routes", views.routes_api, name="api-routes"),
    path("api/routes/<str:route_code>/dates", views.dates_api, name="api-dates"),
    path("api/forecast", views.forecast_api, name="api-forecast"),
]
