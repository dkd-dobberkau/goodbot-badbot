FROM python:3.12-slim

WORKDIR /app

RUN useradd -m -u 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser vendor/ ./vendor/

RUN mkdir -p data && chown appuser:appuser data

# Late ARG so changing the SHA doesn't invalidate the pip-install layer.
ARG GIT_SHA=unknown
ENV BUILD_VERSION=$GIT_SHA

USER appuser

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
