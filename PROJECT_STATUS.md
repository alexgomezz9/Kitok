# Estado vigente de Kitok

Actualizado: **2026-10-27**. Rama **main**. Auditoría y mejoras de Trazo Maldito
terminadas localmente; Jason sigue pendiente de reparación/revisión de voz.
No se hizo push ni publicación en este encargo; CI remoto no comprobado.
Manual: [GUIA](GUIA.md), [auditoría](docs/youtube-production-audit.md),
[voz](docs/fish-voice.md), [audio](docs/audio.md).

## Capacidades y evidencia actual

- Native/FFmpeg monta, mezcla, anima y ejecuta QA sin LLM por plano. El agente
  investiga, escribe, decide escenas/prompts, invoca ImageGen y revisa significado.
- Perfil y tres skills: relato inmersivo del personaje, silueta stickman explícita,
  terror/sangre contextual, tres enfoques antes de ampliar estilo nuevo. Delegación
  «siguiente automático/no preguntes» permite elegir al agente y continuar.
- Control opcional `voice.transcript_verification=local_asr`: Whisper CPU/int8,
  sin enviar audio; bloquea discrepancias/actividad sospechosa hasta revisión.
  No corta automáticamente ni sustituye el reloj Fish. `off` conserva hashes legacy.
  Runtime/modelo compartidos bajo `local/`, fuera del venv principal y de Git.
- Biblioteca: 24 pistas CC BY4.0, ocho candidatas de horror verificadas en caché
  el 27/10. Cuatro nuevas con catálogo/licencia individual/MP3/SHA comprobados.
- Subtítulos: nuevo trabajo conserva encode terminado para reanudar QA sin
  recodificar. No adivina trabajos antiguos sin recibos ni entregas parciales.
- Entrega compacta de seis archivos; limpieza visual explícita con simulación,
  locks y protección de fuentes/revisiones. Cachés Jason conservadas por revisión.
- Gate 27/10: `make verify` pasó 1194 Python/25 React, TypeScript/Vite, higiene,
  docs y whitespace (exit0); `make studio-check` pasó. Últimos controles focales:
  92 de voz y 24 de entrega/subtítulos, revisiones independientes cerradas.
  ASR real completo original/derivado, adapter offline y música local verificados.
  Reproductor HTML probado en Chromium por HTTP local: dos saltos/paradas sin error;
  no acredita escucha del agente ni prueba `file://` en Windows.

## Jason: técnica correcta, voz sin resolver

Activa: `content/longform/trazo_003_jason_voorhees/revisiones/voz_limpia_8min`.
Conserva 109 PNG, 1411 palabras del guion y 115 planos. QA final comprobado 27/10:
497.733333 s/14932 frames, −16.03 LUFS/−1.75 dBTP, audio idéntico al base.
Entrega organizada bajo `entrega/`, con `final_video_ready=false`/`needs_review`.

El corte anterior 401.810930–410.892653s y tempo 0.94 no limpió todas las anomalías.
ASR independiente encuentra 38 diferencias en el derivado, incluidas inserciones
repetidas. La pseudo-habla también está en la voz seca original guardada por Fish;
el guion solicitado no la contiene. Posible frase de 14 palabras sustituida/omitida
antes del corte; pendiente de escucha, las marcas Fish no prueban pronunciación.
No hubo otra síntesis ni cortes de audio en esta auditoría.

Siguiente: revisar `editorial/auditoria_audio_2026-10-27/revision.html` del episodio,
resolver añadidos/posibles omisiones y crear una revisión de voz antes de reeditar.
Conservar cachés; simulación estima 1.09 GiB recuperables, no se aplicó limpieza.
No repetir producción pagada ni dar por limpia la voz por el QA técnico.

Rendimiento: mezcla 2 min 34 s, 115 planos 16 min 50 s, unión 8 s, QA base 3 min 54 s, ASS 2 min 41 s.
NVENC utilizado; cámara/escala 4K/filtros siguen en CPU. Optimización de cámara y
ASS en una sola pasada siguen propuestas; comparación GTA6 no verificada.

Canal: @trazomalditoes/UC9h_aIbnfQUo0ylPsPNnbrg, separado de Loose Thread.
OAuth read-only comprobado 26/10; no revalidado hoy, sin necesidad para este encargo.
