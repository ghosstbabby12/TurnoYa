"""TurnoYa – consola del operador.

Uso:
    python operador.py                                           # local
    python operador.py turnoya-xxxx.a.run.app:443 "Ventanilla 2"  # Cloud Run
"""

import sys

import grpc

import turnos_pb2
import turnos_pb2_grpc
from conexion import crear_canal


def main():
    direccion = sys.argv[1] if len(sys.argv) > 1 else "localhost:8080"
    ventanilla = sys.argv[2] if len(sys.argv) > 2 else "Ventanilla 1"

    with crear_canal(direccion) as canal:
        stub = turnos_pb2_grpc.TurnoServiceStub(canal)
        print(f"\n===== TurnoYa · Operador ({ventanilla}) =====")

        while True:
            try:
                opcion = input("\n[Enter] llamar siguiente | e = estado | s = salir > ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break

            try:
                if opcion == "":
                    r = stub.LlamarSiguiente(turnos_pb2.LlamarSiguienteRequest(ventanilla=ventanilla))
                    if r.hay_turno:
                        print(f"📢 {r.mensaje}. Quedan en espera: {r.en_espera}")
                    else:
                        print(f"😴 {r.mensaje}")
                elif opcion == "e":
                    e = stub.VerEstado(turnos_pb2.VerEstadoRequest())
                    print(f"📋 Turno actual: {e.turno_actual} | En espera: {e.en_espera} | Último entregado: {e.ultimo_entregado}")
                elif opcion == "s":
                    break
                else:
                    print("Opción no válida")
            except grpc.RpcError as e:
                print(f"❌ Error {e.code().name}: {e.details()}")

    print("Fin de la jornada.")


if __name__ == "__main__":
    main()
