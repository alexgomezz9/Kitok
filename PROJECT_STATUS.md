# Estado vigente de Kitok

Actualizado: 2026-10-20. Rama **feature/documentary-motion**, base **main bfd43c5**.
Manual: [GUIA.md](GUIA.md). [Motion y muestras](docs/motion.md),
[audio y derechos](docs/audio.md), [decisión tecnológica](docs/motion-research.md).

## Revisión tras el feedback visual

El operador rechazó la primera presentación por parecer tarjetas/subtítulos.
Las candidatas revisadas usan títulos grandes con entrada enmascarada por líneas,
diagramas de objetos/conexiones escalonados y énfasis sobre stock con degradado,
sin repetir toda la frase como subtítulo. Se retiraron los planos señalados de
solitario, tienda de apps y blackjack; el stock sigue siendo ilustrativo.
La revisión independiente cerró los defectos visuales concretos y de continuidad;
esto **no acredita aprobación profesional ni escucha continua**.

## Incidente real de audio y compatibilidad

Trabajo `lf_cf5e16bb422547aabfb4f5b8b9ef131a` fallido: narración existente
654,733 s, SHA `98c30397e5f542272d07cd757c443c1ffaf2568b09d37f1b540a18636f3d0106`.
Decode completo, guion/voz/modelo/velocidad y recibo Fish coincidentes; 1.849 tokens
alineados, incluidos 84 de duración cero. Ninguna nueva solicitud Fish.

