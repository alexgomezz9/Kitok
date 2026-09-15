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
- Sin publicación automática todavía.

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

Cuando esto sea fiable, v2 añadirá primero YouTube Shorts automático y después Instagram/TikTok.
