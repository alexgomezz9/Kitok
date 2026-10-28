# Estado vigente de Kitok

Actualizado: **28/10/2026**. Rama **main**; cambios verificados en commits locales.
Push autorizado completado: main remoto verificado en 73adb8d; CI de ese commit
completada correctamente ([ejecución](https://github.com/alexgomezz9/Kitok/actions/runs/40693393540)).
Sin publicación de vídeos. Fuentes: [guía](GUIA.md),
[voz](docs/fish-voice.md), [carpetas](docs/episode-files.md),
[auditoría de producción](docs/youtube-production-audit.md).

## Capacidades comprobadas

- Nuevos episodios stickman: voz Fish → ASR local → cortes anclados cuando son
  seguros → segunda ASR estricta → planificación, mezcla y montaje Native.
  Omisiones, sustituciones y actividad ambigua bloquean. No hay reparación universal.
- TTS recibe `guion_final.txt` con espacios únicos y etiquetas `[]` conservadas;
  registra política y hash del texto enviado. La skill exige esta preparación en
  todas las síntesis nuevas del flujo. Solicitudes previas conservan su
  identidad. `guion_lectura_limpia.txt` sirve al storyboard y los subtítulos.
- El ASR puede revisar discrepancias en ventanas cortas con anclas únicas y caché,
  sin recibir el guion ni modificar relojes. Conserva resultados originales.
  Una revisión explícita tiene hash y estado propio; no acepta actividad pendiente
  en autocut ni sustituye la segunda ASR tras cortes.
- Shorts, largos Loose Thread y stickman nuevos usan Native/Fish/FFmpeg.
  MPT sólo permite recuperación histórica explícita; no se desinstaló su servicio.
- `scripts/stickman_delivery.py` ofrece bundle de seis archivos y organización
  explícita con hashes/locks. No borra automáticamente al guardar. El helper de
  imágenes crea contactos nativos; las claves de miniatura se validan antes de Fish.

## Freddy — entregado con feedback positivo

Carpeta: `content/longform/trazo_004_freddy_krueger/entrega/`.
Contiene vídeo subtitulado, miniatura, descripción, créditos, informe y LEEME.
Entrada activa: `revisiones/voz_texto_continuo/`; su configuración está corregida.
El `voz.mp3` de la raíz es el original defectuoso conservado: no usarlo como entrega.
Fases, inputs, outputs, skills e intervenciones: `editorial/produccion.md`.

Guion de 1.984 palabras y tres `[break]`; 124 PNG vistos y validados. El agente
eligió el estilo B bajo delegación, sin aprobación humana. 123 imágenes de atlas
son de 541–542 × 297–298; Native escala sin crear detalle. Última imagen individual:
1656×925. Miniatura final: 1280×720, original 1672×941; vista grande y móvil.

La nueva voz continua dura 630,517 s y no necesitó cortes. ASR: cinco diferencias
iniciales y cero huecos; ventanas automáticas resolvieron cuatro. Krueger/Kruger
se aceptó documentalmente con otra ventana local que recuperaba el nombre.
El agente no escuchó audio; el operador comunicó después que quedó perfecto.
Esto no convierte al control automático en garantía universal. GTA adjunto
coincide con el guion guardado y también usa saltos/etiquetas; falta su recibo
histórico para atribuir modelo o parámetros exactos. No se demostró degradación
intencional del plan gratis ni que los saltos fueran la única causa.

Kitok produjo 132 planos, música y subtítulos: **630,533 s, 18.916 fotogramas,
1920×1080/30 fps**. QA base y subtitulado pasaron; audio decodificado idéntico,
−16,02 LUFS y −2,24 dBTP. NVENC p5 confirmado por proceso y recibo. Total del
comando: 32:17; render/unión/reloj: 1000,42 s. Una ejecución inicial se interrumpió
porque el sandbox bloqueaba GPU; la definitiva se lanzó fuera, sin otra síntesis.
Hash final: `a920047afd15a54cf98f6f56ec9903ad028e44d4e5e1390b504afadad5adbf29`.

Chromium terminó el archivo completo a 4×, silenciado, sin error de medios y con
9.496 fotogramas perdidos. Tramo normal 0–80,174 s: 2.406 frames, cero perdidos.
No demuestra fluidez completa a 1×. Revisión independiente de entrega sin
inconsistencias materiales; no escuchó audio ni repitió ASR/render/decodes.

Limpieza: 869 auxiliares retirados, 1457,8 MiB lógicos; 266 rutas fuente con SHA
intacto. Se conservan revisión activa, PNG, audios, másteres, recibos y licencias.
El vídeo exportado usa hardlink. No se midieron bloques libres ni se barrió /tmp.

## Jason y organización anterior

Jason sigue **STANDBY**: futuro remake con nueva estética y duración útil >480 s.
`voz_reparada.wav` dura 435,729 s; no hay vídeo nuevo con ella. El vídeo conservado
sigue siendo referencia anterior con errores, no una entrega corregida.
Siete episodios ya tienen estructura e índice comunes. Limpieza anterior:
`local/cleanup/2026-10-27-organizacion/`, 419 fuentes verificadas sin deriva;
revisiones cerradas archivadas con restauración. No repetirla como pendiente.

## Verificación y siguiente paso

64 pruebas focales de audio/refinamiento y revisión independiente sin P0/P1;
20 de packaging para validación temprana. `make docs-check` vigente. No se repitió
suite global ni se verificó CI remoto, publicación u OAuth en esta tarea local.
Operador28/10: feedback muy positivo del vídeo/audio; próximas producciones
deben reforzar figuras stickman y etapas reconocibles, y evitar prosa formularia.
Perfil y tres skills actualizados; cierre eficiente registrado en AGENTS.
La prosa se decide al escribir con yt-script; sin regex, detectores ni filtros.
Git auditado: un worktree,11ramas locales históricas sin commits fuera de main;
8ramas históricas remotas consultadas, también contenidas en main43e55c3.
No se borraron ramas. Reglas editoriales centralizadas en el perfil que consulta yt-script; la skill
de coordinación remite a esa fuente. Push a main autorizado en el último encargo.
Siguiente: siguiente encargo editorial o mejora acotada del cierre automático;
remakes futuros siguen pendientes de encargo concreto. No publicar ni regenerar.
