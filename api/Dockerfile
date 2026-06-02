ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim

WORKDIR /app

# Prevents Python from writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Prevents Python from buffering stdout/stderr — logs appear immediately
ENV PYTHONUNBUFFERED=1
# Ensures imports resolve from /app — same as marking api/ as Sources Root
ENV PYTHONPATH=/app

# Install system dependencies
# libpq-dev — required by psycopg2 to connect to PostgreSQL
# gcc — required to compile some Python packages
# Both removed after install to keep image size small
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*


# Python Dependencies
# Copy only requirements first — Docker caches this layer
# so pip install only re-runs when requirements files change
COPY requirements/ requirements/

# REQUIREMENTS_FILE can be passed as build arg or env var
# Defaults to prod.txt for production builds
ARG REQUIREMENTS_FILE=requirements/prod.txt
ENV REQUIREMENTS_FILE=${REQUIREMENTS_FILE}

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r ${REQUIREMENTS_FILE}

COPY . .

ARG API_INTERNAL_PORT=8012
ENV API_INTERNAL_PORT=${API_INTERNAL_PORT}
EXPOSE ${API_INTERNAL_PORT}

CMD ["/bin/bash", "entrypoint.sh"]
