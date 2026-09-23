FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Collect static files at build time (served by WhiteNoise)
RUN SECRET_KEY=build-time-placeholder python manage.py collectstatic --noinput

RUN chmod +x start.sh

EXPOSE 8000

CMD ["./start.sh"]
