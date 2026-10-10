FROM node:20.15.1-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ARG REACT_APP_API_BASE_URL=
ENV REACT_APP_API_BASE_URL=${REACT_APP_API_BASE_URL}
RUN npm run build

FROM python:3.12.4-slim-bookworm AS backend
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FLASK_ENV=production \
    FLASK_DEBUG=0 \
    APP_ENV=production \
    PORT=5000
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt
COPY backend/ /app/backend/
COPY --from=frontend-build /app/frontend/build /app/frontend/build
EXPOSE 5000
WORKDIR /app/backend
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/ready', timeout=2).read()"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "wsgi:app"]
