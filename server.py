"""TurnoYa – servidor gRPC de turnos (estado en memoria).

Concurrencia: un ThreadPoolExecutor atiende cada llamada en su propio hilo.
El estado de la fila está protegido por un threading.Condition:
  - las escrituras (PedirTurno, LlamarSiguiente) toman el lock;
  - LlamarSiguiente hace notify_all() para despertar a todos los SeguirTurno;
  - cada SeguirTurno espera (wait_for) a que cambie el turno actual y envía
    la actualización FUERA del lock, para no bloquear a los demás.
"""

import logging
import os
import signal
import threading
from concurrent import futures

import grpc

import turnos_pb2
import turnos_pb2_grpc

log = logging.getLogger("turnoya")

# Cada cuántos segundos un stream revisa si su cliente sigue conectado.
REVISAR_CONEXION_SEG = 5
# Hilos del servidor: cada cliente que sigue su turno ocupa uno mientras espera.
MAX_HILOS = 100


class TurnoService(turnos_pb2_grpc.TurnoServiceServicer):
    def __init__(self):
        self._cond = threading.Condition()  # lock + aviso a quienes siguen su turno
        self._ultimo_entregado = 0          # último número repartido
        self._turno_actual = 0              # último número llamado (0 = nadie aún)
        self._nombres = {}                  # numero -> nombre del cliente
        self._ventanillas = {}              # numero -> ventanilla que lo llamó

    def PedirTurno(self, request, context):
        nombre = request.nombre.strip()
        if not nombre:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "El nombre es obligatorio")

        with self._cond:
            self._ultimo_entregado += 1
            numero = self._ultimo_entregado
            self._nombres[numero] = nombre
            delante = numero - self._turno_actual - 1

        log.info("Turno %d entregado a %s (%d delante)", numero, nombre, delante)
        return turnos_pb2.PedirTurnoResponse(
            numero=numero,
            personas_delante=delante,
            mensaje=f"Hola {nombre}, tu turno es el {numero}. Personas delante: {delante}",
        )

    def LlamarSiguiente(self, request, context):
        ventanilla = request.ventanilla.strip() or "Ventanilla 1"

        with self._cond:
            if self._turno_actual >= self._ultimo_entregado:
                return turnos_pb2.LlamarSiguienteResponse(
                    hay_turno=False, mensaje="No hay nadie en espera"
                )
            self._turno_actual += 1
            numero = self._turno_actual
            nombre = self._nombres.get(numero, "")
            self._ventanillas[numero] = ventanilla
            en_espera = self._ultimo_entregado - numero
            self._cond.notify_all()  # despierta a todos los SeguirTurno

        log.info("Llamado turno %d (%s) a %s. En espera: %d", numero, nombre, ventanilla, en_espera)
        return turnos_pb2.LlamarSiguienteResponse(
            hay_turno=True,
            numero=numero,
            nombre=nombre,
            en_espera=en_espera,
            mensaje=f"Turno {numero} ({nombre}), acérquese a {ventanilla}",
        )

    def SeguirTurno(self, request, context):
        numero = request.numero
        with self._cond:
            if not 0 < numero <= self._ultimo_entregado:
                context.abort(grpc.StatusCode.NOT_FOUND, f"El turno {numero} no existe")
            if numero < self._turno_actual:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION, f"El turno {numero} ya fue llamado"
                )

        log.info("Cliente siguiendo el turno %d", numero)
        visto = -1  # último turno_actual enviado a este cliente
        while context.is_active():
            with self._cond:
                # Duerme hasta que la fila avance (o hasta el timeout para
                # comprobar que el cliente no se haya desconectado).
                self._cond.wait_for(
                    lambda: self._turno_actual != visto, timeout=REVISAR_CONEXION_SEG
                )
                actual = self._turno_actual
                ventanilla = self._ventanillas.get(numero, "")

            if actual == visto:
                continue  # timeout sin cambios
            visto = actual

            if actual >= numero:
                yield turnos_pb2.ActualizacionTurno(
                    numero=numero,
                    turno_actual=actual,
                    personas_delante=0,
                    es_tu_turno=True,
                    mensaje=f"¡Es tu turno! Acércate a {ventanilla}",
                )
                return

            delante = numero - actual - 1
            atendiendo = f"Atendiendo el turno {actual}" if actual else "Aún no se ha llamado a nadie"
            yield turnos_pb2.ActualizacionTurno(
                numero=numero,
                turno_actual=actual,
                personas_delante=delante,
                es_tu_turno=False,
                mensaje=f"{atendiendo}. Personas delante de ti: {delante}",
            )

        log.info("El cliente del turno %d dejó de seguirlo", numero)

    def VerEstado(self, request, context):
        with self._cond:
            return turnos_pb2.EstadoResponse(
                turno_actual=self._turno_actual,
                en_espera=self._ultimo_entregado - self._turno_actual,
                ultimo_entregado=self._ultimo_entregado,
            )


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    port = os.environ.get("PORT", "8080")

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_HILOS))
    turnos_pb2_grpc.add_TurnoServiceServicer_to_server(TurnoService(), server)
    server.add_insecure_port(f"[::]:{port}")  # Cloud Run pone TLS por delante
    server.start()
    log.info("TurnoYa escuchando en el puerto %s", port)

    # Cloud Run envía SIGTERM antes de apagar el contenedor.
    def apagar(signum, frame):
        log.info("Apagando servidor...")
        server.stop(grace=5)

    signal.signal(signal.SIGTERM, apagar)
    signal.signal(signal.SIGINT, apagar)
    server.wait_for_termination()


if __name__ == "__main__":
    main()
