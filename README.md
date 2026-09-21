# Kitok — local video control panel

# How Kitok Works

```text
content_queue.json (script, caption, optional publish_at)
       |
       v
MoneyPrinterTurbo (generation)
       |
       v
validation / audio normalization (ffprobe + ffmpeg)
       |
       v
READY (local MP4 in outputs/ready and READY_DIR)
       |
       v
Cloudinary (one reusable public video URL)
       |
       v
Buffer (scheduled posts)
  +----+----+
  |    |    |
TikTok IG YouTube
```

The **queue** describes what you want to create and, when supplied, when to publish it. **State**
(`state/state.json`) records generation attempts, files, remote IDs, publishing
intent and reconciliation results. **READY_DIR** is a local/synced folder for
finished videos. **Cloudinary** hosts the video so Buffer can fetch it. **Buffer**
schedules a separate post for each social channel.

| Display state | Meaning |
| --- | --- |
| PENDING | Generation has not started. |
| GENERATING | MPT accepted a task; Kitok is waiting or validating its output. |
| READY | A valid local video exists. It may not have been scheduled anywhere. |
| SCHEDULED | Buffer accepted a scheduled post for this platform. |
| PUBLISHED | Buffer reports `sent` for this platform. |
| FAILED | Generation or a platform operation failed; inspect the error. |
| ATTENTION | A missing file, past date, ambiguous outcome or other issue needs review. |
| SKIPPED | Editorially excluded from future publishing; its queue entry and file remain. |
| ARCHIVED | Hidden from daily views; its history and remote posts remain. |

Generation and publishing statuses are separate. A video can stay **READY** while
TikTok is **SCHEDULED**, Instagram needs **ATTENTION**, and YouTube is **PUBLISHED**.
Kitok preserves saved remote IDs even when a remote post fails or disappears.

# Everyday Usage

