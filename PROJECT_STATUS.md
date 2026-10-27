# Estado vigente de Kitok

Actualizado: **2026-10-27**. Rama **main**; encargo activo: auditoría y mejoras de
Trazo Maldito (voz, skills/estilo, música, archivos y rendimiento). No publicar.
Manual: [GUIA](GUIA.md), [flujo editorial](docs/youtube-editorial.md),
[audio](docs/audio.md), [auditoría](docs/youtube-production-audit.md).

## Evidencia vigente

- Voz/Fish y Native/FFmpeg conservan fuentes, hashes y bloqueo por episodio.
  Narración, dirección visual e invocación ImageGen son trabajo del agente;
  mezcla, cámara, tiempos, montaje y QA los ejecuta Kitok sin LLM por plano.
- Biblioteca:24 pistas Kevin MacLeod/CC BY4.0, ocho candidatas de horror verificadas
  en caché27/10. Cuatro nuevas descargadas con licencia individual/catálogo/hash.
  53 tests de biblioteca pasados; elección no acredita escucha ni retención.
- Perfil del canal: historias9–12 min, MP4estrictamente>480s, una entrega subtitulada,
  identidad@trazomalditoes/UC9h_aIbnfQUo0ylPsPNnbrg separada de Loose Thread.
  OAuth read-only verificado26/10; no revalidado hoy ni necesario para este encargo.
- Gate27/10: `make verify`1194Python/25React, TypeScript/Vite, higiene/docs/
  whitespace exit0; `studio-check`exit0. 92tests finales de voz y24de entrega/
  subtítulos pasados con revisiones independientes cerradas. ASR local sobre
  original+derivado completos, adapter12s offline y caché de música verificados.

- Subtítulos: recuperación de encode terminado tras interrupciónQA, sin repetir
  codificación/GPU. 24tests focales de recuperación/entrega pasados y revisión
  independiente cerrada.

- Entrega compacta de seis archivos y limpieza visual explícita con simulación,
  locks y protección de fuentes/revisiones; cachés Jason conservadas por revisión
  de audio pendiente. Perfil/skills y selección visual: cierre documental en curso.

## Jason: QA técnico pasado, voz pendiente

`content/longform/trazo_003_jason_voorhees/revisiones/voz_limpia_8min` conserva
109 PNG,1411 palabras y115 planos. Recuperación final comprobada27/10:
subtitulado497.733333 s/14932 frames,−16.03LUFS/−1.75dBTP, audio idéntico al base.
No repetir render/Fish como diagnóstico ni afirmar escucha completa del agente.

El corte anterior401.810930–410.892653 s ytempo 0.94 conservó fuentes, pero NO
resuelve todas las anomalías. Reconocimiento local independiente detecta inserciones
candidatas repetidas («montantani», variantes) ausentes del guion. La voz requiere
revisión; `final_video_ready=false`. Protección `voice.transcript_verification=local_asr`
implementada, runtime/modelo compartidos bajo `local/`, sin dependencia del venv
principal. No corta automáticamente. También hay posible frase omitida/sustituida
en el TTS original; las marcas de Fish no prueban palabras pronunciadas. No se envió audio al ASR remoto; operador eligió alternativa local.

Rendimiento real: mezcla2m34s; animar115 planos16m50s; unir8 s; QA base3m54s;
segunda codificaciónASS2m41s. NVENC utilizado; escala4K/cámara/filtros son CPU.
Comparación GTA6 no verificable: no se encontraron sus artefactos actuales.

Siguiente: revisar ventanas `editorial/auditoria_audio_2026-10-27/revision.html`
y resolver añadidos/posibles omisiones antes de reparar voz en una revisión nueva.
Conservar cachés para reedición; no volver a sintetizar/renderizar automáticamente.
Nuevos episodios: perfil inmersivo stickman/terror, muestra de enfoques salvo
delegación, ASR local antes del montaje y entrega compacta. No publicar.
