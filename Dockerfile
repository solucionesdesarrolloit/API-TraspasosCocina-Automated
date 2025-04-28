FROM bamos/face_recognition:latest

WORKDIR /app

COPY requirements.txt .

# Solo instala lo que falta: FastAPI, Uvicorn, etc.
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["gunicorn", "main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
