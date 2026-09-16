# Kitok v1

Pipeline local para:

```text
content_queue.json
      ↓
Python en WSL/Linux
      ↓ HTTP
MoneyPrinterTurbo en Windows
      ↓
MP4
      ↓
ffprobe
      ↓
READY_DIR
      ↓
Drive/FolderSync
      ↓
móvil
```

## Qué incluye

- Cola JSON de contenidos.
- Preset global para MPT.
- `POST /api/v1/videos`.
- Recuperación mediante `GET /api/v1/tasks/{task_id}`.
- Estado persistente e idempotencia local.
- Descarga del MP4 final.
- Validación con ffprobe.
- Copia a carpeta lista para móvil.
- Sidecar JSON con caption/hora.
- `publish_plan.txt` y `publish_plan.json`.
- CLI y tests.
- Publicación opcional mediante Cloudinary + Buffer, desactivada por defecto.

## API MPT verificada contra el repo actual

Endpoints:

```text
POST /api/v1/videos
GET  /api/v1/tasks/{task_id}
GET  /api/v1/tasks
```

Estados actuales:

```text
-1 failed
 1 complete
 4 processing
```

El request de vídeo usa `TaskVideoRequest(VideoParams)`. El preset incluido usa campos reales del schema actual como:

```text
video_subject
video_script
video_terms
video_aspect
video_fit_mode
video_concat_mode
video_clip_duration
match_materials_to_script
video_source
voice_name
voice_rate
bgm_type
subtitle_display_mode
subtitle_animation
font_size
stroke_width
```

Tu instalación concreta es **MoneyPrinterTurbo Portable 1.3.7**, así que Codex debe comparar el OpenAPI de ESA instalación antes de lanzar toda la cola.

---

## 1. Copiar en WSL

```bash
mkdir -p ~/projects
cd ~/projects
unzip /ruta/kitok_v1.zip
cd kitok_v1
```

El código debe vivir preferiblemente en el filesystem Linux (`~/projects/...`), no dentro de `/mnt/c`.

MoneyPrinterTurbo se queda en Windows.

## 2. Dependencias WSL

```bash
sudo apt update
sudo apt install -y python3 python3-venv ffmpeg
```

Después:

```bash
bash scripts/bootstrap_wsl.sh
source .venv/bin/activate
```

## 3. Configuración

```bash
cp .env.example .env
```

Inicialmente:

```env
MPT_BASE_URL=http://localhost:8080
READY_DIR=./outputs/ready-phone
```

## 4. Arrancar la API de MoneyPrinterTurbo en Windows

La WebUI y la API no son lo mismo.

El repo oficial arranca la API desde la raíz de MPT con:

```text
python main.py
```

o:

```text
uv run python main.py
```

y Swagger está en:

```text
http://127.0.0.1:8080/docs
```

Con tu paquete portable usa su Python/entorno incluido.

## 5. WSL → Windows

Prueba desde WSL:

```bash
curl http://localhost:8080/docs
```

Si no funciona:

```bash
bash scripts/find_windows_host.sh
```

y prueba la IP devuelta.

Si MPT necesita escuchar fuera de localhost, en `config.toml`:

```toml
listen_host = "0.0.0.0"
listen_port = 8080
```

En ese caso usa `api_key` y NO expongas el puerto 8080 a Internet.

Luego:

```bash
python main.py --check-mpt
```

## 6. Primero dry-run

```bash
python main.py --dry-run
pytest -q
```

## 7. Generar UN vídeo

```bash
python main.py --id voz_grabada_001
```

No lances toda la cola antes de comprobar visualmente ese MP4.

## 8. Generar pendientes

```bash
python main.py
```

## 9. Estado

```bash
python main.py --status
```

Estados locales:

```text
pending
submitted
generating
generated
ready
failed
```

Si Kitok se cierra durante un render, conserva `mpt_task_id`. Al volver a ejecutar, consulta esa tarea antes de crear otra.

El POST de creación NO se reintenta automáticamente porque MPT no proporciona una idempotency key de cliente; tras un timeout no podemos saber con certeza si el servidor ya aceptó la tarea.

## 10. Reintentar fallidos

```bash
python main.py --retry-failed
```

o solo uno:

```bash
python main.py --id mi_id --retry-failed
```

### Regenerar todos los vídeos listos

```bash
python main.py --regenerate-all-ready --dry-run
python main.py --regenerate-all-ready
```

