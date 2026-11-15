# Запуск в Amvera

Приложение и PostgreSQL создаются отдельными проектами в одном регионе. Для демо достаточно одного экземпляра приложения и одной реплики БД на тарифах «Начальный». Покупать домен не нужно: включите бесплатный адрес HTTPS в настройках приложения.

## Приложение

Загрузите корень этого репозитория, включая `amvera.yml`. Сборка использует существующий Dockerfile; запуск — `python scripts/start_amvera.py`, порт 8000. Caddy и Docker Compose на платформе не нужны.

В разделе «Переменные» задайте:

| Имя | Значение |
|---|---|
| `DJANGO_SECRET_KEY` | Новый случайный секрет не короче 50 символов; тип «Секрет» |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_ALLOWED_HOSTS` | Точный домен приложения без `https://`, плюс `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://` и точный домен приложения |
| `DJANGO_SECURE_COOKIES` | `True` |
| `DJANGO_SSL_REDIRECT` | `True` |
| `POSTGRES_HOST` | Внутренний адрес БД для чтения и записи из кабинета Amvera |
| `POSTGRES_PORT` | `5432` |
| `POSTGRES_DB` | Созданная база, например `airfare` |
| `POSTGRES_USER` | Созданный пользователь, например `airfare` |
| `POSTGRES_PASSWORD` | Пароль этого пользователя БД; тип «Секрет» |

Пароль пользователя приложения и пароль суперпользователя PostgreSQL могут отличаться. Для приложения используйте созданного пользователя БД. Внутреннее подключение не требует публикации PostgreSQL в интернете.

Стартовый скрипт ожидает БД, применяет миграции, при отсутствии активного набора импортирует включённые CSV, собирает статику и запускает Gunicorn. Миграции и первичный импорт защищены PostgreSQL advisory lock. При перезапуске активный набор сохраняется. WhiteNoise раздаёт статику с настройками `config.amvera`.

## Проверка

Откройте публичный адрес: проверьте калькулятор, график, регистрацию и вход. `GET /health` должен отвечать 200. Для 15 контрольных расчётов: `python scripts/verify_running.py https://домен-приложения`.

Для локальной проверки адаптации:

```sh
docker compose build web
docker compose run --rm -e DJANGO_SETTINGS_MODULE=config.amvera web sh -c 'python manage.py collectstatic --noinput --verbosity 0 && python manage.py test forecast accounts -v 1'
```

Для загрузки нового прогноза используйте команду `import_forecast` из README. Обычный перезапуск не заменяет активную версию файлами из образа. Настройки и секреты задаются в кабинете; `.env` загружать не нужно.

[Docker в Amvera](https://docs.amvera.ru/applications/configuration/docker.html), [PostgreSQL](https://docs.amvera.ru/databases/postgreSQL.html), [домены и HTTPS](https://docs.amvera.ru/applications/configuration/network.html).
