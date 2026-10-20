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

La galería carga un único vídeo por clic, muestra primero las muestras y separa
los contactos estáticos del reproductor. El error «could not be decoded» fue
reportado en enlaces del chat: no se reprodujo desde Kitok en Chromium. No se
atribuye una causa no comprobada ni se promete que ese error externo esté resuelto.
Los nuevos MP4 usan H.264/yuv420p y AAC; el renderer convierte PCM una vez a AAC
sin normalizar otra vez, conserva el máster y copia AAC ya aprobado sin recodificar.

## Muestras vigentes

En `outputs/motion-gallery/`, **Montaje → Galería documental → Reproducir muestra**:

| ID | Duración | LUFS / dBTP |
| --- | --- | --- |
| `ub_opening_v7` | 31 s, 1080p | −16,09 / −1,83 |
| `ub_development_v7` | 31,5 s, 1080p | −15,96 / −1,79 |
| `ub_revelation_v7` | 29,5 s, 1080p | −16,10 / −1,85 |
| `generalization_mfa_v3` | 20 s, 1080p | −15,74 / −1,78 |

Además, 19 efectos individuales `effect_r2_*` de cuatro segundos: 23 ítems activos.
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

Siguiente: revisar movimiento y escuchar las muestras nuevas en el estudio. Tras
aprobar calidad, el operador podrá usar **Vídeo largo → Documental enriquecido →
Comprobar → Guardar → Generar**. No lanzar UltimateBet completo desde un agente.
