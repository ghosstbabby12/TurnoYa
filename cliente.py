"""TurnoYa – cliente de consola.

Uso:
    python cliente.py                              # local: localhost:8080
    python cliente.py turnoya-xxxx.a.run.app:443   # Cloud Run (TLS)
"""

import sys

import grpc

import turnos_pb2
import turnos_pb2_grpc
from conexion import crear_canal


def pedir_turno(stub):
    nombre = input("Tu nombre: ").strip()
    resp = stub.PedirTurno(turnos_pb2.PedirTurnoRequest(nombre=nombre))
    print(f"\n🎫 {resp.mensaje}")
    return resp.numero


def seguir_turno(stub, numero):
    if not numero:
        texto = input("Número de turno a seguir: ").strip()
        if not texto.isdigit():
            print("Número inválido")
            return
        numero = int(texto)

    print(f"\n👀 Siguiendo el turno {numero} en tiempo real (Ctrl+C para volver al menú)\n")
    stream = stub.SeguirTurno(turnos_pb2.SeguirTurnoRequest(numero=numero))
    try:
        for act in stream:
            if act.es_tu_turno:
                print(f"\n🔔 {act.mensaje}\a")
            else:
                print(f"   ⏳ {act.mensaje}")
    except KeyboardInterrupt:
        stream.cancel()
        print("\nDejaste de seguir el turno.")


def ver_estado(stub):
    e = stub.VerEstado(turnos_pb2.VerEstadoRequest())
    actual = e.turno_actual or "ninguno"
    print(f"\n📋 Turno actual: {actual} | En espera: {e.en_espera} | Último entregado: {e.ultimo_entregado}")


def main():
    direccion = sys.argv[1] if len(sys.argv) > 1 else "localhost:8080"
    with crear_canal(direccion) as canal:
        stub = turnos_pb2_grpc.TurnoServiceStub(canal)
        mi_turno = 0

        while True:
            etiqueta = f" (#{mi_turno})" if mi_turno else ""
            print("\n===== TurnoYa =====")
            print("1. Pedir turno")
            print(f"2. Seguir mi turno{etiqueta}")
            print("3. Ver estado")
            print("0. Salir")
            try:
                opcion = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            try:
                if opcion == "1":
                    mi_turno = pedir_turno(stub)
                elif opcion == "2":
                    seguir_turno(stub, mi_turno)
                elif opcion == "3":
                    ver_estado(stub)
                elif opcion == "0":
                    break
                else:
                    print("Opción no válida")
            except grpc.RpcError as e:
                print(f"\n❌ Error {e.code().name}: {e.details()}")

    print("¡Hasta pronto!")


if __name__ == "__main__":
    main()
