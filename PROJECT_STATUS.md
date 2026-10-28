# Estado vigente de Kitok

Actualizado: **28/10/2026**. Rama **main**, base de esta unidad 73adb8d.
Esta unidad actualiza documentación y entrega contenido local ignorado.
Sin push ni publicación. El motor se reutilizó sin cambios. Fuentes: [guía](GUIA.md),
[voz](docs/fish-voice.md), [carpetas](docs/episode-files.md).

## Michael Myers — remake entregado para revisión

Carpeta nueva: `content/longform/trazo_005_michael_myers_historia/`.
Historia del personaje, canon 1978→2018→Kills→Ends; episodio anterior de la máscara
conservado aparte. Guion nuevo de 1.915 palabras, revisado independientemente; una
llegada anticipada de Allyson corregida antes de generar voz.

- **Normal:** `video_final.mp4`; SHA256
  `14ed986937ce5bff5984d8f3f75dcd289effcdce5f393d47bf016f7fca56a9cc`.
- **Subtitulado:** `entrega/video.mp4`; SHA256
  `47200831c5a7bd7b9d834891f68e297b3572da61fddff6e26bf9ec4e5b5606f1`.
- Ambos: **613,333 s / 18.400 fotogramas / 1920×1080 / 30 fps**. QA normal y subtitulado
  pasados; decodificación completa y audio decodificado idéntico entre versiones.
  −16,02 LUFS / −1,82 dBTP. Kitok produce exit 0; 44:44 totales, NVENC p5.
- 109 PNG vistos/aceptados y validados; 112 planos reales. Se repararon 6 recortes
  concretos, conservando originales y manifiestos. 102 fuentes de 541–542×297–298,
  4 de 820×454–455 y 3 de 1656×925; Native escala sin inventar detalle.
- Miniatura 1280×720 (original 1672×941) vista grande/móvil; 9 capítulos de tiempos
  reales, descripción y créditos. Música local Anxiety/DarkFog, CC BY 4.0.
  Bundle de 6 archivos comprobado; máster normal conservado fuera del bundle.

Una solicitud Fish con `collapse_whitespace_v1`, texto enviado/hash comprobados,
sin cortes ni nueva síntesis por el bloqueo ASR. 68 discrepancias revisadas por fila
(nombres/cifras/segmentación); 0 actividad sin palabras. Ventanas no corroboran
3 inserciones. Revisión documental independiente permite continuar; NO es una
coincidencia automática ni prueba de fidelidad acústica perfecta. Dos dicciones
exactas pendientes: **Laurie/Laura 6:11** y **aquel escondite 8:37**.

El agente vio todos los PNG, un fotograma normal y dos del subtitulado. No hubo
escucha ni reproducción completa de este remake. Siguiente: revisión/escucha del
operador, especialmente esos dos puntos. No publicar, repetir proveedores ni
continuar Jason por rutina. Registro: `editorial/produccion.md` y `estado.json`.

## Conservación indicada por el operador

Última aclaración 28/10: conservar carpetas anteriores para borrado manual y
mantener AMBOS MP4 (normal/subtitulado). El inventario se canceló antes de borrar:
**0 borrados, 1.134 rutas inventariadas con SHA intacto**.
Recibo: `local/cleanup/2026-10-28-pre-remake/cancelled-verification.json`.
No se aplicó limpieza ni archivo a los episodios anteriores en este encargo.

## Capacidades y límites vigentes

- Fish nuevo recibe espacios únicos y [] intactos; guion fuente legible conservado.
  Solicitudes anteriores mantienen identidad/caché. No sintetizar al guardar.
- Voz→ASR local→cortes seguros anclados en copia→segunda ASR estricta. Omisiones,
  reemplazos y actividad ambigua bloquean; revisión explícita separada del match.
  No hay reparación universal ni garantía de escucha humana.
- Ventanas cortas con anclas únicas y caché, sin guion al reconocedor ni relojes
  inventados. No reemplazan la segunda ASR tras cortes.
- Native/Fish/FFmpeg para nuevos shorts/largos; MPT sólo recuperación histórica
  explícita. Interfaces y contratos: [guía](GUIA.md).
- `stickman_delivery.py`: bundle de 6 archivos y organización con hashes/locks, sin
  borrado automático. El agente prepara relato/prompts/imágenes; Kitok procesa
  voz, tiempos, mezcla, cámaras, subtítulos y montaje.

Freddy sigue entregado con feedback muy positivo del operador. Su entrada activa
es `trazo_004_freddy_krueger/revisiones/voz_texto_continuo`; NO usar el voz.mp3
defectuoso de su raíz como entrega. Duración 630,533 s; su registro sigue intacto.
Jason sigue STANDBY: referencia anterior con errores de voz, no entrega corregida;
WAV reparado de 435,729 s, futuro remake útil >480 s sólo bajo otro encargo.

## Verificación de esta unidad

Kitok prepare exit 0/ready_to_render; produce exit 0; QA de ambos MP4 pasado; 109 PNG con SHA
intactos; bundle de 6 archivos/hashes y 9 capítulos comprobados. `make docs-check` y
`git diff --check` pasados el 28/10. Sin cambio de motor: no suite global por rutina.
No se verificaron OAuth, CI remoto ni publicación en este encargo.
