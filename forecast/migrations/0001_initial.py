import django.db.models.deletion
import uuid
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Route',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=32, unique=True, verbose_name='Код')),
                ('name', models.CharField(max_length=160, verbose_name='Название')),
                ('origin', models.CharField(max_length=80, verbose_name='Откуда')),
                ('destination', models.CharField(max_length=80, verbose_name='Куда')),
            ],
            options={
                'verbose_name': 'Маршрут',
                'verbose_name_plural': 'Маршруты',
                'ordering': ['code'],
            },
        ),
        migrations.CreateModel(
            name='ForecastDataset',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('imported_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата импорта')),
                ('forecast_filename', models.CharField(max_length=255, verbose_name='Файл прогноза')),
                ('routes_filename', models.CharField(max_length=255, verbose_name='Файл маршрутов')),
                ('forecast_sha256', models.CharField(max_length=64)),
                ('routes_sha256', models.CharField(max_length=64)),
                ('is_active', models.BooleanField(default=False, verbose_name='Активная версия')),
                ('route_snapshot', models.JSONField(verbose_name='Исходные параметры маршрутов')),
            ],
            options={
                'verbose_name': 'Версия прогноза',
                'verbose_name_plural': 'Версии прогнозов',
                'ordering': ['-imported_at'],
                'constraints': [models.UniqueConstraint(fields=('forecast_sha256', 'routes_sha256'), name='unique_source_pair'), models.UniqueConstraint(condition=models.Q(('is_active', True)), fields=('is_active',), name='one_active_dataset')],
            },
        ),
        migrations.CreateModel(
            name='FlightForecast',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Дата')),
                ('seats', models.PositiveIntegerField(verbose_name='Вместимость')),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='flights', to='forecast.forecastdataset')),
                ('route', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='flights', to='forecast.route')),
            ],
            options={
                'verbose_name': 'Прогноз на дату',
                'verbose_name_plural': 'Прогнозы на даты',
                'ordering': ['route__code', 'date'],
            },
        ),
        migrations.CreateModel(
            name='ForecastQuantile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('level', models.DecimalField(choices=[(Decimal('0.1'), '0.1'), (Decimal('0.2'), '0.2'), (Decimal('0.3'), '0.3'), (Decimal('0.4'), '0.4'), (Decimal('0.5'), '0.5'), (Decimal('0.6'), '0.6'), (Decimal('0.7'), '0.7'), (Decimal('0.8'), '0.8'), (Decimal('0.9'), '0.9')], decimal_places=1, max_digits=2, verbose_name='Квантиль')),
                ('base_demand', models.DecimalField(decimal_places=12, max_digits=30, verbose_name='Спрос при базовой цене')),
                ('optimal_price', models.DecimalField(decimal_places=8, max_digits=24, verbose_name='Цена из CSV')),
                ('price_demand', models.DecimalField(decimal_places=12, max_digits=30, verbose_name='Спрос при цене из CSV')),
                ('forecast', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='quantiles', to='forecast.flightforecast')),
            ],
            options={
                'verbose_name': 'Квантиль',
                'verbose_name_plural': 'Квантили',
                'ordering': ['level'],
                'constraints': [models.UniqueConstraint(fields=('forecast', 'level'), name='unique_forecast_quantile'), models.CheckConstraint(condition=models.Q(('level__in', (Decimal('0.1'), Decimal('0.2'), Decimal('0.3'), Decimal('0.4'), Decimal('0.5'), Decimal('0.6'), Decimal('0.7'), Decimal('0.8'), Decimal('0.9')))), name='nine_allowed_quantiles')],
            },
        ),
        migrations.CreateModel(
            name='ForecastRouteParameters',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('base_price', models.DecimalField(decimal_places=8, max_digits=24, verbose_name='Базовая цена')),
                ('cost_per_passenger', models.DecimalField(decimal_places=8, max_digits=24, verbose_name='Расход на пассажира')),
                ('price_sensitivity', models.DecimalField(decimal_places=12, max_digits=24, verbose_name='Чувствительность')),
                ('price_min', models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True, verbose_name='Рекомендуемая цена от')),
                ('price_max', models.DecimalField(blank=True, decimal_places=8, max_digits=24, null=True, verbose_name='Рекомендуемая цена до')),
                ('extra_numeric', models.JSONField(default=dict, verbose_name='Дополнительные параметры')),
                ('dataset', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='route_parameters', to='forecast.forecastdataset')),
                ('route', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='parameters', to='forecast.route')),
            ],
            options={
                'verbose_name': 'Параметры маршрута в версии',
                'verbose_name_plural': 'Параметры маршрутов в версиях',
                'constraints': [models.UniqueConstraint(fields=('dataset', 'route'), name='unique_version_parameters'), models.CheckConstraint(condition=models.Q(('base_price__gte', 0), ('cost_per_passenger__gte', 0), ('price_sensitivity__gt', 0)), name='valid_route_parameters')],
            },
        ),
        migrations.AddConstraint(
            model_name='flightforecast',
            constraint=models.UniqueConstraint(fields=('dataset', 'route', 'date'), name='unique_flight_forecast'),
        ),
    ]
