# Estado vigente de Kitok

Actualizado: 2026-10-20. Rama **feature/documentary-motion**, base **main bfd43c5**.
Manual operativo: [GUIA.md](GUIA.md). Decisiones y licencias: [investigación](docs/motion-research.md).

## Revisión abierta por feedback del operador

El 20/10 el operador rechazó el lenguaje visual de las primeras muestras por
parecer tarjetas/subtítulos estáticos. Su calidad editorial **no está aprobada**;
se está revisando primero una prueba corta, sin render completo ni nueva Fish.
El error «could not be decoded» se reportó al abrir enlaces del chat. No se
reprodujo en Kitok: los 24 vídeos originales llegaron al final por HTTP en Chromium
(en dos ejecuciones). Una muestra histórica conserva audio PCM; el renderer entrega AAC cuando el
máster no es AAC, sin normalizar de nuevo ni reemplazar el original. Pruebas
reales PCM/AAC correctas; AAC conserva su audio decodificado idéntico.
La galería ahora carga un único reproductor por clic, prioriza muestras y separa
el mosaico estático del vídeo. Verificación: 21 React, build, API Range 206 y
reproducción real; esto no explica ni resuelve por sí solo el error del chat.

## Capacidades comprobadas

- Documental enriquecido integrado en Vídeo largo: Native/FFmpeg, ASS y Pillow;
  19 composiciones/tratamientos, tres presets y caché por escena. Three.js/póker
  se conserva opcional histórico, fuera de la selección automática documental.
- MotionDirector conservador: preguntas, cantidades literales, fechas, nombres
  explícitos y conceptos técnicos acotados; diversidad, densidad y sincronía Fish
  validada. Diagramas/documentos complejos requieren plan. [Contrato y límites](docs/motion.md).
- Frontend: voz, música Automática/Desactivada/Manual y Básico/Documental enriquecido.
  Guardar/comprobar no contacta proveedores. Galería con reproducción, descarga,
  comparación A/B y créditos. Generar es una acción explícita que puede usar Fish/Pexels.
- 20 músicas Incompetech CC BY 4.0 con hashes, procedencia y atribución; seis SFX
  originales. Selección por tono/canal, rotación, dos ambientes con crossfade,
  ducking y medición de mezcla. 11 voces y 15 muestras, incluidas alternativas
  españolas; favoritos y asignación por canal. Loose Thread conserva su voz
  predeterminada `e686ae649ee44f219a108aacba206c1a`. [Audio y derechos](docs/audio.md).

## Evidencia audiovisual local

En `outputs/motion-gallery/`, accesible desde **Montaje → Galería documental**:

| Muestra vigente | Duración | LUFS / dBTP |
| --- | --- | --- |
| `ub_opening_v5` | 31 s, 1080p | −16,09 / −1,83 |
| `ub_development_v5` | 31,5 s, 1080p | −15,96 / −1,79 |
| `ub_revelation_v5` | 29,5 s, 1080p | −16,10 / −1,85 |
| `generalization_mfa_v1` | 20 s, 1080p | −15,74 / −1,78 |
| `native_roundtrip_v2` | 31,07 s, 720p | −16,10 / −1,81 |

Además, 19 efectos individuales de cuatro segundos. Las tres muestras UltimateBet
reutilizan Fish/alineación/stock existentes y comparan imagen con audio A/B idéntico.
MFA demuestra reutilización visual sin narración nueva. El recorrido Native usa
proveedores locales simulados, sockets externos bloqueados y bloqueo real por ID.
Versiones anteriores conservadas, fuera de la galería vigente.

QA: decodificación completa, duración, geometría, hashes, LUFS/pico y contactos
visuales. Reproducción puntual real en Chromium de las cinco muestras, audio/vídeo
avanzando, créditos HTTP 200 y cero errores de página. No acredita escucha continua
ni aprobación editorial: ambas quedan al operador. Stock ilustrativo con autores
consultados por API oficial Pexels; cachés históricas pueden carecer de autor.
Content ID desconocido. Los previews nuevos de voces tienen textos distintos;
las muestras históricas plain/tags sí permiten comparar el mismo texto. La marca
licensed de Fish no acredita consentimiento universal.

## Verificación y continuidad

- 20/10: `make verify-browser` correcto: **764 pruebas Python, 20 React, build
  TypeScript/Vite y cinco E2E**. `make studio-check` y `make docs-check` correctos.
  Revisión independiente de corrección, adversarial y entrega cerrada sin pendientes
  funcionales P0/P1/P2; la aceptación audiovisual humana sigue pendiente.
- Checkpoints coherentes publicados desde `fba1361` hasta `9e47f88`, incluido audio,
  compositor, sincronía, atribución e integración. SHA remoto `9e47f88` comprobado;
  [CI de integración correcto](https://github.com/alexgomezz9/Kitok/actions/runs/39406713963).
  Este estado documenta esa evidencia; el checkpoint de cierre no cambia el motor.
- Skill local `kitok-audiovisual-qa` instalada y validada. No se añadió otro motor,
  MCP, hook ni agente autónomo de producción. Google/CTR y perfiles multicanal
  completos siguen pendientes. Buffer y permisos YouTube no se modificaron.
- Sin síntesis Fish nueva, render completo, publicación ni merge a main en esta fase.
  Original de 652,6 s y piloto de 76 s conservados. Credencial Google local ignorada,
  no leída. La restauración de cola del 19/10 y su límite siguen registrados en
  `local/backups`: sin hash previo que certifique cambios locales posteriores.

Siguiente paso: corregir y revisar el movimiento y composición de las muestras
cortas antes de volver a pedir aceptación audiovisual. Después, el operador podrá usar
**Vídeo largo → Documental enriquecido → Comprobar → Guardar → Generar** para un
trabajo nuevo. No lanzar UltimateBet completo desde un agente durante esta fase.
