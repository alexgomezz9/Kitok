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
El trabajo original permanece fallido e intacto; no se retomó el episodio completo.
[Procedimiento de recuperación](GUIA.md#recuperar-un-largo-fallido-conservando-la-voz-pagada).

La nueva evidencia del operador incluye fallo en Kitok y Windows descargado.
Auditoría de todos los fotogramas encontró seis MP4 con cambio intermedio de
High/4:2:0 a High 4:4:4 en transiciones; la cabecera inicial no lo revelaba.
Renderer corregido después de `xfade`, formato de salida fijado y caché invalidada.
23 copias nuevas `_compat1`: 5.640 frames uniformes 4:2:0, decode completo y AAC
idéntico; originales y metadatos preservados con respaldo. Windows real no está
verificado en este host Linux. [Detalles y reparación](docs/motion.md).

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

- `make verify-browser`: **781 Python, 21 React, build TypeScript/Vite y cinco E2E**,
  correctos. `make studio-check`, `make docs-check` y revisión independiente correctos.
  Evidencia local de gate: `/tmp/kitok-motion-revision-final.log`.
- QA de los nuevos MP4: decode completo, geometría, duración, LUFS/pico y A/B;
  contactos y entradas/salidas inspeccionados. Reproducción por HTTP en Chromium,
  Range 206 y créditos comprobados. El entorno de navegador registró fotogramas
  perdidos: no acredita rendimiento sostenido en el equipo del operador.
- Checkpoints correctivos publicados: `a7088ac` (galería), `ecd84c6` (AAC),
  `9b7ce83` (compositor). SHA remoto comprobado y
  [CI del compositor correcto](https://github.com/alexgomezz9/Kitok/actions/runs/39421185950).
- Sin nueva síntesis Fish, render completo UltimateBet, publicación ni merge a main.
  Original de 652,6 s, piloto de 76 s, cola y credenciales conservados. Buffer y OAuth
  no se modificaron. El límite histórico de restauración de cola del 19/10 sigue
  registrado en `local/backups`; no hay hash previo que certifique cambios posteriores.

En curso: gate completo y CI de los checkpoints del incidente. Siguiente operación
del titular para este trabajo: **Vídeo largo → ficha fallida → Revisar recuperación
sin generar → Recuperar montaje usando esta voz · sin Fish ni red**. La segunda
acción monta el episodio completo; no usar «Generar» ni crear otro borrador para
recuperar esta narración. Revisar además las copias `_compat1` en Windows y
escuchar antes de aprobar la calidad. No lanzar UltimateBet completo desde un agente.
