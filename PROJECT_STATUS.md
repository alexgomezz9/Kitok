# Estado vigente de Kitok

Actualizado: **2026-10-22**. Rama **feature/youtube-stickman-es**, base main
`99f4766`; motor compartido `19984d5` subido con CI correcto (39741341045).
Integración y push de main autorizados expresamente por el operador; pendientes
hasta cerrar el checkpoint del adaptador y su verificación final.
Manual: [GUIA.md](GUIA.md); [stickman ES](docs/youtube-stickman-es.md);
[montaje](docs/editing.md); [movimiento](docs/motion.md); [audio](docs/audio.md).

## Capacidades comprobadas

- Nuevo `youtube_stickman_es` por CLI: guion/título originales, voz/SRT, cortes
  sobre tiempos reales, plan JSON/Markdown y solicitudes de ilustraciones por
  escena. Prueba de 600 s con subtítulos granulares produce 120 escenas.
- **Codex genera las ilustraciones con su herramienta integrada**. Python sólo
  gestiona recursos, tiempos, reanudación, QA y montaje. Hay muestras, aprobación
  vinculada a hashes, reservas, revisión, reintentos explícitos y recuperación;
  no hay backend ImageGen ni API de pago alternativa.
- Único motor Native/FFmpeg/ASS/Pillow: cámaras, imágenes a pantalla completa,
  transiciones de 0,4 s, música licenciada de caché, SFX, ducking y normalización.
  Produce MP4 1080p/30, tres miniaturas PNG, descripción, capítulos y metadatos;
  reanuda o renderiza otra revisión sin regenerar imágenes ni voz.
- Shorts, documentales, importación de fotos por archivo/frase, estudio y
  recuperación de voz pagada se conservan. Galería documental: 43 demostraciones,
  20 efectos, 11 cámaras y 8 transiciones. Nuevas generaciones usan Native;
  MPT sólo recupera IDs históricos. No hay publicación automática en este flujo.

## Verificación y límites

- Gate final: `KITOK_E2E_PORT=18441 make verify-browser`, **1005 Python**,
  **25 React**, TypeScript/Vite y **5 E2E**, salida cero. Incluye detección
  acústica con FFmpeg real; 10 pruebas focales previas correctas.
  `make docs-check`, `make studio-check` e higiene del índice correctos.
- Prueba local `outputs/evaluation/stickman-es-setup-20261022-r3/`: **15,033 s,
  451 fotogramas**, todos los PTS, decode completo, 1080p/30/yuv420p, −16,02 LUFS,
  pico −13,51 dBTP y ningún negro inesperado. Tres imágenes de diagnóstico y tres
  miniaturas; música licenciada/SFX y rerender que reutiliza los tres planos.
  `qa-continuity.json` analiza voz original y mezcla, sin silencios ≥1,5 s bajo
  −45 dB. Los intervalos detectados requieren escucha contextual, no rechazo ciego.
- Chromium reprodujo completa la prueba local silenciada, sin error ni frames
  descartados. Contactos de principio/desarrollo/final, transiciones y miniatura
  inspeccionados. Revisiones de corrección, adversarial y evaluación cerradas;
  sin P0/P1 pendiente. La muestra **usa tono sintético, no narración**: no acredita
  sincronía hablada, calidad final del canal ni aprobación editorial.
- No se han generado ilustraciones definitivas, otra voz Fish ni un episodio
  completo. Cuota real para 120 imágenes y acabado final pendientes. Un MP3 externo
  sin SRT ni timestamps Fish compatibles necesita alineación real aportada; este
  adaptador no añade ASR local. Escucha, errores semánticos/gráficos, referencias,
  derechos y Windows requieren revisión humana.
- Los 12 inputs protegidos conservan hashes. Backend del operador intacto;
  navegador y servidor temporales de QA cerrados. No se publica ni despliega.
  Pexels admite fotos por keywords, comprobado antes; su búsqueda automática de
  fotos sigue sin implementarse. [Historia](docs/archive/README.md).

Siguiente: terminar gate/checkpoint e integración main autorizada. Para producir
el primer stickman, aportar guion definitivo, título y fotogramas interiores;
Codex prepara y presenta una muestra de estilo antes del lote. UltimateBet
completo lo inicia el operador desde el estudio tras revisar sus muestras.
