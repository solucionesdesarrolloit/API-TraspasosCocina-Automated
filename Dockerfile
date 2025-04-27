FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .

# Instalar herramientas necesarias y luego instalar los paquetes de Python
RUN apt-get update && \
    apt-get install -y build-essential cmake libopenblas-dev libx11-dev && \
    pip install --no-cache-dir --use-deprecated=legacy-resolver -r requirements.txt && \
    apt-get remove -y build-essential cmake && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

COPY main.py .
COPY .env .

EXPOSE 8000

CMD ["gunicorn", "main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