Reproducción offline exacta con músicas cacheadas y nueve SFX: la mezcla fallida
mide 654,599 s (−134 ms frente a tolerancia 80 ms), −15,99 LUFS, LRA 3,50 y
−1,80 dBTP. Sólo falla duración. La corrección del reloj de muestras ha producido
654,733 s con las mismas medidas de sonoridad, sin padding ni límites ampliados.
Regresión de seis minutos con MP3 sin Xing, música automática, crossfade y SFX:
pasa con el arreglo y falla con el código anterior. MP4 real de 22 s alrededor del
cambio musical: 660 frames 4:2:0, AAC y decode completos; −15,28 LUFS / −2,11 dBTP.
Recuperación estricta disponible en UI/API/CLI: auditoría de sólo lectura y
confirmación explícita de SHA/fingerprint, mismo ID, bloqueo y workspace nuevo.
No construye cliente Fish ni proveedor de stock con red; detiene recursos ausentes.
58 pruebas de recuperación/estudio correctas y revisión independiente sin bloqueos.
El diagnóstico inicial conservó el trabajo fallido; después el operador inició
dos recuperaciones que se detuvieron en el preflight descrito a continuación.
[Procedimiento de recuperación](GUIA.md#recuperar-un-largo-fallido-conservando-la-voz-pagada).

Reintentos del operador a las 17:07 y 17:08: fallo distinto, antes de mezcla o Fish.
El preflight exigía 20 búsquedas originales aunque el montaje utiliza 17; faltaban
`computer security code` y `empty poker table`, ninguna usada. Corregido para
validar sólo las consultas del timeline durante recuperación, conservando el
preflight anterior a Fish en generación nueva. Regresión reproduce el fallo con
código anterior; **104 pruebas de Native/recuperación/estudio/shorts** correctas
y revisión independiente sin hallazgos. Prueba del renderer real hasta el límite previo a mezclar: 17
consultas y 94 assets locales válidos, cero red/Fish, estado y hashes originales
intactos. Evidencia `local/audio-failure/preflight-followup-1792509093486690083/`.
No se relanzó el episodio ni se alteraron los dos errores de recuperación guardados.


La nueva evidencia del operador incluye fallo en Kitok y Windows descargado.
Auditoría de todos los fotogramas encontró seis MP4 con cambio intermedio de
High/4:2:0 a High 4:4:4 en transiciones; la cabecera inicial no lo revelaba.
Renderer corregido después de `xfade`, formato de salida fijado y caché invalidada.
23 copias nuevas `_compat1`: 5.640 frames uniformes 4:2:0, decode completo y AAC
idéntico; originales y metadatos preservados con respaldo. Windows real no está
verificado en este host Linux. [Detalles y reparación](docs/motion.md).

## Generación nueva: cobertura real de stock

Tras el reintento del operador, la mezcla pasó pero el montaje falló a las 17:30
por `shot_0068`. Había dos ventanas inválidas: Pexels declaraba 10/8 s, pero los
streams de vídeo miden 9,566667/7,48 s. El cálculo aleatorio pedía fines
9,620250/7,801471 s. El segundo contenedor dura 7,53 s: tampoco sirve como límite.
Native calcula ahora las entradas con vídeo real y redondeo a FPS, para generación
nueva y recuperación. Un recurso entero insuficiente se rechaza antes de mezclar.
El render valida todos los planos antes de iniciar el primero, con valores medidos.

Prueba desde cero: voz/Pexels simulados, música automática, crossfade, SFX,
gráficos, render/mux reales y MP4 4:2:0/AAC decodificado completo. Pasa con el arreglo
y falla con el cálculo anterior. Regresión de una escena 68 inválida se detiene
antes de encoder/workspace. Plan real de 120 escenas: 114 ventanas de stock y seis
placas verificadas sin render completo, sin Fish/red y sin modificar el estado.
Evidencia: `local/audio-failure/stock-window-followup-1792510735414464988/`.
El operador prioriza crear de nuevo desde cero; el agente no ha generado voz nueva
ni lanzado el episodio. Gate local: **821 Python, 22 React, build y cinco E2E**
correctos; docs/studio correctos y revisión independiente sin hallazgos. Backend
local reiniciado inactivo y salud HTTP 200 comprobada. Fuentes compartidas por
vídeos nuevos y recuperación; no hace falta reiniciar de nuevo para usar el cambio.

## Muestras vigentes

En `outputs/motion-gallery/`, **Montaje → Galería documental → Reproducir muestra**:

| ID | Duración | LUFS / dBTP |
| --- | --- | --- |
| `ub_opening_v7_compat1` | 31 s, 1080p | −16,09 / −1,83 |
| `ub_development_v7_compat1` | 31,5 s, 1080p | −15,96 / −1,79 |
| `ub_revelation_v7_compat1` | 29,5 s, 1080p | −16,10 / −1,85 |
| `generalization_mfa_v3_compat1` | 20 s, 1080p | −15,74 / −1,78 |

Además, 19 efectos individuales `effect_r2_*_compat1` de cuatro segundos: 23 ítems activos.
Las tres UB conservan voz/música anteriores y referencia A/B con audio idéntico.
MFA demuestra reutilización visual sin narración nueva. Versiones anteriores
archivadas en metadata, sin eliminar MP4; 28 hashes de originales comprobados
sin cambios y recibo en `local/motion-phase/archival-receipt-2026-10-20.json`.
El recorrido Native anterior con proveedores locales/sockets bloqueados se conserva
como prueba técnica histórica, fuera de la selección visual vigente.

## Capacidades y límites

- Native/FFmpeg + ASS/Pillow, 19 composiciones/tratamientos, tres presets y caché.
  Three.js/póker permanece opcional histórico, fuera del director documental.
- MotionDirector acotado a preguntas, cifras, fechas, nombres explícitos y conceptos
  técnicos. Mantiene densidad/diversidad y anclas Fish validadas; si faltan, declara
  estimaciones. No resume preguntas ni infiere una acción mediante verbos sueltos.
  Titulares breves, diagramas complejos y símbolos requieren decisiones de plan.
- Vídeo largo ofrece voz, música automática/manual/desactivada y Básico/Documental.
  Guardar/comprobar no contacta proveedores. Generar es una acción explícita.
  20 músicas CC BY 4.0, seis SFX originales, 11 voces/15 previews y favoritos/canales;
  narrador Loose Thread original conservado. Dos ambientes musicales por trabajo.
- Stock/licencias/autores documentados; Content ID desconocido. Las voces nuevas
  tienen textos distintos; las históricas plain/tags permiten comparación común.
  Metadatos licensed de Fish no equivalen a consentimiento universal.

## Verificación y siguiente paso

- 2026-10-20, cobertura stock: `make verify` pasó **821 Python, 22 React y build
  TypeScript/Vite**. Los **cinco E2E** pasaron en fixture temporal, puerto 18241
  y traducción de Origin exclusiva del fixture, preservando el backend del operador.
  Logs `/tmp/kitok-stock-final-verify.log` y `/tmp/kitok-stock-e2e.log`.
  `make studio-check`, `make docs-check` y revisiones independientes correctos.
- Prueba real de mezcla con código final `sample-clock-v2`: 654,733 s,
  −15,99 LUFS / LRA 3,50 / −1,80 dBTP. WAV idéntico al usado en el MP4 corto;
  voz, alineación y selección intactas, cero intentos de red. Recibo local:
  `local/audio-failure/final-1792507776156545090/confirmed.wav.json`.
  MP4 y QA en `outputs/evaluation/lf_cf5e16bb422547aabfb4f5b8b9ef131a_recovery_check/`.
- Muestra compatible de desarrollo completada en Chromium silenciado a 2×:
  945 frames, dos perdidos, sin error de decode/página, Range 206 y créditos 200.
  El intento con sonido se detuvo en 5 s sin error bajo carga del host: **no acredita
  reproducción audible continua ni Windows real**. Decodificación completa y
  formato uniforme comprobados por separado en las 23 copias.
- Checkpoints publicados: `6d9a62f` (vídeo), `c8d12aa` (mezclador), `5176130`
  (recuperación); SHA remoto comprobado. [CI de vídeo correcto](https://github.com/alexgomezz9/Kitok/actions/runs/39442296453)
  y [CI de audio correcto](https://github.com/alexgomezz9/Kitok/actions/runs/39442817758).
  [CI de recuperación](https://github.com/alexgomezz9/Kitok/actions/runs/39443108621).
- Sin nueva síntesis Fish, render completo UltimateBet, publicación ni merge a main.
  Job fallido, voz, alineación, cachés, temporales, cola y credenciales conservados.
  Buffer y OAuth no se modificaron. El límite histórico de restauración de cola
  del 19/10 sigue registrado en `local/backups`; no hay hash previo que certifique
  cambios posteriores.

Siguiente: el operador puede actualizar la página, crear un borrador nuevo y usar
**Comprobar → Guardar → Generar vídeo largo**. La recuperación del trabajo anterior sigue disponible,
pero no es necesaria para probar un vídeo nuevo. Los originales se conservan.
No se lanzó UltimateBet completo desde el agente. Windows y aprobación audiovisual
siguen pendientes del operador.
