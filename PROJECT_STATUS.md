# Estado vigente de Kitok

Actualizado: **2026-10-27**. Rama **main**. Corrección de voz cruda y comparación
Fish realizadas; próximo episodio en recorrido guiado, una fase cada vez.
Sin publicación ni push en este encargo. Manual: [GUIA](GUIA.md),
[archivos por fase](docs/youtube-stickman-es.md#entradas-y-salidas-por-fase),
[voz](docs/fish-voice.md), [flujo editorial](docs/youtube-editorial.md).

## Voz y procedencia

- Stickman envía a Fish `guion_final.txt.strip()`. `guion_lectura_limpia.txt`
  pertenece al storyboard, no es la entrada de voz. Guion/hash originales conservados.
- Prueba real: 64 palabras idénticas, Jason/Loose Thread, S2.1-free, directo y con
  timestamps. Jason tiene inserciones en ambas rutas; LT también difiere al leer
  español (referencia inglesa). La respuesta directa se guarda sin montaje.
  La captura del operador usa Drama3; muestra API Drama3 devolvió HTTP402, sin retry.
  No aislar causa universal de modelo/voz ni equiparar web y API con modelos distintos.
- `local_asr_autocut`: voz cruda → ASR local → recortes anclados en copia PCM →
  otra ASR → sólo entonces reloj/mezcla/montaje. Es el valor de init nuevo.
  Reemplazos, omisiones y ambigüedades bloquean; off conserva episodios antiguos.
  Runtime/modelo ASR compartidos en local/, sin enviar audio ni modificar Fish crudo.
- Validación actual: checks focales de motor/empalmes/integración, 42 últimos tests
  pasados; 40 del motor y 43 de fronteras Native/MPT pasados durante el encargo.
  studio-check, docs-check e higiene correctos. No repetir suite completa sin motivo.
  Baseline histórico anterior: make verify 1194 Python/25 React (no gate del nuevo código).

## Jason

Base: `content/longform/trazo_003_jason_voorhees`. Entradas y usos en su `FLUJO.md`.
Voz reparada: `editorial/autocorreccion_audio_2026-10-27/voz_reparada/audio.wav`.
Se aplicaron 24 cortes automáticos, 1 editorial por nombre ambiguo y 2 frases/19 palabras
recuperadas con la misma voz. Fuente original intacta. WAV 435.728708 s; segunda ASR
completa: 0 inserciones, 14 diferencias de reconocimiento. Escucha humana pendiente;
no declarar coincidencia acústica perfecta ni cumplimiento del mínimo 8 min.
NO se ha montado un vídeo nuevo con esta voz. El subtitulado anterior en
`revisiones/voz_limpia_8min/entrega/video.mp4` conserva errores: referencia visual,
`final_video_ready=false`. No ofrecerlo como vídeo nuevo corregido.

Limpieza: 1359 archivos de Jason retirados, incluidos220duplicados exactos de
imágenes/referencias de rutas históricas. Se verificaron245entradas por hash y
se conservó cada contenido canónico; quedan374archivos (imágenes/fuentes/recibos).
887 temporales Kitok/pytest cerrados retirados. Neto ~1.86 GiB tras compactar evidencia.
Manifiestos: `local/cleanup/2026-10-27-jason`. Se eliminaron muestras/cachés y el
máster limpio anterior, conservando el MP4 subtitulado de referencia. Reeditar
requerirá renderizar clips de nuevo; no borrar recibos ni fuentes para forzar TTS.

## Próximo episodio y motores

`content/longform/trazo_004_freddy_krueger`: fase 1: idea creada; STOP antes de
investigación/canon y escaleta. Perfil guided_exercise activo: explicar entradas,
operación y salidas, parar cada fase; volver a automático sólo por petición expresa.
Nuevas referencias del operador: stickman claro, sombras/contraluz/niebla, sangre
contextual cuando corresponde; escenas tranquilas/diurnas mantienen ese contexto.

Loose Thread largo, shorts y stickman generan con Native/Fish/FFmpeg. MPT sólo
queda para recuperación histórica explícita; no se desinstaló ningún servicio.
No revalidar YouTube para este trabajo local; OAuth anterior no prueba acceso hoy.
