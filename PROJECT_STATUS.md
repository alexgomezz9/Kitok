# Estado vigente de Kitok

Actualizado: **2026-10-21**. Rama **feature/documentary-motion**, base main
`bfd43c5`. Integración final en main autorizada por el encargo, todavía pendiente.
Manual: [GUIA.md](GUIA.md); contrato: [montaje](docs/editing.md);
[efectos](docs/motion.md); [audio](docs/audio.md); [capacidades](docs/capabilities.md).

## Editor final en verificación

- Native comparte fotos, documentos, stock, once cámaras, ASS, caché y FFmpeg.
  JSON parcial: archivo y frase bastan; efectos explícitos y stock automático
  cubren una timeline sin huecos. Anclas Fish comprobadas o estimación declarada.
- Disolución/barrido/slide/foco usan continuación móvil, sin congelar ni repetir
  cola. Si falta margen opcional de stock, corte registrado. Fades visuales .6/.8 s
  en documental, dentro de duración; no se funde la voz ni se amplían tolerancias.
- Nuevo efecto: fecha mecanografiada con foco. Identidad y resaltado sobre documento
  aportado mejorados. Parallax sin capas se rechaza; Three.js/póker sigue histórico.
- Estudio de fotos/importación/voz reutilizada implementado, comprobado localmente
  y verificado también en Chromium con upload real, imagen+frase, comprobación
  y borrador en workspace temporal. Navegar/guardar/comprobar no llama proveedores.
  Nuevo montaje auditado usa otro ID; recuperación del mismo ID se conserva.
- MP4 reales actuales: `outputs/motion-gallery/final_ub_opening_r2/preview.mp4`
  (31,5 s/945 frames/1080p, decode completo y audio A/B idéntico), conservada y
  sustituida por `final_ub_opening_r3` tras detectar blackjack. Retrato
  `final_ub_portrait_r1` (27,8 s) y `final_mfa_r1` (20 s), mismo compilador.
  Colección nueva: 43 demos; revisión de reproducción/fotogramas en curso.

## Evidencia y límites actuales

- Motor publicado `dc4924c`, SHA remoto igual; CI 39676770736 en ejecución.
- 108 pruebas core Native/visuales/recuperación correctas (16,51 s); dos recorridos
  Native de 6 s con FFmpeg real y proveedores simulados. Render/cámara/motion:
  53 pruebas de renderer/reloj/cues correctas (42,32 s), además de regresiones de
  continuidad y retardo global. Estudio/API: 66 pruebas correctas (6,16 s).
- 25 React, build TypeScript/Vite y cinco E2E aislados correctos (18,2 s).
  `make docs-check` y `make studio-check` correctos; gate completo pendiente.
- Revisión independiente de corrección y adversarial: hallazgos P2 de intervalos,
  defaults, validación antes de Fish y auditoría de voz corregidos y releídos.
- Remotion real 4 s/120 frames: 31,50 s/654.240 KB RSS frente a Native revisado
  11,53 s/279.664 KB; mismo audio. Sin dependencia nueva de producción.
  [Medición, fuentes y límites](docs/motion-research.md).
- 12 inputs protegidos conservan hashes. No nueva Fish ni documental completo,
  publicación, borrado de cachés o modificación del backend del operador.
  Windows, escucha continua y aceptación audiovisual siguen sin comprobar.

Los arreglos anteriores de reloj exacto y mezcla se conservan; historial y rutas
medidas mediante [el índice de archivo](docs/archive/README.md). MPT sólo recupera
IDs históricos: no se envían trabajos nuevos ni se afirma dependencia cero histórica.

Siguiente: terminar demos/reproducción, ejecutar gates, checkpoints/CI e integración
segura autorizada. El operador reinicia su backend cuando esté inactivo; no se toca
su proceso desde este encargo.
