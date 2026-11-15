from django.core.management.base import BaseCommand, CommandError
from forecast.services.importer import ImportValidationError, import_dataset

class Command(BaseCommand):
    help = "Проверить CSV и атомарно активировать версию прогноза"

    def add_arguments(self, parser):
        parser.add_argument("--forecast", required=True)
        parser.add_argument("--routes", required=True)

    def handle(self, *args, **options):
        try:
            result = import_dataset(options["forecast"], options["routes"])
        except (ImportValidationError, OSError) as error:
            raise CommandError(str(error)) from error
        verb = "Создана" if result.created else "Повторно активирована существующая"
        self.stdout.write(self.style.SUCCESS(f"{verb} версия {result.dataset.pk}: {result.forecasts} прогнозов, {result.forecasts * 9} квантилей."))
