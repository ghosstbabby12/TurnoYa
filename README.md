# TurnoYa – Sistema de turnos con gRPC en Google Cloud Run

Los clientes piden turno y ven **en tiempo real** (server streaming) cuántas personas faltan;
un operador llama al siguiente turno.

## 1. Estructura

```
TurnoYa/
├── turnos.proto        # Contrato del servicio gRPC (4 métodos)
├── server.py           # Servidor: estado en memoria + threading.Condition
├── conexion.py         # Crea el canal: TLS si el puerto es 443, inseguro en local
├── cliente.py          # Consola del cliente (pedir / seguir / estado)
├── operador.py         # Consola del operador (llamar siguiente / estado)
├── requirements.txt    # grpcio + grpcio-tools
├── Dockerfile          # Imagen para Cloud Run (genera los stubs al construir)
├── .dockerignore / .gitignore
└── turnos_pb2.py, turnos_pb2_grpc.py   # GENERADOS (no se suben a git)
```

| Archivo | Qué hace |
|---|---|
| `turnos.proto` | Define `TurnoService`: `PedirTurno`, `LlamarSiguiente`, `VerEstado` (unary) y `SeguirTurno` (server streaming). |
| `server.py` | Guarda la fila en memoria. Un `ThreadPoolExecutor` atiende cada llamada en un hilo. `LlamarSiguiente` hace `notify_all()` sobre un `threading.Condition` y cada `SeguirTurno` despierta y envía su actualización (fuera del lock). Lee el puerto de `PORT` (8080 por defecto). |
| `cliente.py` / `operador.py` | Clientes de consola. Reciben la dirección como argumento. |
| `Dockerfile` | `python:3.11-slim`, instala dependencias, compila el `.proto` y arranca `server.py`. |

## 2. Generar el código a partir del `.proto`

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. turnos.proto
```

Repite el último comando cada vez que modifiques `turnos.proto`.
(En Docker no hace falta: el `Dockerfile` ya lo ejecuta.)

## 3. Probar en local (4 terminales)

En cada terminal: `cd TurnoYa && source .venv/bin/activate`

| Terminal | Comando | Qué hacer |
|---|---|---|
| 1 – Servidor | `python server.py` | Deja corriendo; verás los logs. |
| 2 – Cliente A | `python cliente.py` | `1` → nombre "Ana" → `2` (seguir mi turno) |
| 3 – Cliente B | `python cliente.py` | `1` → nombre "Luis" → `2` (seguir mi turno) |
| 4 – Operador | `python operador.py` | Pulsa **Enter** para llamar al siguiente |

Cada Enter del operador actualiza al instante las terminales 2 y 3, hasta que cada una
recibe `🔔 ¡Es tu turno!`. (Opcional: probar la imagen con
`docker build -t turnoya . && docker run -p 8080:8080 turnoya`.)

## 4. Desplegar en Google Cloud Run desde cero

### 4.1 Instalar gcloud
- **macOS:** `brew install --cask google-cloud-sdk`
- **Windows / Linux:** instalador en https://cloud.google.com/sdk/docs/install

```bash
gcloud init                      # inicia sesión con tu cuenta de Google
```

### 4.2 Crear proyecto y vincular facturación
```bash
export PROJECT_ID=turnoya-$RANDOM      # debe ser único a nivel mundial
gcloud projects create $PROJECT_ID
gcloud config set project $PROJECT_ID

gcloud billing accounts list           # copia el ACCOUNT_ID
gcloud billing projects link $PROJECT_ID --billing-account=XXXXXX-XXXXXX-XXXXXX
```
> Cloud Run exige facturación activa (la capa gratuita cubre de sobra una demo).
> Con créditos educativos, vincula la cuenta de facturación de los créditos.

### 4.3 Habilitar APIs
```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

### 4.4 Desplegar (desde la carpeta `TurnoYa`)
```bash
gcloud run deploy turnoya \
  --source . \
  --region us-central1 \
  --use-http2 \
  --allow-unauthenticated \
  --max-instances 1 \
  --timeout 3600
```
- `--source .` construye la imagen con el `Dockerfile` usando Cloud Build (no necesitas Docker local).
  Si pregunta por crear un repositorio de Artifact Registry, responde **Y**.
- `--use-http2`: gRPC necesita HTTP/2 de extremo a extremo (Cloud Run envía h2c al contenedor).
- `--max-instances 1`: **importante**, el estado está en memoria; con varias instancias cada una tendría su propia fila.
- `--timeout 3600`: un stream de `SeguirTurno` puede durar hasta 60 min (por defecto se cortaría a los 5).

Al terminar verás algo como `Service URL: https://turnoya-abc123-uc.a.run.app`.

### 4.5 Conectarse a la nube
```bash
python cliente.py turnoya-abc123-uc.a.run.app:443
python operador.py turnoya-abc123-uc.a.run.app:443 "Ventanilla 2"
```
(También acepta la URL completa `https://...`; sin puerto asume 443 con TLS.)

### Problemas frecuentes
- **Error de permisos en Cloud Build al desplegar (proyectos nuevos):**
  ```bash
  PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member=serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com \
    --role=roles/cloudbuild.builds.builder
  ```
  y vuelve a ejecutar el `gcloud run deploy`.
- **La fila "se reinicia":** Cloud Run apaga la instancia tras unos minutos sin tráfico y el estado
  en memoria se pierde. Para la clase puedes añadir `--min-instances 1` (tiene un costo pequeño
  mientras esté activo) y quitarlo después.
- **Logs:** `gcloud run services logs read turnoya --region us-central1`
- **Borrar todo al final:** `gcloud run services delete turnoya --region us-central1`

## 5. Guion de la demo en clase (5 pasos)

1. **Contrato.** Muestra `turnos.proto` y señala la palabra `stream` en `SeguirTurno`:
   "un request, muchas respuestas". Muestra el comando `gcloud run deploy ... --use-http2` y la URL del servicio.
2. **Dos clientes en la nube.** Abre dos terminales (o pide a dos compañeros que se conecten
   desde su portátil): `python cliente.py <url>:443` → `1` (pedir turno). Ejecuta `3` (ver estado): ya hay 2 en espera.
3. **Activar el streaming.** En ambos clientes, opción `2`. Se quedan "escuchando" con
   `⏳ Aún no se ha llamado a nadie. Personas delante de ti: …`.
4. **El operador llama.** En una tercera terminal, `python operador.py <url>:443` y pulsa Enter
   despacio: el público ve cómo **las dos pantallas se actualizan al mismo tiempo** sin que los
   clientes hagan nada, hasta `🔔 ¡Es tu turno! Acércate a Ventanilla 1`.
5. **Cierre.** Pulsa Enter otra vez → `😴 No hay nadie en espera`. Muestra los logs
   (`gcloud run services logs read turnoya --region us-central1`) y resume: gRPC + Protobuf,
   unary vs. server streaming, HTTP/2 en Cloud Run y por qué `--max-instances 1` con estado en memoria.
