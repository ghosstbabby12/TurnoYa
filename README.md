# TurnoYa – Sistema de turnos con gRPC desplegado en la nube

**Taller gRPC** · Camila Bastidas · Universidad Cooperativa de Colombia

TurnoYa gestiona los turnos de una sala de espera (una EPS, un banco o un restaurante):

- Los **clientes** piden un turno y ven **en tiempo real** cuántas personas faltan antes que ellos.
- Un **operador** llama al siguiente turno, y todos los clientes conectados se enteran al instante.

La comunicación entre clientes y servidor usa **gRPC**: Protocol Buffers sobre HTTP/2, con métodos *unary* y
*server streaming*. El servidor corre en **Azure Container Apps**.

## 🌐 Servidor en la nube

| | |
|---|---|
| **Dirección gRPC** | `turnoya.yellowocean-0382ffbd.mexicocentral.azurecontainerapps.io:443` |
| **Plataforma** | Azure Container Apps (suscripción Azure for Students) |
| **Región** | Mexico Central |
| **Transporte** | HTTP/2 de extremo a extremo, con TLS terminado por Azure |
| **Imagen** | `ghcr.io/ghosstbabby12/turnoya:2` (Python 3.11) |

> Esa dirección no es una página web: abierta en el navegador muestra un error.
> Para usarla hay que conectarse con un cliente gRPC, como `cliente.py` (ver [Probar contra la nube](#-probar-contra-la-nube)).

## Arquitectura

```
 ┌──────────────┐                                   ┌──────────────────────────────┐
 │ cliente.py   │── PedirTurno / VerEstado ────────▶│  Azure Container Apps        │
 │ (cliente A)  │◀═ SeguirTurno (stream) ══════════ │  ┌────────────────────────┐  │
 └──────────────┘                                   │  │ server.py (gRPC)       │  │
 ┌──────────────┐        gRPC + TLS (puerto 443)    │  │  TurnoService          │  │
 │ cliente.py   │◀═ SeguirTurno (stream) ══════════ │  │  estado en memoria     │  │
 │ (cliente B)  │                                   │  │  threading.Condition   │  │
 └──────────────┘                                   │  └────────────────────────┘  │
 ┌──────────────┐                                   │   ingress HTTP/2 → :8080     │
 │ operador.py  │── LlamarSiguiente ───────────────▶│                              │
 └──────────────┘                                   └──────────────────────────────┘
```

Cada vez que el operador llama un turno, el servidor despierta a todos los streams abiertos y cada cliente
recibe su actualización sin tener que preguntar.

## Servicio gRPC (`turnos.proto`)

| Método | Tipo | Entrada → Salida | Descripción |
|---|---|---|---|
| `PedirTurno` | unary | `nombre` → `numero`, `personas_delante` | Entrega el siguiente número de turno. |
| `LlamarSiguiente` | unary | `ventanilla` → turno llamado, nombre, `en_espera` | El operador avanza la fila. |
| `SeguirTurno` | **server streaming** | `numero` → `stream ActualizacionTurno` | Envía una actualización cada vez que la fila avanza y termina con **"¡Es tu turno!"**. |
| `VerEstado` | unary | — → `turno_actual`, `en_espera`, `ultimo_entregado` | Muestra el estado de la fila en ese momento. |

Errores gRPC que devuelve el servidor:

| Código | Cuándo |
|---|---|
| `INVALID_ARGUMENT` | Se pide turno con el nombre vacío. |
| `NOT_FOUND` | Se intenta seguir un turno que no existe. |
| `FAILED_PRECONDITION` | Se intenta seguir un turno que ya fue llamado. |

### Concurrencia

- El servidor usa un `ThreadPoolExecutor` y atiende cada llamada en su propio hilo.
- El estado de la fila está protegido por un `threading.Condition`.
- `LlamarSiguiente` actualiza el turno actual y hace `notify_all()`.
- Cada `SeguirTurno` espera con `wait_for()` a que el turno cambie y envía la actualización **fuera del lock**, para no
  bloquear a los demás clientes.
- Cada 5 segundos, la espera revisa `context.is_active()` para liberar el hilo si el cliente se desconectó.

## Estructura del proyecto

```
TurnoYa/
├── turnos.proto        # Contrato del servicio gRPC
├── server.py           # Servidor gRPC (lee el puerto de la variable PORT, 8080 por defecto)
├── cliente.py          # Consola del cliente: pedir turno, seguir mi turno, ver estado
├── operador.py         # Consola del operador: llamar siguiente, ver estado
├── conexion.py         # Canal TLS si el puerto es 443; sin TLS en local
├── requirements.txt    # grpcio, grpcio-tools
├── Dockerfile          # Imagen python:3.11-slim; compila el .proto al construir
└── turnos_pb2*.py      # Generados con grpc_tools.protoc (no se versionan)
```

## Instalación

Requisitos: Python 3.11 o superior.

```bash
git clone https://github.com/ghosstbabby12/TurnoYa.git
cd TurnoYa
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. turnos.proto
```

El último comando genera `turnos_pb2.py` y `turnos_pb2_grpc.py`. Repítelo si cambias `turnos.proto`.

## ☁️ Probar contra la nube

```bash
# Terminal 1 y 2: clientes
python cliente.py turnoya.yellowocean-0382ffbd.mexicocentral.azurecontainerapps.io:443

# Terminal 3: operador
python operador.py turnoya.yellowocean-0382ffbd.mexicocentral.azurecontainerapps.io:443 "Ventanilla 1"
```

1. En cada cliente, elige `1` (pedir turno) y luego `2` (seguir mi turno).
2. En el operador, pulsa **Enter** para llamar al siguiente.
3. Los clientes se actualizan al instante hasta recibir `🔔 ¡Es tu turno!`.

## 💻 Probar en local

```bash
python server.py                     # Terminal 1: servidor en localhost:8080
python cliente.py                    # Terminales 2 y 3
python operador.py                   # Terminal 4
```

También con Docker:

```bash
docker build -t turnoya .
docker run -p 8080:8080 turnoya
```

## 🚀 Despliegue en Azure Container Apps

Pasos con los que se desplegó este proyecto, usando una suscripción **Azure for Students** (sin tarjeta de crédito).

### 1. Publicar la imagen en GitHub Container Registry

Hace falta un token *classic* de GitHub con el permiso `write:packages`. Se escribe cuando el login pide la contraseña;
nunca se guarda en el repositorio.

```bash
docker login ghcr.io -u <usuario-github>
docker buildx build --platform linux/amd64 -t ghcr.io/<usuario-github>/turnoya:1 --push .
```

`--platform linux/amd64` es necesario al construir desde un Mac con Apple Silicon.

### 2. Preparar Azure

```bash
az login
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az group create --name turnoya-rg --location eastus
az containerapp env create --name turnoya-env --resource-group turnoya-rg \
  --location mexicocentral --environment-mode WorkloadProfiles
```

### 3. Desplegar

```bash
read -s GH_TOKEN      # pegar el token sin que se muestre en pantalla
az containerapp create --name turnoya --resource-group turnoya-rg --environment turnoya-env \
  --image ghcr.io/<usuario-github>/turnoya:1 \
  --registry-server ghcr.io --registry-username <usuario-github> --registry-password "$GH_TOKEN" \
  --target-port 8080 --ingress external --transport http2 \
  --min-replicas 1 --max-replicas 1 --cpu 0.25 --memory 0.5Gi
```

Qué hace cada opción importante:

| Opción | Por qué |
|---|---|
| `--transport http2` | gRPC necesita HTTP/2 de extremo a extremo. Con `auto` o `http` las llamadas fallan con `UNAVAILABLE`. |
| `--environment-mode WorkloadProfiles` | Los entornos *Express*, el modo por defecto en versiones recientes de la CLI, no soportan HTTP/2. |
| `--location mexicocentral` | Azure for Students solo permite ciertas regiones (`az policy assignment list` las muestra). |
| `--max-replicas 1` | El estado está en memoria. Con varias réplicas, cada una tendría su propia fila. |
| `--min-replicas 1` | Evita que la réplica se apague por inactividad y se pierda la fila. |

### Operación

```bash
az containerapp logs show -n turnoya -g turnoya-rg --follow --format text    # logs en vivo
az containerapp revision list -n turnoya -g turnoya-rg -o table              # revisiones
az containerapp update -n turnoya -g turnoya-rg --min-replicas 0             # ahorrar crédito
az group delete --name turnoya-rg --yes                                      # borrar todo
```

### Alternativa: Google Cloud Run

El mismo contenedor funciona en Cloud Run, que requiere una cuenta de facturación:

```bash
gcloud run deploy turnoya --source . --region us-central1 --use-http2 \
  --allow-unauthenticated --max-instances 1 --timeout 3600
```

## Limitaciones

- **Estado en memoria.** Si el contenedor se reinicia, la fila vuelve a cero. Es intencional: el taller pide que no haya
  base de datos.
- **Una sola réplica.** Escalar horizontalmente exigiría un estado compartido, por ejemplo Redis.
- **Sin autenticación.** Cualquiera con la dirección puede llamar al siguiente turno.
- **Corte de streams a los 240 s.** Azure Container Apps cierra cualquier petición a los 4 minutos, incluidos los streams.
  `cliente.py` lo detecta (errores `INTERNAL`/`UNAVAILABLE`) y vuelve a llamar a `SeguirTurno` automáticamente, sin
  repetir mensajes. Se probó siguiendo un turno durante más de 4 minutos.

## Guion de demo (5 pasos)

1. Mostrar `turnos.proto` y la palabra `stream` en `SeguirTurno`: un request, muchas respuestas.
2. Mostrar el portal de Azure: app *En ejecución*, región Mexico Central, ingress con transporte **HTTP/2**.
3. Abrir dos clientes contra la nube, pedir turno en ambos y activar *Seguir mi turno*.
4. En el operador, pulsar Enter despacio: las dos pantallas se actualizan a la vez hasta "¡Es tu turno!".
5. Mostrar los logs del servidor en vivo (*Supervisión → Flujo de registro*) y cerrar con unary vs. server streaming.
