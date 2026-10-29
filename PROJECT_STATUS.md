# Estado vigente de Kitok

Actualizado: **29/10/2026**. Rama **main**, base de esta unidad **00ed04a**.
Cierre/cola stickman implementados localmente; sin push ni publicación.

## Pennywise007 — entregado a la cola, render en curso

`content/longform/trazo_007_pennywise_historia/`, continuidad IT2017/2019.
Guion2157palabras habladas,87PNG vistos/validados,2reparaciones,miniatura1280×720
vista grande/móvil;15ImageGen. Preparaciónreal:134planos/708.0s previstos/13capítulos.
Voz original707.9705s preservada;28discrepanciasASR revisadas documentalmente,
5+5ventanas,0actividadfuera,0cortes. Dos posibles variacionesmenores aceptadas;
escucha humana pendiente. UnaudioFishconfirmado, tras primerfalloDNS incierto y
reintentoautorizado; siempre s2.1-pro-free, sin inferir cobro a partir del nombre.

Worker **9cd3ae0ad98b447283020a2091db75d0**, GPUexigida; log confirmaNVENCp5
ymezcla iniciada. Resumen `local/stickman_jobs/ESTADO.md`; log delmismoID.
Kitok continúa normal/subtítulos/QA/bundle/limpieza sin mantener al agenteesperando.
**Todavía no acreditados MP4/QA/limpieza finales de Pennywise.** No publicar.

Feedback29/10 guardado en perfil/guía: estilos/interiores y ancla separados de
miniatura; emoción/cejas/ojos/boca/postura por escena, sin cara delvillano enreparto.
MuestraChucky vista, patrónobservado; causalidaddereferencia plausible noconfirmada.
Chucky/vídeos anteriores no se modifican por esta regla futura.

## Cola stickman — disponible para el siguiente episodio

`complete` reúne Native normal → subtítulos → ambos QA/recibos → entrega seis
archivos → `organize` conservador, bajo un lock de episodio. Recibe materiales
editoriales definitivos y narración existente; no ejecuta síntesis, ASR ni cortes.
El agente termina guion/voz/imágenes/miniatura/descripción/capítulos antes de encolar.

`scripts/stickman_jobs.py enqueue EPISODIO --require-gpu` arranca un worker
independiente de terminal/chat; `status`, `watch [ID]`, `retry ID` y `start`.
Resumen `local/stickman_jobs/ESTADO.md`, JSON/log por ID con fase, planos,
heartbeat, error y traceback. Estados queued/running/needs_review/technical_complete.
Inputs congelados por SHA, retry explícito sin repetir proveedores. Un pesado por
cola; no exclusión de otros CLI/Studio ni servicio de arranque de Windows.
Muerte del worker conserva materiales y procesos supervivientes bloquean la cola.

Cierre técnico conserva ambos MP4, PNG, voz original/efectiva, alineación, prompts,
manifiestos/licencias/revisiones. Auditoría de limpieza previa e integridad posterior.
GPU requerida se propaga a cada nueva codificación; reutiliza bytes válidos antes
de seleccionar encoder. NVENC p5 comprobado con acceso real al dispositivo;
el sandbox restringido selecciona CPU. [Operación](GUIA.md#produccion-repetida-de-trazo-maldito).

Verificado29/10: **95 tests focales**, incluidos Native real6s, ambos QA, bundle,
limpieza, reuse sin encode, fallo de bundle/limpieza parcial, inputs cambiados,
worker desacoplado, kill+FFmpeg superviviente, locks y política GPU. Revisiones
independientes arquitectura/corrección/adversarial; hallazgo GPU corregido y releído.
**25 tests frontend + build**, `studio-check`, `docs-check`, higiene y whitespace.
`make verify` excedió su límite600s en pytest (~70%, sin fallos mostrados hasta
corte); suite global completa no acreditada. No repetir vídeos históricos para QA.
Todavía sin episodio largo completo por la nueva cola; primera producción real
servirá para confirmar duración/operación. Éxito técnico no acredita escucha humana.

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

## Siguiente paso

Consultar el estado/log de Pennywise; intervenir sólo si queda REVISAR o lo pide el
operador. Puede prepararse otro episodio mientras Kitok monta. No esperar aquí QA.
Cambios de esta unidad: preferencias/editorial/estado, sin modificar motor.
`docs-check`, validaciónconfig, integridad87PNG y preparaciónreal pasados29/10.
No suite global por rutina; no push, publicación ni CI/remoto comprobados.