Activate the environment and install the updated dependencies:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
streamlit run dashboard.py
# Equivalent launcher:
python main.py --dashboard
```

The local dashboard binds to `127.0.0.1:8501`. Telemetry is disabled in the project
Streamlit configuration. It is a local tool, not a public multi-user service.

The main navigation is **Home**, **Content**, **Calendar**, and **Attention**.
Home shows one recommended next step, today's timeline and the known schedule
coverage. Content is a searchable library with per-item video previews and a
short edit form. Calendar groups items by local date; its item menu includes
Move earlier/later, Skip and Archive. Moving swaps two local `publish_at`
values; it never reschedules an existing Buffer post. Attention groups issues
into an inbox. **Settings** and **Advanced / System** sit in the secondary sidebar
section, along with a short **How Kitok works** guide. Settings are read-only
and credentials are never displayed.

Rendering and navigation make no remote requests. Content lazily extracts a
small JPG from each local ready MP4 using FFmpeg, around 1.5 seconds in. The
disposable cache lives in `state/thumbnails/`; extraction failure leaves the
video untouched and simply shows the normal placeholder. Calendar rows omit
thumbnails to keep the schedule compact. **Refresh publishing status**
explicitly reads Buffer; **Reconcile saved posts** reads Buffer and reconciles
local saved IDs without recreating missing posts. **Preview schedule** is
offline and shows the proposed platform matrix, uploads, estimated Buffer
requests and resulting occupancy. **Fill schedule**, **Schedule this video**,
**Generate video** and **Regenerate video** require a review and a separate
confirmation click. Technical IDs and raw records are under Advanced details.

**Import batch** is inside Content → Add content. Paste a JSON array or upload a
UTF-8 `.json` file (up to 2 MB), then validate before the separate Import
confirmation. Each object needs `id`, `subject` (or `topic`), `script`, `caption`
and `keywords` (or `video_terms`). `publish_at` is optional; omitting it creates
an unscheduled item. Optional fields include `youtube_title` and `platforms`.

```json
[{"id":"moon_1","topic":"Why the Moon glows","script":"A narration of at least twenty characters.","caption":"Moon facts","video_terms":["moon","night"]}]
```

IDs must be unique and an ID with saved state history cannot be reused. Explicit
date conflicts are shown in the calendar instead of rejecting the whole batch.
Import commits the whole batch in
one local queue write; it does not generate videos or contact a service.
Confirmed actions recheck state and cannot silently add posts outside the preview.
Publishing controls are disabled when `PUBLISH_ENABLED=false`.

Title, YouTube title, caption, terms, script and time edits, plus publishing-state
reset, also show a confirmation. Queue edits are local and atomic. Changes to an
item's content or schedule, swapping times and Skip are blocked when publishing
metadata exists. Script and video terms can change only before generation starts;
this keeps an existing ready video aligned with its script. Archive only hides the
local item; it leaves remote posts alone. Skipped and archived entries are also
excluded from generated local handoff plans.
Delete from queue requires typing the content ID and is available only when no
publishing metadata exists. It preserves local media and state history, and that
ID cannot be reused. New content starts as Pending; adding it never generates a
video. Reset is only for manual recovery after deleting social posts yourself.

CLI equivalents:

## Queue and scheduling

Generation and scheduling use separate state. `READY + UNSCHEDULED` means the
MP4 exists but has no date. `READY + QUEUED` waits in the local FIFO queue.
`READY + SCHEDULED` has a local `publish_at`. Buffer submission remains a
separate, explicit publishing action; a local date does not mean a Buffer post
exists.

The queue uses `queue_position`. New READY items go to the bottom, and the
automatic scheduler assigns the oldest queued item to the next free configured
slot. In Calendar, **Antes** and **Después** exchange two local scheduled times;
they remain disabled for items already sent to Buffer. Use the other Calendar
buttons or these commands:

```bash
python main.py --queue
python main.py --queue-add CONTENT_ID
python main.py --queue-up CONTENT_ID
python main.py --queue-down CONTENT_ID
python main.py --queue-top CONTENT_ID
python main.py --queue-bottom CONTENT_ID
python main.py --queue-remove CONTENT_ID
python main.py --unschedule-id CONTENT_ID
```

Bulk operations always support a read-only preview followed by an explicit
confirmation:

```bash
python main.py --unschedule-future --dry-run
python main.py --unschedule-future --confirm
python main.py --import-batch rick_morty_30.json --dry-run
python main.py --import-batch rick_morty_30.json --confirm
python main.py --queue-ready-all --dry-run
python main.py --queue-ready-all --confirm
python main.py --schedule-fill --dry-run
python main.py --schedule-fill --confirm
python main.py --queue
```

`--unschedule-future` only clears future local dates and preserves queue rows,
READY state and MP4 files. Add `--queue-after` to its confirmed invocation to
put affected READY videos at the bottom of the queue. Items with Buffer history
are reported under `attention` and remain unchanged. Published items cannot be
unscheduled. An explicit timezone-aware `publish_at` still overrides automatic
scheduling. Daily slots and timezone are configured once through
`DEFAULT_POSTING_SLOTS` and `TIMEZONE` (defaults: 13:00, 19:00 and 22:00 in
Europe/Madrid).

```bash
python main.py --status
python main.py --publish-dry-run
python main.py --publish-dry-run --live
python main.py --buffer-usage
python main.py --buffer-usage --refresh
python main.py --cloudinary-usage
python main.py --cloudinary-usage --refresh
# The next command can upload and schedule; requires PUBLISH_ENABLED=true:
python main.py --buffer-maintain
python main.py --sync-buffer-status
```

`--publish-dry-run` is **truly offline**, even with API credentials. It prints
local time, UTC `dueAt`, caption/title, media path, disclosure flags, occupancy
source and snapshot time. `--live` allows Buffer reads but does not write local
state/cache, upload, or schedule. Neither preview guarantees future availability.

`--buffer-usage` reads only cached headers. `--refresh` sends one lightweight
`account { id }` query with no retry. Other Buffer operations save headers from
responses they already need. The account-scoped cache is `state/services.json`.
Buffer documents structured `RateLimit` (`r` remaining, `t` reset seconds) and
`RateLimit-Policy` (`q` quota, `w` window seconds) headers. Kitok matches the
900/86400/2592000-second windows by `w`, not by plan-specific names. Missing values
stay unknown. A cached counter is an observation, not a quota reservation.

Maintenance reuses recently checked organization/channels for up to
`BUFFER_DISCOVERY_TTL_SECONDS` (300 by default); an explicit dashboard refresh
always refreshes channel health. Configured organization IDs avoid account
rediscovery. All target channels share one paginated occupancy query (`first: 100`).
Known posts missing from that snapshot and ambiguous intents still require safe
reconciliation reads. There are no readbacks of newly created posts and no
occupancy refetch after each create. The run prints BEFORE / CREATED / AFTER
(estimated), its approximate request count, and known remaining quotas. A budget
check runs before uploads/creates and reserves `BUFFER_REQUEST_RESERVE` requests.
An unknown or expired short-window budget also blocks the publishing batch until
a response supplies current usage headers.
Read retries are bounded; long 429 cooldowns stop immediately and are cached.
Creation is never automatically retried after an ambiguous response.

AI disclosure is explicit: `CONTENT_AI_ASSISTED`, `TIKTOK_AI_GENERATED`, and
`YOUTUBE_AI_GENERATED` default to `true`. False values are sent as false. The
current schema also supports Instagram `isAiGenerated`, so
`INSTAGRAM_AI_GENERATED=true` preserves the existing disclosure by default and
makes it configurable. Only documented Instagram metadata is sent. Kitok does not
classify whether a disclosure is legally required.

Every new generation/regeneration is inspected for container, codecs, dimensions,
fps, pixel format, bitrate, duration and size. Kitok uses a conservative H.264,
yuv420p, AAC-LC profile. Excessive AAC bitrate/sample rate is repaired with
`-c:v copy -c:a aac -profile:a aac_low -b:a 120k -ar 48000 -movflags +faststart`,
then inspected again before READY. Compliant files are not re-encoded. Other
video defects are reported for review rather than silently changing video quality.
Existing files are not normalized merely by opening the dashboard or previewing.

Cloudinary's Admin `usage` API is available through explicit refresh. The display
uses returned storage/bandwidth/transformation/credit values only. Its numbers are
updated periodically. `CLOUDINARY_USAGE_GUARD=true` blocks **new uploads** when the
report is absent, older than `CLOUDINARY_USAGE_MAX_AGE_SECONDS`, lacks a usable
limit, or reaches `CLOUDINARY_USAGE_THRESHOLD` (90% by default). Reusing an existing
asset and reconciling an uncertain upload remain possible. Refresh usage before
the first new upload. Local byte reservations include earlier uploads in the
storage check until the next explicit usage refresh. Failed/uncertain uploads
keep their reservation conservatively. The application never upgrades or buys a plan. This guard
cannot guarantee future bandwidth charges, because Cloudinary reports lag and
external traffic is outside Kitok's control.

Implementation map: `dashboard.py` is the entrypoint; `kitok.dashboard` renders
pages; `control_panel` coordinates existing services. `Publisher` owns planning,
idempotency and scheduling; `BufferClient` owns HTTP; `CloudinaryHost` owns media
hosting. `VideoValidator.prepare` owns audio normalization. `StateStore` provides
all atomic JSON writes and publishing locks; service caches use those same helpers.

API references checked during this change:

- [Buffer rate-limit headers](https://developers.buffer.com/guides/api-limits.html)
- [Buffer pagination and combined channel filters](https://developers.buffer.com/guides/pagination.html)
- [Buffer CreatePostInput](https://developers.buffer.com/types/CreatePostInput.html), [YouTube AI field](https://developers.buffer.com/types/YoutubePostMetadataInput.html), [Instagram AI field](https://developers.buffer.com/types/InstagramPostMetadataInput.html)
- [Instagram requirements](https://support.buffer.com/en-us/articles/using-instagram-with-buffer-YSjg2dXFV8): 128 kbps audio, 25 Mbps video, 300 MB. Buffer's media pages differ on a 3/5-second minimum; Kitok uses the stricter 5-second automatic-Reel requirement.
- [Cloudinary Admin usage API](https://cloudinary.com/documentation/admin_api#usage)

The sections below retain the detailed WSL/MPT setup and CLI recovery guide.


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

## Vídeos con voces y diálogo

Las entradas antiguas de `content_queue.json` siguen siendo vídeos explicativos con Álvaro y Pexels. En **Content → Add content** puedes escoger formato, voz y, para diálogo, estilo visual y poses. El importador JSON acepta esos mismos campos. La cola guarda las opciones elegidas y la regeneración las reutiliza.

Para diálogo, `visual_profile: "pexels"` conserva MPT/Pexels. `visual_profile: "gameplay"` usa vídeos locales de `assets/backgrounds/gameplay/` sin pedir un fondo a MPT. El archivo Minecraft existente se descubre automáticamente. También se conservan las piscinas locales antiguas (`minecraft/`, `random/`, `satisfying/`, `subway/`). Se aceptan `.mp4`, `.mov`, `.mkv` y `.webm`; basta con añadir un archivo a la carpeta. La ruta gameplay mide el audio final de Fish, selecciona un archivo y un intervalo reproducibles a partir del ID, y busca el segmento con FFmpeg antes de decodificar. `background_seed` es opcional para cambiar el intervalo sin cambiar el contenido.

Si quieres personajes, coloca PNG transparentes en `assets/characters/rick/` y `assets/characters/morty/` y selecciona **Rick + Morty poses**. Se descubren todas las poses por nombre de archivo, se valida su transparencia y se recorta el borde transparente antes de escalarlas. Un PNG inválido se omite con advertencia. Las poses cambian según el turno y solo se muestra el hablante activo. Los MP4, PNG y audios generados no se versionan.

Las opciones para futuras voces, parejas de personajes, mapeo hablante→carpeta y tipos de fondo viven en `presets/generation_profiles.json`. Para añadir una pose, solo añade el PNG; para añadir un personaje o una voz, añade su carpeta y entrada al catálogo. El compositor no necesita cambios. Los subtítulos de diálogo son locales, de 2 a 4 palabras cuando el texto lo permite, con `DIALOGUE_SUBTITLE_MAX_CHARS` configurable. Los explicativos conservan sus subtítulos MPT.

Añade a `.env`:

```dotenv
FISH_API_KEY=
FISH_MODEL=s2.1-pro-free
FISH_TTS_TIMEOUT_SECONDS=180
MPT_PROGRESS_STALL_MINUTES=12
```

Para narradores Fish de un solo hablante, configura también MoneyPrinterTurbo `config.toml` con `[fish_audio] api_key = "..."` (o su variable `FISH_API_KEY`) y `model = "s2.1-pro-free"`. Para diálogo, Kitok lee su propia clave y llama a Fish directamente. Usa una versión de MPT que admita `voice_name = "no-voice"` y voces `fish_audio:<reference_id>:<display_name>`; Kitok desactiva los subtítulos de MPT y compone los suyos con FFmpeg. `ffmpeg` y `ffprobe` deben estar disponibles. Toda salida final pasa por `VideoValidator.prepare()` antes de READY.

El vídeo visual de diálogo con Pexels usa una frase corta derivada del primer término de búsqueda. MPT calcula la duración de `no-voice` a partir de `video_script`; enviarle todo el diálogo creaba una unión innecesariamente larga de clips. Kitok ajusta el visual a la duración real del audio Fish después de descargarlo.

Para comprobar la integración real sin tocar la cola, el estado ni los vídeos READY de producción, ejecuta deliberadamente:

```bash
python main.py --smoke-test dialogue-pexels
python main.py --smoke-test dialogue-gameplay
```

La prueba Pexels usa Fish, el MPT local y FFmpeg; la de gameplay usa Fish, Minecraft local, PNG y FFmpeg. Ambas aíslan estado y archivos de trabajo. La prueba gameplay deja una vista previa inspeccionable en `outputs/smoke/dialogue_gameplay_preview.mp4`, fuera de READY y de la cola. MPT conserva su tarea de prueba Pexels en su propio historial. Si una tarea de MPT desaparece o deja de avanzar, Kitok conserva el ID y marca el intento como fallido; revisa el historial de MPT antes de usar `--retry-failed`.

Ejemplo de diálogo con Pexels:

```json
{
  "id": "pulpo_dialogue_001",
  "content_format": "dialogue",
  "dialogue_preset": "rick_morty_es",
  "subject": "Por qué los pulpos tienen tres corazones",
  "dialogue": [
    {"speaker": "rick_es", "text": "Morty, los pulpos tienen tres corazones."},
    {"speaker": "morty_es", "text": "¿Tres corazones?"}
  ],
  "caption": "Un dato marino sorprendente",
  "keywords": ["octopus", "ocean"],
  "visual_profile": "pexels",
  "publish_at": "2026-09-20T13:00:00+02:00"
}
```

Para gameplay, cambia `visual_profile` a `gameplay` y añade `character_profile: "rick_morty_es"` si quieres poses. Puedes añadir `background_seed: "otra-toma"` para elegir otro segmento y `visual_seed: "otra-presentacion"` para repetir o cambiar poses y pequeñas variaciones de posición. Solo aparece el hablante activo; la configuración de reacciones se conserva para un posible uso futuro, pero el compositor actual no la utiliza. Tamaño, ancho máximo, anclajes, variación, entradas y salidas se ajustan con las variables `CHARACTER_*` documentadas en `.env.example`. Los explicativos pueden elegir `voice_profile: "alvaro"`, `"rick_es"` o `"morty_es"`; conservan el flujo original de MPT y Pexels.

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

Cuando se incluye, `publish_at` exige zona horaria. Si se omite, el contenido se
importa sin programar y puede añadirse después a la cola FIFO.

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
posts. Por defecto usa el estado y caché locales incluso con credenciales.
`--publish-dry-run --live` consulta la ocupación actual sin escrituras locales ni
remotas. El resultado no garantiza disponibilidad futura.

### Subtítulos antes de la primera prueba

Comprueba `subtitle_enabled` en el preset actual. El MP4 destinado a publicación
automática debe llevar sus propios subtítulos incrustados. Comprueba visualmente
el vídeo final y prepara sus subtítulos mediante tu flujo de generación/edición
antes de subirlo. ffprobe valida propiedades técnicas, pero no puede demostrar
que haya texto incrustado en los fotogramas. Esta capa no cambia el preset, no
invoca subtítulos nativos de las plataformas. La normalización de audio copia el vídeo sin recodificarlo.

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

Las creaciones siguen `CONTENT_AI_ASSISTED`, `TIKTOK_AI_GENERATED` y
`YOUTUBE_AI_GENERATED` (true por defecto). El esquema actual admite también
`INSTAGRAM_AI_GENERATED`, que conserva el valor true por defecto. Instagram usa `type: reel` y `shouldShareToFeed: true`.
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
