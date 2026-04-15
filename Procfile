release: python manage.py migrate && python manage.py collectstatic --noinput
web: gunicorn backend.wsgi --bind 0.0.0.0:$PORT --workers 3 --log-file -