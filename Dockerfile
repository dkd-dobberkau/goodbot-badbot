FROM python:3.12-slim

WORKDIR /app

RUN useradd -m -u 1000 appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser templates/ ./templates/
COPY --chown=appuser:appuser vendor/ ./vendor/
COPY --chown=appuser:appuser content/ ./content/

RUN mkdir -p data && chown appuser:appuser data

# Late ARG so changing the SHA doesn't invalidate the pip-install layer.
ARG GIT_SHA=unknown
ENV BUILD_VERSION=$GIT_SHA

USER appuser

# Trust X-Forwarded-For only from Mittwald's ingress, which connects from the
# 100.64.0.0/10 shared address space (RFC 6598; peers seen 2026-11-17:
# 100.125.x.x). With "*" uvicorn took the first entry, which the client sets
# itself, so anyone could choose the IP behind ip_hash, rate limits and spoof
# detection. Now uvicorn takes the entry the ingress appended.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "100.64.0.0/10"]
