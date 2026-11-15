from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render

def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})

def error_response(request, status, message):
    if request.path.startswith("/api/"):
        return JsonResponse({"error": {"message": message}}, status=status)
    return render(request, "error.html", {"status": status, "message": message}, status=status)

def csrf_failure(request, reason=""):
    return error_response(request, 403, "Сессия формы устарела. Обновите страницу и попробуйте снова.")

def bad_request(request, exception=None):
    return error_response(request, 400, "Не удалось обработать запрос.")

def forbidden(request, exception=None):
    return error_response(request, 403, "Доступ к этой странице ограничен.")

def not_found(request, exception=None):
    return error_response(request, 404, "Страница не найдена.")

def server_error(request):
    return error_response(request, 500, "Сервис временно недоступен. Попробуйте позже.")
