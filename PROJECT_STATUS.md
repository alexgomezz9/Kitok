# Estado vigente de Kitok

Actualizado: 2026-10-20. Rama **feature/documentary-motion**, base **main bfd43c5**.
Manual: [GUIA.md](GUIA.md); [montaje](docs/editing.md),
[muestras](docs/motion.md), [audio/licencias](docs/audio.md),
[capacidades y límites](docs/capabilities.md).

## Incidente vigente: reloj de vídeo documental

El operador lanzó `lf_2b8be75387384569a3cc20b4292166ed` desde el estudio.
Se renderizaron 120 planos, pero la validación final rechazó vídeo de
654,533333 s / 19.636 fotogramas frente a 654,733333 s / 19.642 esperados.
El audio sí duraba 654,733 s. Seis cortes perdían un frame; siete planos tenían
inicio de vídeo a 0,033008 s. Los recortes fraccionales de stock 29,97/23,976 FPS
conservaban esa fase antes de `fps`, y el límite temporal truncaba planos.

CLI y web comparten Native. El JSON histórico básico con música manual usa otra
rama; su motor ya reiniciaba PTS. El documental/música de biblioteca activaba
el render editorial nuevo. No era un fallo del transporte React.

Corrección: reiniciar PTS antes de FPS, emitir el número exacto de fotogramas
entre límites globales y validar inicio cero, frames y duración en cada plano,
caché, ensamblado y MP4. No se amplían tolerancias ni se añade relleno.
Errores medidos y `*.validation.json` persistentes; progreso por plano en estudio.
Caché anterior invalidada. Regresión real de 12 escenas: código previo entrega
350/360 frames y falla; corregido produce 360 exactos. Cobertura adicional de
caché defectuosa, fade/dissolve/wipe y error API sin reintentos automáticos.
Revisión independiente cerrada sin P0/P1/P2; 99 pruebas focales independientes.

Se han corregido sólo los siete planos con reloj defectuoso, reutilizando los
otros 113 y la mezcla existente. Candidato exclusivo, sin alterar el job fallido:
`outputs/evaluation/lf_2b8be75387384569a3cc20b4292166ed_frame_repair_1792512967449183090/UltimateBet_complete_timing_fixed.mp4`.
19.642 frames, inicio cero, vídeo 654,733333 s / audio 654,733 s.
`repair.json`, relojes de escenas y hashes anteriores en esa misma carpeta.
Cero solicitudes Fish/red; hashes de originales y estado del operador intactos.
Decodificación completa correcta: 19.642 frames uniformes 4:2:0 y AAC;
mezcla de entrega −16,00 LUFS / LRA 3,50 / −1,77 dBTP.
Los 420 archivos originales mantienen sus hashes después de la QA.
No se ha vuelto a renderizar todo el documental ni marcado el trabajo como terminado.

## Correcciones anteriores comprobadas

- Mezclador `sample-clock-v2`: MP3 existente de 654,733 s producía mezcla de
  654,599 s (−134 ms, margen 80 ms). Sólo fallaba duración; −15,99 LUFS,
  LRA 3,50 y −1,80 dBTP válidos. Reloj de muestras corregido sin padding ni
  relajar límites. Regresión de seis minutos, música automática/crossfade/SFX.
  WAV real final 654,733 s con los mismos niveles; voz/alineación conservadas.
- Recuperación estricta UI/API/CLI: auditoría de sólo lectura, SHA/fingerprint
  explícitos, mismo ID y bloqueo compartido, workspace nuevo. No construye
  cliente Fish ni descarga stock. Preflight comprueba las búsquedas realmente
  usadas: 17 frente a 20 originales. [Procedimiento](GUIA.md#recuperar-un-largo-fallido-conservando-la-voz-pagada).
- Cobertura stock: API 10/8 s frente a streams 9,566667/7,48 s. Native elige
  entradas con duración de vídeo medida y margen de redondeo global. Las 114
  ventanas reales pasan; todas se validan antes del primer render. Prueba nueva
  de 12 s con proveedores simulados y FFmpeg real correcta, sin probar Fish real.
- Compatibilidad: seis muestras cambiaban de 4:2:0 a 4:4:4 dentro de `xfade`.
  Formato fijado tras transición y en salida. 23 copias `_compat1`, 5.640 frames
  uniformes 4:2:0, decode completo y AAC idéntico; originales preservados.
  Windows real no está verificado en este host Linux.

## Muestras y límites

Galería activa: `ub_opening_v7_compat1` (31 s),
`ub_development_v7_compat1` (31,5 s), `ub_revelation_v7_compat1` (29,5 s),
`generalization_mfa_v3_compat1` (20 s) y 19 efectos individuales de cuatro segundos.
La primera presentación fue rechazada; estas candidatas usan máscaras tipográficas,
símbolos/conexiones y stock ilustrativo. Sigue pendiente escucha continua y
aceptación audiovisual del operador. QA técnica no acredita calidad narrativa.
Native/FFmpeg + ASS/Pillow; MotionDirector acotado, sin LLM por plano ni editor
visual de timeline. [Decisión tecnológica](docs/motion-research.md).

## Verificación y siguiente paso

- Corrección publicada: `ecb1ac7`; SHA remoto comprobado, main intacta.
  [CI del arreglo](https://github.com/alexgomezz9/Kitok/actions/runs/39457274652).
  Checkpoint anterior `a7eb776`, CI 39451469106 correcto.
- Corrección actual: `make verify` correcto: **826 Python (320,92 s), 22 React
  y build TypeScript/Vite**. `make docs-check` y `make studio-check` correctos.
  **Cinco E2E** aislados en puerto 18241 correctos (18,5 s), sin tocar el backend
  del operador. Logs `/tmp/kitok-final-clock-{verify,e2e}.log`.
- Backend del agente cerrado a petición del operador. El backend que éste haya
  iniciado no se toca. Debe reiniciarlo él cuando esté inactivo para cargar cambios;
  actualizar la página no cancela un trabajo ni recarga el código Python.
- No nueva síntesis Fish, borrado de cachés/temporales, publicación ni merge a main.
  Trabajos anteriores, voz, alineación y cola se conservan. Buffer/OAuth intactos.

Siguiente: el operador puede abrir el candidato completo y reiniciar su backend
cuando esté inactivo para cargar la corrección. El job conserva el fallo histórico;
el candidato está en la ruta local indicada. No lanzar otra generación completa
automáticamente. Windows, escucha continua y aceptación siguen pendientes.
