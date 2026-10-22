# Estado vigente de Kitok

Actualizado: **2026-10-22**. Rama **feature/youtube-stickman-es**, base main
`99f4766`. Main anterior integrado por fast-forward desde feature/documentary-motion.
Motor documental `dc4924c`, estudio
`c61635d`. Se conserva el historial granular. SHA remoto y CI del checkpoint
final se comprueban al entregar; CI de ambas unidades anteriores correcto
(39676770736 y 39677661474).
Manual: [GUIA.md](GUIA.md); [montaje](docs/editing.md);
[efectos y demos](docs/motion.md); [audio](docs/audio.md).

## Capacidades comprobadas

- Preparación del adaptador `youtube_stickman_es` en curso, separado de shorts
  y documentales. El motor compartido admite duración de transición configurable
  (mantiene 0,28 s anterior) y recibo SHA del MP4. Nuevo flujo todavía en verificación;
  no hay imágenes definitivas, voz nueva ni episodio completo generado.

- Fotos/documentos JPG, PNG y WebP, stock, cámaras, ASS, caché y FFmpeg comparten
  Native. Archivo y frase bastan; JSON parcial opcional sobrescribe defaults.
  Los intervalos restantes conservan montaje automático. Anclas Fish validadas
  contra transcript completo o estimación declarada; sin LLM durante el render.
- Once cámaras; seis básicas primero. Disolución, barrido, slide y foco usan
  continuación móvil real; sin margen de stock, corte seguro registrado. Fundidos
  visuales .6/.8 s dentro del metraje, sin fundir la narración.
- Fecha mecanografiada/foco nueva; identidad y documento aportado mejorados.
  Veinte candidatos de efectos, no veinte intenciones automáticas. Parallax sin
  capas se rechaza. Three.js/póker continúa opcional histórico.
- Estudio: importar guion/JSON, elegir episodio/fotos, upload seguro y añadir
  archivo+frase. Preview/guardar no llama proveedores. Comprobado en Chromium con
  upload real y persistencia de borrador en workspace temporal.
- Nuevo montaje con voz pagada: otro ID, auditoría de recibo/guion/voz/alineación,
  confirmación y bloqueos compartidos; sin Fish ni red. La recuperación del mismo
  ID sigue disponible. No se inició un montaje completo del operador.
- Galería activa: **43 demos**; muestras UltimateBet `final_ub_opening_r3`
  (31,5 s) y `final_ub_portrait_r1` (27,8 s), otro tema `final_mfa_r2` (20 s),
  documento aportado, 20 efectos, 11 cámaras y 8 transiciones. Referencias A/B,
  créditos y anteriores conservados. Detalles y comandos en [motion](docs/motion.md).

## Verificación y límites

- `KITOK_E2E_PORT=18441 make verify-browser`: **897 Python** (310,19 s),
  **25 React**, TypeScript/Vite y **5 E2E** (17,1 s), salida cero.
  Incluye dos recorridos Native de 6 s con FFmpeg real y proveedores simulados;
  la suite bloquea red externa. `make docs-check` y `make studio-check` correctos.
- Auditoría de los **7.179 frames** de los 43 MP4: PTS, 30 FPS, inicio cero,
  `yuv420p` y decode completo correctos. Tres muestras con audio A/B idéntico;
  primeros/últimos frames reales negros. Los 43 vídeos llegaron al final sin error
  en Chromium local silenciado (un frame descartado por el navegador), registrado
  en `outputs/evaluation/editor-final-20261021/browser-playback-summary.json`.
  Contactos de muestras/documento y secuencias de seis cámaras/cinco transiciones
  inspeccionados. No equivale a escucha o aceptación editorial humana.
- Revisiones independientes de corrección y adversarial: hallazgos materiales
  corregidos y releídos. Evaluación final sin P0/P1 nuevo; segundo tema demuestra
  generalización visual con música, **sin narración** ni prueba de sincronía hablada.
  No había voz del segundo tema y no se sintetizó otra Fish.
- Remotion real, misma foto/audio, 4 s/120 frames: 31,50 s/654.240 KB RSS frente
  a Native 11,53 s/279.664 KB. La mejora tipográfica se trasladó a ASS. Sin segundo
  motor en producción. [Método, fuentes y límites](docs/motion-research.md).
- Pexels permite fotos por keywords: prueba de lectura/descarga correcta con
  crédito. Investigación adicional, no búsqueda automática de fotos implementada.
- 12 inputs protegidos mantienen hashes. Sin nueva Fish, documental completo,
  publicación, borrado de cachés ni modificación del backend del operador.
  Derechos/autenticidad de fotos aportadas, escucha y Windows siguen sin verificar.

MPT sólo recupera IDs históricos: nuevos largos/shorts usan Native; no se envían
trabajos nuevos al motor antiguo. Historial de reparaciones y límites previos en
[el índice de archivo](docs/archive/README.md).

Siguiente para el operador: reiniciar su backend cuando esté inactivo (`make studio`),
revisar las muestras en «Montaje» y usar «Vídeo largo» para el siguiente episodio.
La generación completa de UltimateBet la inicia el operador tras revisar las muestras.
