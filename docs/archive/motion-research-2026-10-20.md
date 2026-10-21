# Investigación histórica del 20/10/2026

Archivo histórico. No son instrucciones vigentes; consulta docs/motion-research.md.

# Selección del motor de motion documental

Investigación verificada el **20 de octubre de 2026** mediante documentación
oficial, API pública de GitHub y lectura de archivos fuente. La decisión de esta
fase es conservar **FFmpeg como ensamblador**, usar **ASS/libass para texto
sincronizado** y **Pillow para composiciones propias**. Ninguna alternativa se ha
demostrado superior con un benchmark de motores. La selección reduce integración,
dependencias y memoria y permite probar primero la calidad de fragmentos reales.
El estado de implementación y las muestras se documentan en [Montaje](editing.md).

## Qué se comprobó

Se consultaron todos los enlaces del encargo, sus licencias y ejemplos; se leyeron
implementaciones concretas, no sólo títulos de repositorios. Las fechas de abajo
son las del último commit observado en la rama predeterminada, obtenidas mediante
API GitHub; una fecha reciente no demuestra estabilidad ni compatibilidad local.

| Candidato | Mecanismo, dependencias y evidencia | Licencia observada y decisión |
| --- | --- | --- |
| [Remotion](https://www.remotion.dev/) | React/TypeScript, frames calculados por código, Chromium para render y codificación de vídeo. Commit `3557ab7c` del 20/10/2026. [TransitionSeries](https://www.remotion.dev/docs/transitions/) dispone de fade, slide, wipe y otros; el código controla solapes y límites de duración. | [Licencia propia](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md), no MIT: uso comercial gratuito para individuos y organizaciones elegibles de hasta 3 empleados; fuera de ese grupo exige licencia de empresa. La [tarifa de automatización](https://www.remotion.dev/docs/license/pricing) distingue productos automatizados. Alternativa viable, aplazada: añadir otro renderer no acredita por sí mismo mejor edición. |
| [Remotion captions](https://www.remotion.dev/docs/captions/create-tiktok-style-captions) | Agrupa tokens con tiempos en páginas, conserva límites por palabra y exige espacios iniciales. Su [función fuente](https://github.com/remotion-dev/remotion/blob/main/packages/captions/src/create-tiktok-style-captions.ts) no transcribe audio: consume alineación ya existente. | Misma familia de licencia. Se adopta la idea de separar segmentación temporal y presentación, con implementación propia y alineación Fish. No se añade una transcripción ni un servicio de voz. |
| [remotion-dev/skills](https://github.com/remotion-dev/skills) | Router oficial con guías específicas de creación, captions, render y Studio; leído `skills/remotion-best-practices/SKILL.md`. Commit `039e8a2f` del 19/10/2026. | No se encontró LICENSE/COPYING ni campo `license` en package.json en el árbol consultado. La instalación publicada por el autor no debe confundirse con una licencia MIT. No instalar ahora: sus instrucciones presuponen Remotion y duplicarían un motor que esta fase no usa. Reconsiderar si se incorpora Remotion. |
| [Motion Canvas](https://github.com/motion-canvas/motion-canvas) | TypeScript, Canvas 2D, generators y signals; editor Vite y exportación de secuencias o FFmpeg. Leído el ejemplo `quickstart.tsx`: `yield* all(...)` anima posición y color. [Guía](https://motion-canvas.io/docs/quickstart/) y [flujo](https://motion-canvas.io/docs/flow/) respaldan este modelo. Commit `7b91435c` del 02/07/2026. | Núcleo [MIT](https://github.com/motion-canvas/motion-canvas/blob/main/LICENSE); **el paquete @motion-canvas/ffmpeg declara GPLv3**. Buen candidato futuro para diagramas vectoriales complejos. Aplazado: obliga a mantener escenas TS y otro proceso/exportador para resolver composiciones que caben en el motor actual. |
| [MotionCraft](https://github.com/ahmdd4vd/MotionCraft) | Skill + CLI Node, plantillas Remotion y Three.js. Leídos `Headline.tsx`, package.json y guía de QA de píxeles: mide ancho real, equilibra dos líneas y avisa de overflow; QA exporta muestras, sin certificar todos los frames. Commit `8f487154` del 26/09/2026. | [MIT](https://github.com/ahmdd4vd/MotionCraft/blob/main/LICENSE) en su código; Remotion conserva licencia propia. Se toman patrones de diseño: tokens por estilo, medición tipográfica, eventos de sonido escasos y revisión del MP4. No copiar ni instalar pipeline: duplica voz, mezcla y render e introduce 3D que ahora no es prioritario. |
| [vertical-explainer-video](https://github.com/ryanhanley13/vertical-explainer-video) | Remotion, ElevenLabs, TS/Zod; 19 escenas declaradas. `StatScene.tsx` anima un número por spring; `transitions.ts` selecciona fade/slide/wipe. Commit `500b5980` del 19/02/2026. Su README enlaza un **placeholder** como preview, no una demo comprobable. | README afirma MIT, pero no hay archivo LICENSE/COPYING en el árbol ni licencia detectada por GitHub. **No reutilizar código con esa incertidumbre**. Sus familias semánticas son una referencia conceptual; su pipeline cambia Fish por otro proveedor y el objetivo es vertical, no documental horizontal. |
| [frei0r](https://github.com/dyne/frei0r) | ABI C/C++ de filtros por frame; host FFmpeg/MLT, sin GPU especial requerida. Leído tutorial de filtro y BUILD. Más de 100 plugins declarados por el proyecto; no es un planificador. Commit `618dde79` del 06/10/2026; release v3.6.0 del 27/09/2026. | [GPL-2.0 y licencias compatibles por archivo](https://github.com/dyne/frei0r/blob/master/COPYING). FFmpeg local admite el filtro frei0r, pero no se encontraron plugins en sus dos rutas estándar. No instalar: blur/color/transiciones necesarios ya existen en FFmpeg; falta una ventaja concreta que compense ampliar empaquetado y pruebas. |
| [FFmpeg](https://ffmpeg.org/ffmpeg-filters.html) | Ejecutable local **6.1.1-3ubuntu5**, comprobado con `-version` y `-filters`: ass/subtitles, drawtext, xfade, zoompan, crop, curvas, desenfoques, freeze, loudnorm, ducking y crossfade. | [LGPL-2.1+ o GPL según build](https://ffmpeg.org/legal.html). El build local incluye `--enable-gpl`, libass, libx264 y frei0r. Se mantiene; no se redistribuyen binarios nuevos en esta fase. |
| [ASS/libass](https://github.com/libass/libass) | Tipografía, capas, movimiento, fades, transformación y karaoke por tiempos. Ya integrado en Kitok. Commit libass `f61db567` del 17/09/2026; README identifica 0.17.5 del 24/06/2026. | libass [ISC](https://github.com/libass/libass/blob/master/COPYING). Seleccionado para texto; no sustituye por sí solo a un compositor de gráficos o stock. Escapar texto y medir layout sigue siendo responsabilidad de Kitok. |
| [MLT](https://www.mltframework.org/docs/) | Productores, playlists, filtros, transiciones y consumers; timeline descrito en XML y bindings. Leídos [arquitectura](https://www.mltframework.org/docs/framework/) y CMake. Commit `f0cafd23` del 18/10/2026. | Núcleo [LGPL-2.1](https://github.com/mltframework/mlt/blob/master/COPYING), varios módulos GPLv2/GPLv3; CMake activa componentes GPL por defecto. Aplazado hasta necesitar interoperabilidad de timeline o editor externo: duplicaría la orquestación de Kitok. |
| [Manim Community](https://github.com/ManimCommunity/manim) | Python, escenas programadas y exportación con Cairo/OpenGL/FFmpeg. Alternativa útil para diagramas científicos o matemáticos; [instalación](https://docs.manim.community/en/stable/installation/) añade su propia cadena de herramientas y LaTeX si se utiliza. Commit `b31c77e1` del 16/10/2026. | [MIT](https://github.com/ManimCommunity/manim/blob/main/LICENSE). Aplazado: no aporta ventaja demostrada para rótulos, stock o fechas. Reabrir sólo para un diagrama que el compositor simple no resuelva. |
| [Pillow](https://pillow.readthedocs.io/en/stable/about.html#license) | Rasterización local en Python, ya disponible. Puede medir texto y dibujar gráficos sin servidor, navegador ni modelo generativo. | Licencia HPND/PIL del proyecto. Seleccionado para gráficos propios cacheados; fuentes e imágenes conservan sus licencias separadas. |

No se ejecutaron instaladores, scripts de terceros ni proveedores. El código
consultado y las imágenes de referencia se descargaron sólo a una carpeta temporal
de investigación; no pasan a ser recursos de producción ni se incorporan al repo.

## Qué muestran realmente los ejemplos

Se descargaron los GIF `media/pi-v2-loop.gif` y `media/hindsight-loop.gif` de
MotionCraft: cada uno tiene 120 frames a 480×270. Se extrajeron e inspeccionaron
cuatro momentos por GIF. Las composiciones observadas usan espacio claro, títulos
cortos, acento azul, tarjetas de interfaz y pequeños objetos 3D. Son referencias
visuales concretas para jerarquía y legibilidad, pero no una prueba de montaje
documental, escucha ni rendimiento de un episodio. No se afirma haber visto sus
vídeos completos con sonido. El enlace original está en su
[README](https://github.com/ahmdd4vd/MotionCraft#made-with-motioncraft).

En Remotion y Motion Canvas se inspeccionaron documentación y código de ejemplos;
no se midieron sus tiempos de render en esta máquina. Vertical-explainer no aportó
un preview real verificable en el README. Las capturas externas son material de
investigación, no imágenes con licencia aprobada para publicar en un documental.

## Ajuste al equipo de 4 GB VRAM / 8 GB RAM

La recomendación es render secuencial de escenas, resolución 1080p, caché por
contenido/configuración y pocos procesos simultáneos. Un frame RGBA 1920×1080
ocupa unos 7,9 MiB sin comprimir: un segundo a 30 fps ocuparía unos 237 MiB si se
retuviera completo. Conviene enviar frames de forma incremental, no acumularlos
en listas. NVENC puede codificar cuando el probe real funciona; no acelera de
forma automática todos los filtros CPU ni el dibujo Pillow.

Remotion y Motion Canvas son técnicamente candidatos para 2D, pero compatibilidad
no equivale a benchmark favorable. La [documentación de GPU de Remotion](https://www.remotion.dev/docs/gpu)
advierte que Chromium headless puede deshabilitar GPU; un parámetro `--gl` tampoco
demuestra que cada paso utilice la RTX. No se necesita Three.js para texto, curvas,
fechas, stock o diagramas planos. Se conserva el piloto histórico de póker, sin
convertirlo en requisito del nuevo modo ni borrar archivos existentes.

## Repertorio candidato y reglas de dirección

Estas son **familias de diseño propuestas**, no una afirmación de que todas estén
implementadas o aprobadas. La galería y la implementación vigentes determinan
cuáles se aceptan finalmente.

| Familia | Candidatos reutilizables | Motivo editorial |
| --- | --- | --- |
| Texto | Pregunta, frase por palabras, palabra clave, cita atribuida | Preguntar, enfatizar o separar voz propia de una cita. |
| Contexto | Cantidad, fecha/timeline, identidad, lugar, capítulo | Mostrar información explícita en el guion; un número aislado no autoriza una gráfica. |
| Explicación | Comparación de barras, diagrama de pasos, documento resaltado | Sólo valores con unidades compatibles; pasos/documento auténtico aportados. No inventar hechos ni simular pruebas. |
| Plano | Zoom lento, paneo, congelación, foco por desenfoque, tratamiento de color | Dirigir la mirada, mantener una imagen relevante o distinguir época/ambiente. |
| Unión | Disolución, paso por negro, wipe direccional | Continuidad, pausa o cambio de espacio/tiempo; el corte simple sigue siendo válido. |

Son 20 candidatos agrupados en cinco familias. Deben parametrizar texto, paleta,
tipografía, duración y movimiento. Propuesta de diversidad: impedir repeticiones
inmediatas de composición, espaciar pantallas de énfasis y conservar tramos de
stock sin rótulos. Las preferencias de canal eligen entre presets; el calendario
de escenas, la selección y el dibujo son deterministas, sin LLM por frame.

La alineación Fish real tiene prioridad. Cuando sólo existe tiempo por frase,
no fingir precisión por palabra: usar aparición de frase y registrar ese límite.
Un contador necesita un valor literal respaldado; una comparación necesita dos
valores comparables y sus etiquetas. Si no hay evidencia suficiente, conservar
stock y narración. Toda muestra debe revisarse como MP4 con voz y música, además
de checks de decode, negros, sonoridad, duración y capturas de legibilidad.

## Uso comercial, automatización y continuidad

La licencia de una herramienta no concede derechos sobre sus demos, stock,
fuentes, música, marcas o voces. El software libre puede utilizarse para procesar
material propio comercialmente; las obligaciones al redistribuir el software son
otra cuestión. La [FAQ oficial GNU sobre salida](https://www.gnu.org/licenses/gpl-faq.en.html#WhatCaseIsOutputGPL)
explica que la licencia del programa generalmente no se aplica al resultado de
convertir datos del usuario, con excepciones si incorpora material protegido del
propio programa. Conservar autor, licencia y procedencia de cada recurso; ninguna
elección de renderer garantiza monetización ni ausencia de Content ID.

Remotion requiere volver a comprobar elegibilidad si crece el equipo o cambia el
modelo de automatización; su licencia menciona cambios futuros para 5.0. Las
licencias ambiguas de vertical-explainer y skills oficiales impiden asumir permiso
de redistribución de código. No se instala una skill por popularidad: una skill
local de dirección/QA sólo aporta valor si usa los comandos reales de Kitok,
reutiliza Fish, impone revisión de muestras y evita reintroducir proveedores.
Las herramientas aplazadas se reabren con una necesidad y una prueba pequeña;
no sustituir el motor Native sin evidencia visual y operativa superior.