El dry-run enumera los elementos que se regenerarían sin crear tareas MPT ni escribir archivos o estado. La ejecución usa el preset MPT actual, crea tareas nuevas de forma secuencial y valida cada descarga antes de sustituir los MP4 en `outputs/generated`, `outputs/ready` y `READY_DIR`. Omite los elementos que no estén en `ready` y los que tengan metadatos de Cloudinary o Buffer; muestra el motivo de cada omisión y un resumen de regenerados, fallidos y omitidos. Un fallo no detiene los demás elementos. No sube archivos a Cloudinary ni crea publicaciones en Buffer.

## 11. Preset

`presets/mpt_default.json` viene preparado para:

- Pexels.
- 9:16.
- cover.
- secuencial.
- match visuals to script.
- clip máximo 2 s.
- 1 vídeo.
- Edge TTS `es-ES-AlvaroNeural`.
- velocidad 1.0.
- sin BGM.
- word-by-word.
- spring pop.
- `MicrosoftYaHeiBold.ttc`.
- tamaño 85.
- blanco + outline negro.
- outline 3.

`custom_position=70.0` es un punto a revisar con tu configuración visual exacta.

## 12. Cola

Ejemplo:

```json
[
  {
    "id": "voz_grabada_001",
    "subject": "Por qué tu voz grabada te suena tan rara",
    "script": "¿Por qué tu propia voz grabada...",
    "keywords": ["voice recording", "microphone"],
    "caption": "Tu voz no suena como crees 🤯",
    "publish_at": "2026-09-16T13:00:00+02:00"
  }
]
```

`publish_at` exige zona horaria.

## 13. Nombres finales

```text
2026-09-16_13-00__voz_grabada_001.mp4
```

Así en el móvil sabes qué toca publicar.

## 14. Móvil

Primero prueba con:

```env
READY_DIR=./outputs/ready-phone
```

Cuando funcione, apunta `READY_DIR` a la carpeta de Drive montada en WSL, por ejemplo:

```env
READY_DIR=/mnt/g/My Drive/PasaPorAlgo/ready
```

La ruta concreta depende de tu Drive de Windows.

FolderSync Android:

```text
Remote: Google Drive/PasaPorAlgo/ready
Local: Internal Storage/Movies/PasaPorAlgo
Mode: remote -> local
```

Cada 15 min es suficiente.

## 15. Publish plan

Kitok genera:

```text
publish_plan.txt
publish_plan.json
```

con hora, vídeo y caption de los elementos `ready`.

## 16. Comandos

```bash
python main.py --dry-run
python main.py --check-mpt
python main.py --status
python main.py --id voz_grabada_001
python main.py
python main.py --retry-failed
python main.py --plan
```

## 17. Qué NO hace v1

A propósito todavía no:

- TikTok API.
- YouTube API.
- Instagram API.
- Selenium.
- generación de ideas con LLM.
- analytics.
- cron.
- concurrencia.

Objetivo de v1:

```text
pegar muchos guiones
→ un comando
→ muchos MP4
→ aparecen solos en el móvil
```

La capa opcional siguiente añade programación mediante Buffer sin cambiar la generación.

## 18. Publicación opcional: Cloudinary → Buffer

La generación conserva el flujo anterior y nunca publica, aunque
`PUBLISH_ENABLED=true`. La publicación se ejecuta únicamente con sus comandos
específicos. No se utilizan APIs directas de las redes ni automatización de navegador.

```text
MP4 ready → Cloudinary (una subida) → URL HTTPS estable
          → Buffer → TikTok / Instagram Reel / YouTube Short
```

Instala las dependencias actualizadas:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

Copia las nuevas variables de `.env.example` a tu `.env` sin sobrescribir la
configuración de MPT/Drive. Nunca subas `.env` al repositorio:

