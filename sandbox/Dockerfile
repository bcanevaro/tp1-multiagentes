# Imagen del sandbox donde corre el código que genera el Agente Analista.
#
#   docker build -t mas-tp-sandbox sandbox/
#
# Solo trae Python y las librerías que puede usar el código generado (BR-020). El contenedor se
# ejecuta sin red, con el sistema de archivos de solo lectura, límites de memoria/CPU/procesos
# y un usuario sin privilegios (ver services/sandbox/backends.py).
FROM python:3.11-slim

RUN pip install --no-cache-dir pandas==3.0.6 numpy==2.4.6 pyarrow==25.0.1 \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sandbox

USER 10001
WORKDIR /data
