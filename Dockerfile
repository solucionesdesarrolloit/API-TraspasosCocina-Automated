#(Ubuntu 22.04 + Python 3.10 + ODBC)
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Instala herramientas y dependencias base
RUN apt-get update && apt-get install -y \
    curl \
    gnupg2 \
    apt-transport-https \
    software-properties-common \
    ca-certificates \
    gcc \
    g++ \
    python3.10 \
    python3.10-venv \
    python3-pip \
    unixodbc \
    unixodbc-dev \
    libgssapi-krb5-2 \
    libpq-dev

# Agrega repos de Microsoft
RUN curl -sSL https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -o packages-microsoft-prod.deb \
    && dpkg -i packages-microsoft-prod.deb \
    && rm packages-microsoft-prod.deb

# Instala el driver ODBC
RUN apt-get update && ACCEPT_EULA=Y apt-get install -y \
    msodbcsql17 \
    mssql-tools \
    && echo 'export PATH="$PATH:/opt/mssql-tools/bin"' >> ~/.bashrc

# Ajustes Python y entorno
RUN ln -s /usr/bin/python3.10 /usr/bin/python && python -m pip install --upgrade pip

WORKDIR /app
COPY . /app

RUN pip install -r requirements.txt

EXPOSE 8002
CMD ["gunicorn", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8002", "main:app"]