```dotenv
PUBLISH_ENABLED=false
FIXED_HASHTAGS="#curiosidades #datoscuriosos"
BUFFER_API_KEY=
BUFFER_ORGANIZATION_ID=
BUFFER_TIKTOK_CHANNEL_ID=
BUFFER_INSTAGRAM_CHANNEL_ID=
BUFFER_YOUTUBE_CHANNEL_ID=
BUFFER_MAX_SCHEDULED_PER_CHANNEL=9
BUFFER_REQUEST_TIMEOUT_SECONDS=30
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

### Comprobaciones y vista previa

```bash
python main.py --buffer-channels
python main.py --buffer-check
python main.py --publish-dry-run
python main.py --publish-dry-run --id estomago_no_se_digiere_001
python main.py --publish-id estomago_no_se_digiere_001 --publish-dry-run
```

`--buffer-check` solo consulta organizaciones y canales, incluso con publicación
activada. No carga MPT ni necesita una cola/preset válido. `--buffer-channels`
muestra IDs para resolver canales ambiguos. Si hay varias organizaciones, configura
`BUFFER_ORGANIZATION_ID`; si hay varios canales del mismo servicio, configura su
ID explícito. Un ID debe pertenecer al servicio y organización seleccionados.
Los canales ausentes, desconectados, bloqueados o pausados no se programan.

`--publish-dry-run` muestra ID, plataforma, `dueAt` UTC, caption, título de YouTube,
ruta del vídeo y campos de creación. No sube archivos, modifica estado ni crea
posts. Con credenciales consulta la ocupación real; sin ellas muestra una
**estimación offline** con el estado local y canales sin verificar (`channelId`
será `null` si no está configurado). El resultado no garantiza disponibilidad futura.

### Subtítulos antes de la primera prueba

El preset actual tiene **`subtitle_enabled: false`**. El MP4 destinado a publicación
automática debe llevar sus propios subtítulos incrustados. Comprueba visualmente
el vídeo final y prepara sus subtítulos mediante tu flujo de generación/edición
antes de subirlo. ffprobe valida propiedades técnicas, pero no puede demostrar
que haya texto incrustado en los fotogramas. Esta capa no cambia el preset, no
invoca subtítulos nativos de las plataformas y no recodifica vídeos.

### Primera prueba real: UN vídeo, tras confirmación

La implementación y los tests no publican nada. Tras configurar credenciales,
verificar subtítulos y aprobar la vista previa, la prueba se limita a un ID:

```bash
# Solo después de confirmar la prueba real:
PUBLISH_ENABLED=true python main.py --publish-id estomago_no_se_digiere_001
```

`--publish-id` hace una prevalidación completa, imprime un resumen antes de escribir
y opera exclusivamente sobre ese ID. Puede crear hasta **tres posts**, uno para
TikTok, Instagram y YouTube,
compartiendo una única subida del vídeo. Respeta el límite y mantiene la fecha de
la cola; nunca transforma una fecha vencida en publicación inmediata. Si la fecha
de ese ejemplo ha pasado, elige primero una fecha futura y vuelve a revisar la
vista previa. Su combinación con `--publish-dry-run` no sube ni programa nada.

### Mantenimiento de Buffer Free

```bash
python main.py --sync-buffer-status
# Los siguientes requieren PUBLISH_ENABLED=true:
python main.py --publish-ready
python main.py --buffer-maintain
```

- `--sync-buffer-status`: consulta y guarda estados de posts conocidos y reconcilia
  creaciones desconocidas; no crea nada y funciona con publicación desactivada.
- `--publish-ready`: cuenta la cola remota y programa los vídeos `ready` futuros
  más tempranos hasta el objetivo por canal.
- `--buffer-maintain`: sincroniza, cuenta y rellena, con resumen de creaciones,
  sincronizaciones, elementos aplazados y problemas que requieren atención.
- `--id` limita selección para publicar o previsualizar; la sincronización revisa
  todos los posts conocidos para mantener una visión coherente de la cuenta.

El objetivo es **9 por canal**, configurable entre 1 y 9, dejando una plaza del
límite Free de 10. Los posts existentes de otras herramientas/personas también
cuentan. Los estados `sending` y los posts locales aún no visibles remotamente
reservan capacidad por prudencia. La paginación recorre todos los resultados;
una consulta incompleta nunca se interpreta como una cola vacía. Kitok serializa
sus mantenimientos en WSL/Linux; otro programa o usuario de Buffer puede cambiar
la cola después de leerla, por lo que conviene coordinar quién la rellena.

No hay sondeo continuo ni cron instalado. Una ejecución manual o unas pocas al
día bastan para esta cola. Buffer Free ofrece 3 canales, 1 API key y 3000 peticiones
en 30 días; también aplica ventanas más cortas. Las consultas reintentan con
espera exponencial acotada y respetan `Retry-After`. Una limitación durante creación
termina el lote y guarda un plazo de reintento; **no reenvía la mutación**.
Los detalles vigentes están en [límites de Buffer](https://developers.buffer.com/guides/api-limits.html)
y [planes y acceso API](https://buffer.com/api).

### Texto, validación y divulgación de IA

Se usa exclusivamente `caption` y `subject` de la cola, sin generar texto nuevo.
Los hashtags fijos se añaden centralmente, evitando repetir etiquetas existentes.
TikTok exige que el resultado tenga ≤150 caracteres; un título de YouTube de más
de 100 caracteres se rechaza sin truncarlo. Instagram valida también el límite
final de 2200 caracteres. YouTube recibe la descripción en `text` y el título
en `metadata.youtube.title`.

Todas las creaciones llevan `aiAssisted: true` y `isAiGenerated: true` en los
metadatos del servicio. Instagram usa `type: reel` y `shouldShareToFeed: true`.
YouTube usa categoría `27`, `madeForKids: false`, `privacy: public` y
`notifySubscribers: true`. La programación usa `automatic`, `customScheduled`,
`needsApproval: false` y una fecha convertida a UTC: `19:00+02:00` → `17:00Z`.
La cola rechaza fechas sin zona horaria.

ffprobe comprueba MP4 vertical con audio y duración válida; para TikTok exige
≥3 segundos, ≤1 GB, al menos 360×360 y 23–60 FPS; para Shorts exige 9:16 y ≤180
segundos. Se usa `ready_path` o la copia de `outputs/ready`, sin usar archivos
incompletos de generación. Los problemas no cambian el estado de generación.

### Estado, recuperación y medios

El formato existente mantiene `status: ready`, `mpt_task_id` y los demás campos.
Se añade `publishing.cloudinary` con `public_id`, `url`/`secure_url`, hash y estado,
y `publishing.buffer.<plataforma>` con `post_id`, `status`, `last_error`, canal,
fecha y copia del request para reconciliación. Las escrituras siguen siendo
atómicas, con bloqueo y mezcla de los campos persistidos.

- Un `post_id` guardado prohíbe cualquier recreación automática, incluso si Buffer
  devuelve `draft`, `error`, `needs_approval` o el post se elimina externamente.
  Los otros estados remotos admitidos son `scheduled`, `sending` y `sent`.
- Antes de `createPost` se guarda intención con estado local `unknown`. Un timeout,
  desconexión, respuesta ambigua o cierre del proceso deja esa protección activa.
- `--sync-buffer-status` busca alrededor de la fecha original (±5 minutos, todos
  los estados), y exige una coincidencia única de canal, instante exacto y texto
  original. Guarda su ID y nunca adopta el mismo ID para dos elementos.
- Cero coincidencias o varias coincidencias mantienen `unknown` y bloquean el
  relleno de ese canal. Comprueba Buffer manualmente; no borres este estado para
  forzar un reintento sin demostrar primero que la creación no ocurrió.
- Un `MutationError` explícito permite registrar fallo definitivo. También se
  inspeccionan los `errors[]` GraphQL: HTTP 200 por sí solo no indica éxito.
  Si llega un ID junto a errores, se conserva inmediatamente.
- Cloudinary usa el SDK oficial, `resource_type="video"`, un ID determinista y
  `overwrite=false`; guarda el resultado antes de crear posts. Reutiliza la URL
  para todas las plataformas y ejecuciones posteriores. Tras una subida incierta
  consulta el ID persistido; no vuelve a subir automáticamente si no logra resolverlo.
- **No se elimina ningún medio de Cloudinary automáticamente**. Conserva el archivo
  disponible hasta que Buffer haya terminado de publicarlo. No uses enlaces
  compartidos de Google Drive como assets de Buffer.

### Restablecer el estado de publicación de un elemento

Solo para recuperación o pruebas después de eliminar manualmente las publicaciones de las plataformas:

```bash
python main.py --reset-publish-id CONTENT_ID
python main.py --reset-publish-id CONTENT_ID --confirm
```

El primer comando muestra el estado de publicación que se borraría y no escribe nada. `--confirm` elimina únicamente el bloque `publishing` de ese ID, incluidas las referencias de Buffer y Cloudinary y los campos de intención o reconciliación. Conserva el estado de generación, las rutas de vídeo, los intentos y la cola. No consulta ni modifica servicios externos ni elimina el archivo remoto de Cloudinary.

Referencia de operaciones y campos: [Buffer GraphQL](https://developers.buffer.com/reference.html).
Subida de medios: [Cloudinary Upload](https://cloudinary.com/documentation/upload_images).

### Tests sin servicios externos

```bash
pytest -q
python main.py --dry-run
python main.py --publish-dry-run
```

Los tests usan respuestas GraphQL/SDK simuladas y bloquean conexiones de red.
Cubren límites de cola, fechas, texto, vídeo, descubrimiento, estado, bloqueos,
reconciliación, respuestas parciales y ausencia de efectos externos en dry-run/check.
