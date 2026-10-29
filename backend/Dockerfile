FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd --create-home app && chown -R app /app
USER app
RUN DJANGO_DEBUG=true python manage.py collectstatic --noinput
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && ( [ \"$FLOWPILOT_DEMO_MODE\" != \"true\" ] || python manage.py seed_demo ) && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60"]
