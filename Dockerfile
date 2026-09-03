FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=3001

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY data/ data/
COPY src/ src/

EXPOSE 3001

# Data is baked into the image; run as a non-root user.
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

CMD ["python", "src/mcp_server.py"]
