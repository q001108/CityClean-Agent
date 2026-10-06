FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN python -m pip install --no-cache-dir --timeout 300 --retries 5 --index-url "$PIP_INDEX_URL" . \
    && useradd --create-home --uid 10001 cityclean

USER cityclean
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "cityclean_agent.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
