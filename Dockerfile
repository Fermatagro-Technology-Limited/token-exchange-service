# Stage 1: Build
FROM python:3.12-slim AS builder

# Install Poetry and upgrade pip
RUN pip install --no-cache-dir --upgrade pip poetry

# Set the working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install production dependencies and clean up caches
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-root --no-interaction --no-ansi \
    && rm -rf ~/.cache/pip ~/.cache/pypoetry

# Copy application source code
COPY src ./src

# Precompile Python files for runtime optimization
RUN python -m compileall -q /usr/local/lib/python3.12/site-packages

# Stage 2: Production
FROM python:3.12-slim

# Add a non-root user for security
RUN useradd -ms /bin/bash appuser
USER appuser

# Set the working directory
WORKDIR /app

# Copy dependencies and application code from the builder stage
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /app/src ./src

# Set environment variables for Python optimization
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Use Poetry-installed Uvicorn directly
ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["src.main:app", "--host", "0.0.0.0", "--port", "8000"]