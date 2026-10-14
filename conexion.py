"""Crea el canal gRPC: TLS si el puerto es 443 (Cloud Run), inseguro en otro caso (local)."""

import grpc


def crear_canal(direccion: str) -> grpc.Channel:
    # Acepta también la URL tal como la muestra Cloud Run: https://turnoya-xxxx.a.run.app
    direccion = direccion.removeprefix("https://").rstrip("/")
    if ":" not in direccion:
        direccion += ":443"

    if direccion.rsplit(":", 1)[1] == "443":
        print(f"Conectando a {direccion} (TLS)")
        return grpc.secure_channel(direccion, grpc.ssl_channel_credentials())
    print(f"Conectando a {direccion} (sin TLS)")
    return grpc.insecure_channel(direccion)
