# Estado vigente de Kitok

Actualizado: **29/10/2026**. Rama **main**, base de esta unidad **eee0fd1**.
Entrega editorial local; sin cambios del motor, push ni publicación.

## Chucky — entrega cerrada para revisión del operador

Episodio: `content/longform/trazo_006_chucky_historia/`.
Paquete de seis archivos en `entrega/`; conserva además ambos másteres:
`video_final.mp4` y `video_subtitulado.mp4`.

- **703,266667 s / 21.098 fotogramas / 117 planos / 1080p / 30 fps**.
- QA normal y subtitulado pasados, decodificación completa y audio idéntico
  entre versiones; −16,02 LUFS / −1,85 dBTP. Bundle/hashes comprobados.
- 101 PNG vistos, aceptados y validados; cinco reparaciones puntuales.
  94 fuentes de 543–544×299–300 y siete de 1658×927: escalado Native,
  sin inventar detalle. Miniatura revisada grande/móvil y 12 capítulos reales.
- Una solicitud Fish con `collapse_whitespace_v1`, voz original intacta y cero
  recortes/resíntesis. ASR sin inserciones/actividad fuera de palabras;
  51 discrepancias revisadas documentalmente y seis ventanas de contraste.
  Esto no acredita escucha humana ni dicción acústica perfecta.
- El agente vio todos los PNG y el contacto de fotogramas normal. No realizó
  reproducción ni escucha completa del vídeo. Revisión final del operador pendiente.
- El intento inicial usó CPU (23 planos, 14:58) por acceso restringido a GPU.
  Probe y MP4 posteriores confirmaron NVENC p5; reanudación de 32:45 usando
  el mismo CLI, voz, imágenes y mezcla, sin cambios de código/configuración.
- Limpieza `organize`: **784 auxiliares / 1.652.031.132 bytes lógicos** retirados.
  **120 rutas protegidas con SHA intacto**, incluidos 101 PNG, voz, ambos MP4
  y entrega. Recibos: `local/cleanup/2026-10-29-chucky/`.

Registro editorial y límites: `editorial/produccion.md`, `revision_voz.json` y
`estado.json` del episodio. Música Dark Walk/Unnatural Situation, CC BY4.0,
con créditos completos. Sin créditos vidIQ ni nuevos servicios.

## Miniaturas e identidad del canal

Perfil y [guía](GUIA.md): personaje stickman reconocible con máscara/ropa icónicas
y extremidades finas; punto intermedio, sin llevarlo a palitos puros. Texto
«LA HISTORIA DE» y nombre rojo; fondo, luz y composición propios de cada historia.
La luna no es plantilla. Proactividad editorial dentro del encargo autorizada.

Michael005 y Jason003: selección nueva en `miniaturas/miniatura_final.png`,
versionada como `miniatura_historia_v2.png`; anteriores preservadas. Sus bundles
previos conservan miniatura/recibos originales: al subir, usar la selección nueva.
Michael002 conserva copia nueva en su carpeta. Freddy permanece igual.

## Episodios anteriores y límites

- Michael005: remake entregado, 613,333 s; ambos MP4 conservados. Operador
  confirmó buen audio y dicciones de 6:11/8:37. Auditoría y experimento Native
  medido en [registro](docs/youtube-production-audit.md); optimizaciones propuestas
  sin integrar. No repetir Fish ni regenerar medios por rutina.
- Freddy004: entrega activa en `revisiones/voz_texto_continuo`, 630,533 s;
  feedback positivo del operador. La voz defectuosa de raíz no es la entrega.
- Jason003 sigue **standby**: portada nueva no corrige el vídeo/audio anterior.
  Futuro remake sólo con otro encargo. Carpetas históricas conservadas.
- Lectura oficial de Trazo Maldito comprobada28/10: ID correcto, cero vídeos,
  Analytics sin datos y Reporting disponible. No se verificaron publicación ni CI.

## Verificación y siguiente paso

Kitok preparado/renderizado, QA de ambos MP4, hashes y bundle comprobados29/10;
limpieza aplicada y fuentes/finales íntegros. `make docs-check` y
`git diff --check` pasados29/10 para cerrar esta unidad documental.
Sin cambios del motor: no suite global por rutina.
**Trabajo cerrado.** Operador revisa/escucha la entrega; no hay publicación autorizada.
