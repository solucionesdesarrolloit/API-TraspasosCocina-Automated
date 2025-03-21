# Usa una imagen base de Python
FROM python:3.10-slim

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos del proyecto al contenedor
COPY . /app

# Crea un entorno virtual
RUN python -m venv venv

# Activa el entorno virtual e instala dependencias
RUN . /app/venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt

# Expone el puerto 8009
EXPOSE 8009

# Comando para correr Gunicorn con el entorno virtual activado
CMD ["/bin/bash", "-c", ". /app/venv/bin/activate && gunicorn --bind 0.0.0.0:8009 main:app"]


