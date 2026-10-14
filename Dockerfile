FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY turnos.proto server.py ./
# Genera turnos_pb2.py y turnos_pb2_grpc.py dentro de la imagen
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. turnos.proto

# No ejecutar el servidor como root
RUN useradd --create-home turnoya
USER turnoya

EXPOSE 8080
CMD ["python", "server.py"]
