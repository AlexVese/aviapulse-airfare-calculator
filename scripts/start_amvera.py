import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.amvera"

import django

django.setup()

from django.core.management import call_command
from django.db import connection, OperationalError
from forecast.models import ForecastDataset

for attempt in range(12):
    try:
        connection.ensure_connection()
        break
    except OperationalError:
        if attempt == 11:
            raise
        print("Waiting for PostgreSQL...", flush=True)
        time.sleep(3)

with connection.cursor() as cursor:
    cursor.execute("SELECT pg_advisory_lock(%s)", [831809521483])
try:
    call_command("migrate", interactive=False)
    if not ForecastDataset.objects.filter(is_active=True).exists():
        call_command("import_forecast", forecast="data/my_forecast.csv", routes="data/routes.csv")
finally:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [831809521483])

call_command("collectstatic", interactive=False, verbosity=0)
connection.close()
os.execvp("gunicorn", [
    "gunicorn", "config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2",
    "--timeout=30", "--access-logfile=-", "--error-logfile=-",
])
