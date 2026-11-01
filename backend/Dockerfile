FROM python:3.12-slim

WORKDIR /srv
COPY backend /srv/backend
COPY q /srv/q
WORKDIR /srv/backend
RUN pip install --no-cache-dir .
ENV MARKETSTREAM_DATA_DIR=/data \
    MARKETSTREAM_Q_ENABLED=false \
    PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["marketstream"]
