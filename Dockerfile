FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ODBC kurulumu için sistem araçlarını yükle
RUN apt-get update && apt-get install -y \
    curl gnupg2 apt-transport-https ca-certificates software-properties-common \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Diğer bağımlılıklar
RUN apt-get update && apt-get install -y \
    build-essential gcc \
    freetds-dev libpq-dev libssl-dev libffi-dev \
    libxml2-dev libxslt1-dev zlib1g-dev \
    unixodbc unixodbc-dev libodbc1 odbcinst \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Playwright gerekiyorsa (browser için)
RUN pip install playwright && playwright install --with-deps chromium || true

COPY . /app/

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]

CMD ["celery", "-A", "INSAI", "worker", "--loglevel=info"]
