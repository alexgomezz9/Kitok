# Qué hace Kitok y cómo reutilizarlo

Kitok genera shorts y largos a partir de un guion aportado, y permite mejorar un
montaje con audio ya aprobado. Automatiza ejecución, cachés y comprobaciones
técnicas. Las decisiones de investigación, guion y dirección editorial siguen
necesitando una persona o un agente que prepare entradas explícitas.

Esta guía describe el código actual y su frontera de reutilización. Para operar,
consulta [GUIA.md](../GUIA.md); para la evidencia fechada de ejecuciones reales,
[PROJECT_STATUS.md](../PROJECT_STATUS.md). El [índice](README.md) separa manuales
vigentes, propuestas y archivo histórico. No hay una medición que permita asignar
un porcentaje de automatización al proyecto.

## Responsabilidades por etapa

«Kitok solo» significa que, recibida una entrada válida y una orden explícita,
el programa ejecuta esa etapa. No implica que elija por su cuenta el siguiente
tema, apruebe el vídeo o mantenga un canal desatendido. Un agente puede ayudar
con las tareas editoriales; el operador también puede hacerlas sin agente.

| Etapa | Kitok solo, ya implementado | Agente o editor: qué debe decidir | Operador y límite actual |
| --- | --- | --- | --- |
| Tema y documentación | Guarda el guion y los borradores aportados. | Investigar, contrastar fuentes, elegir enfoque, estructura y afirmaciones. | Fijar objetivos y revisar hechos. No hay investigación ni guion autónomos dentro de Kitok. |
| Preparación | Formularios Short/Largo, validación local, persistencia y un ejecutor compartido. | Preparar búsquedas, voz, duración orientativa y requisitos visuales. | Configurar claves y archivos una vez; ordenar cada generación. Guardar/comprobar no consume voz. |
| Voz | Fish, caché por petición, conservación de audio confirmado y bloqueo de resultados inciertos; sin retry automático de POST de voz. | Revisar pronunciación, texto, tono e idioma antes de gastar; localizar audio/alineación existentes. | Escuchar y aprobar. Cambiar texto/voz/parámetros puede exigir nueva síntesis. No hay doblaje automático. |
| Shorts | Narración Rick local, diálogo Rick/Morty con gameplay y narración Pexels; montaje nativo, personajes/subtítulos según el formato. | Elegir un formato y aportar guion, fondos/poses cuando correspondan. | Revisar el MP4. La suite con proveedores simulados no prueba una nueva generación real de todos los estilos. |
| Largo básico | Fish + búsqueda/selección Pexels + FFmpeg; secciones, cortes y salida horizontal local. | Aportar guion completo y búsquedas pertinentes; revisar la relación frase/imagen. | Motor nativo experimental, 1080p, sin subtítulos. El stock puede ser genérico y el tiempo por sección estimado. |
| Largo documental | MotionDirector conservador, 19 candidatos configurables, galería local y montaje Native por escenas. | Revisar preguntas/datos/intenciones, imágenes y muestras antes del episodio completo. | Automático: preguntas, cantidades, fechas, presentaciones explícitas y conceptos acotados. Diagramas/documentos complejos siguen necesitando un plan. |
| Recuperación de largo | Auditoría de trabajos Native fallidos/interrumpidos del estudio y recuperación explícita del mismo ID usando narración confirmada, sólo caché local. | Revisar identidad, hashes y recursos antes de retomar. | No llama a Fish ni descarga; detiene faltantes. Requiere recibo Fish v2 y alineación completos; no cubre trabajos CLI antiguos ni MPT. [Procedimiento](../GUIA.md#recuperar-un-largo-fallido-conservando-la-voz-pagada). |
| Recursos específicos | Catálogo Commons, registro offline de Pexels ya cacheado, selección por entidad/rol, licencia y hash. | Comprobar identidad, contexto, derechos y utilidad; anotar entidad y función exactas. | Descargar/revisar los recursos faltantes. Buscar candidatos no verifica quién aparece en la imagen. |
| Dirección por escenas | Compila un brief explícito, comprueba cobertura y recursos y produce un plan determinista. | Escribir beats con tiempos, afirmación, fuente, intención y recurso/composición. | Sin editor de timeline ni interpretación de un guion arbitrario. Un faltante bloquea la preparación. |
| Montaje avanzado | Gráficos de identidad/cifra/información oculta, fotografía animada, rótulos, movimiento, render incremental y comparación A/B. | Elegir qué explica cada plano, legibilidad, ritmo y sincronía; reparar escenas concretas. | Los gráficos usan datos aportados. Los planos de mesa/informes tienen reparto UltimateBet fijo. |
| Música y SFX | CLI con 20 pistas auditadas, elección reproducible por trabajo/canal/ambiente, rotación, crossfade, ducking, medidas y seis SFX sintéticos. | Elegir intención musical y escuchar la mezcla; conservar créditos. | Formulario largo con Automática/Desactivada/Manual; pistas cacheadas y créditos descargables. Cambia dos ambientes, no compone música nueva ni entiende el tono de cada frase. |
| QA | Decodificación, geometría, duración, negros, sonoridad/pico, hashes, contacto visual y comparación del audio. | Ver el montaje y escuchar: semántica, continuidad, encuadre, contraste, pronunciación y ritmo. | Informe verde no acredita calidad narrativa ni ausencia de reclamaciones. |
| Entrega | Descarga local; shorts con fecha local, preview, confirmación Buffer y reconciliación de IDs guardados. | Preparar metadatos y revisar destino. | Confirmar publicación. Largos fuera de Buffer; subida manual a YouTube Studio. |
| Métricas | CLI YouTube oficial de lectura: OAuth, identidad/catálogo, consultas Analytics y enumeración Reporting. | Interpretar resultados cuando exista conexión real. | Consentimiento Google pendiente de comprobación real; CTR/CSV y dashboard no implementados. No hay optimización autónoma de retención. |

Los agentes y skills que coordinan desarrollo, revisión o preparación editorial
no son trabajos autónomos de Kitok. La skill local `kitok-audiovisual-qa` guía muestras y revisión; no instala un servicio
ni amplía por sí sola el director. No se han instalado MCP adicionales; las capacidades descritas son las del repositorio.
La aplicación no llama a un LLM por plano, fotograma o reintento de render.

## Un vídeo nuevo desde cero

1. Prepara un guion con fuentes, narrador y recursos apropiados. Un agente puede
   investigar y redactar si se lo encargas; el formulario usa el texto que le des.
2. Abre `make studio`, elige Short o Vídeo largo, comprueba sin generar y guarda.
   Corrige los requisitos indicados y revisa voz/búsquedas antes de generar.
3. Ordena la generación explícita. Ésta puede usar Fish y Pexels; no equivale a
   publicar. Conserva el audio y los resultados intermedios para posteriores cambios.
4. Revisa una muestra audiovisual antes de ampliar un montaje editorial exigente.
   El montaje básico puede bastar para una pieza sencilla. Para control por escena,
   prepara un brief o plan y sigue el recorrido de la sección siguiente.
5. Revisa el resultado, créditos y metadatos. Descarga localmente; confirma Buffer
   sólo para shorts, o sube un largo manualmente a YouTube Studio.

Para terminal, `main.py` y `longform.py` son las entradas de shorts y largos. Por
ejemplo, estos comandos sólo validan entradas ya preparadas; no contactan APIs:

```bash
.venv/bin/python main.py --dry-run
.venv/bin/python longform.py content/longform/mi_video.json --renderer native --dry-run
```

El JSON largo y el guion deben existir: su formato está en
[el manual](../GUIA.md). El dry-run comprueba requisitos locales, no saldo ni
autenticación remota. El largo acepta hasta 24.000 caracteres y 20 búsquedas en
el estudio. `native` es el motor nuevo; MPT conserva únicamente diagnóstico y
recuperación explícita de tareas históricas ya enviadas.

## Un vídeo con audio ya aprobado

Este recorrido puede hacerse sin agente cuando sabes qué mostrar y cuándo.
El agente ayuda a convertir decisiones editoriales en JSON o a revisar planos;
Kitok ejecuta después sin pedirle decisiones por fotograma.

1. Localiza primero audio Fish y alineación existentes, la referencia MP4 y las
   cachés. No generes otra voz para corregir un rótulo o cambiar una imagen.
2. Conserva una referencia con la mezcla final aprobada dentro del proyecto,
   por ejemplo `outputs/evaluation/mi_documental_muestra/A_current.mp4`.
3. Copia [brief.json](../examples/editorial/brief.json) a una carpeta de trabajo.
   Es una plantilla genérica de 12 segundos: sustituye **todos** los marcadores,
   fuentes `example.com`, ID, título, ruta de audio y entidades. `audio_approved`
   es una declaración tuya: ponlo a `true` sólo después de escuchar y aprobar.
4. Aporta al catálogo dos recursos revisados para este ejemplo: un clip Pexels
   cacheado con la entidad elegida y rol `footage`, de al menos 6 s desde el offset
   solicitado; y una foto Commons del sujeto correcto con entidad exacta y rol
   `portrait`. Las fuentes de las afirmaciones deben justificar lo narrado, no
   ser una página de stock. El ejemplo no incluye audio ni medios privados y no
   se puede compilar tal cual.
5. Ajusta duración y beats al audio real. Deben cubrir el intervalo completo sin
   huecos/solapamientos, durar al menos 0,4 s y caer en la rejilla global de FPS.
   Usa timestamps confirmados cuando existan; una estimación sigue siendo estimada.
6. Compila y renderiza a nombres nuevos. Estos comandos usan archivos locales,
   no descargan stock, sintetizan voz ni publican:

```bash
.venv/bin/python scripts/media_library.py list
.venv/bin/python scripts/direct_edit.py outputs/evaluation/mi_documental_muestra/brief.json --output outputs/evaluation/mi_documental_muestra/plan_v1.json
.venv/bin/python scripts/render_edit.py outputs/evaluation/mi_documental_muestra/plan_v1.json --output outputs/evaluation/mi_documental_muestra/B_v1.mp4 --compare-to outputs/evaluation/mi_documental_muestra/A_current.mp4
```

La compilación termina con código 2 y sin plan si falta un recurso admisible;
un archivo/brief inválido produce código 1. Valida licencia, hash, duración,
resolución medida, entidad/rol y repetición; reutilizar el mismo recurso requiere
`reuse_asset=true`. Guarda hashes de audio/medios y bloquea el render si cambian
sus bytes. La comprobación estructural del modelo no demuestra todo eso: también
deben existir el audio y los recursos correctos.

`--compare-to` exige el mismo audio decodificado en A/B: usa el mismo fragmento
y duración. El plan compilado trata el audio como mezcla final y lo conserva.
Si prefieres definir gráficos directamente, parte de
[plan.json](../examples/editorial/plan.json); el brief actual compila foto,
stock y las reconstrucciones admitidas, no todas las opciones del plan manual.
Consulta [el contrato de montaje](editing.md) para parámetros y QA.

Corrige el brief o plan y usa una nueva salida. Los planos no afectados se
reutilizan desde `.editorial-work/`; no borres cachés ni archivos aprobados para
forzar un reintento. Revisa MP4, `.editorial.json`, `.qa.json` y `.qa.contact.jpg`.
La hoja de contacto es una muestra de hasta 80 puntos, no una reproducción completa.

## Qué sirve para otros vídeos y canales

**Genérico hoy:** motor nativo, reutilización del audio confirmado, catálogo de
medios, fotos animadas, gráficos explícitos, plan por escenas, rótulos,
movimientos, cachés, QA y descarga. Un nuevo episodio necesita sus propios hechos,
fuentes, audio y recursos; conserva IDs y carpetas separados. Para un brief de
otro caso usa `family="generic"`, `cast={}` y `composer="photo"` o `"stock"`
explícitos con entidad/rol. `auto` sin recurso puede intentar una composición
de póker que quedará bloqueada para esa familia.

**Específico de UltimateBet:** las mesas y relaciones entre informes contienen
Paredes/NioNio, manos ilustradas y rótulos del caso. El compilador exige
`family="ultimatebet"` y exactamente
`{"player":"David Paredes","opponent":"NioNio"}` para `table`/`records`.
Cambiar el título, `channel_id` o `label` no cambia ese reparto. No uses esas
escenas para representar otro caso. Generalizarlas requiere desarrollo y revisión
del código 3D/Pillow y sus pruebas. No son imágenes del software ni manos históricas.

**Canales:** `channel_id` etiqueta los planes, no configura automáticamente voz,
marca o estrategia. En planes manuales puedes elegir paleta marfil/verde y acento;
los gráficos/fotos/3D conservan también su diseño propio. La música sólo selecciona
combinaciones de canal/ambiente presentes en `presets/music_sources.json`; un ID
nuevo por sí solo no crea un perfil. El catálogo admite únicamente las cuatro
pistas auditadas: ampliar artistas/pistas requiere revisar también el contrato
del código. Los perfiles multicanal versionados siguen siendo una propuesta.

**Idiomas:** aporta el texto del nuevo idioma y una voz Fish adecuada; revisa su
pronunciación. Conserva sus rótulos, audio y tiempos propios. Traducir o doblar
requiere preparar y aprobar otra versión: no se conservan automáticamente los
tiempos ni existe doblaje/traducción sincronizada. La elección de voz no traduce
el guion. Tampoco hay garantía de calidad lingüística por elegir un ID de canal.

## Recursos, música y derechos

Commons ofrece candidatos raster con licencias admitidas (CC0, CC BY y CC BY-SA
2.0/3.0/4.0). El operador/editor verifica sujeto, autor y contexto antes de anotar
entidad/rol. Se conservan fuente, licencia, atribución, hash y obligación
ShareAlike. Pexels sólo se registra como ilustración: no prueba un hecho ni puede
identificar al protagonista. `register-pexels` registra vídeos ya descargados y
revisados, sin otra búsqueda o descarga. La resolución de salida no acredita la
resolución original; una caché de menor resolución exige aceptación expresa.

`media_library.py list` y `audio_library.py list` son locales. En cambio,
`media_library.py search/fetch` consultan Commons y `audio_library.py fetch`
descarga/verifica fuentes oficiales cuando falta una caché válida. Los comandos
de adquisición están en [GUIA.md](../GUIA.md); no forman parte del render offline.

La biblioteca musical permite elegir y mezclar pistas ya cacheadas sin voz nueva:

```bash
.venv/bin/python scripts/audio_library.py list
.venv/bin/python scripts/audio_library.py select --job mi_documental_v1 --channel documentary --mood investigation
.venv/bin/python scripts/audio_library.py mix --job mi_documental_v1 --narration outputs/evaluation/mi_documental_muestra/narration.mp3 --duration 12 --output outputs/evaluation/mi_documental_muestra/mix_v1.m4a
```

Requiere narración existente y suficientes pistas cacheadas para esa selección.
`mix` crea una salida separada con recibo `.m4a.json`; no reemplaza la referencia
aprobada. Si eliges esa mezcla para el vídeo, apruébala y úsala también en una
nueva referencia A para exigir igualdad de audio. El formulario largo tiene
su opción histórica de archivo de música local; no activa este selector.

El catálogo musical conserva 20 pistas de Kevin MacLeod bajo CC BY 4.0,
con procedencia y créditos. Incluye las atribuciones y avisos de cambios de los
recibos al distribuir el resultado. Content ID permanece `unknown`: licencia,
hash y QA no garantizan ausencia de reclamaciones o monetización.

## Coste, equipo y conservación

La voz nueva puede consumir saldo Fish; una petición incierta queda detenida
para revisión. El programa no acredita que el proveedor cobre exactamente una
vez. La reedición sobre audio/medios aprobados no consume proveedores. Las
bibliotecas locales no son una nueva suscripción; adquirir recursos sí necesita
Internet. No se ha medido un coste total por episodio ni se promete producción
gratuita. La investigación vidIQ no es un requisito de render y su gasto requiere
autorización específica.

El diseño usa FFmpeg, ejecución secuencial y caché para el equipo de referencia
de 4 GB VRAM/8 GB RAM. Prueba NVENC y usa libx264 si no funciona. El 3D opcional
usa Three.js/Chromium local, hasta 1920×1080; `make cinema-setup` instala su
navegador. WebGL por software puede ser lento. No necesita modelos locales de
generación de vídeo y no hay un benchmark que permita prometer tiempo real,
paralelismo entre canales o duración fija de render para otro equipo.

Conserva audio, alineación, manifiestos, créditos y cachés útiles. `.env`, medios,
cola activa y estado pertenecen al espacio privado local, no al ejemplo público.
No borres IDs/operaciones para eludir protecciones ni sobrescribas resultados
terminados. Los servidores se abren sólo en `127.0.0.1`.

## Puesta en marcha, operación y mantenimiento

| Frecuencia | Trabajo requerido | Quién lo hace |
| --- | --- | --- |
| Instalación inicial | Python/Node/FFmpeg, `make studio-setup`, claves privadas y recursos; navegador opcional para 3D. | Operador con ayuda técnica si hace falta. Un agente no es requisito para ejecutar el programa instalado. |
| Cada vídeo | Guion, fuentes, voz, medios, aprobación de audio y revisión del resultado. Brief/plan si se necesita dirección precisa. | Editor u operador; un agente puede investigar, preparar JSON y proponer correcciones. |
| Cada render/revisión local | Ejecutar plan, reutilizar planos, mezclar y producir QA a partir de entradas resueltas. | Kitok tras la orden explícita. No necesita agente en cada bucle o fotograma. |
| Publicación/conexión | Consentimiento Google, revisión Buffer y confirmación de los envíos. | Titular/operador. No se sustituyen por silencio ni por un test local. |
| Nuevo formato/canal complejo o defecto | Cambiar contratos, parametrizar reparto, implementar perfiles, reparar código y verificar. | Desarrollador o agente de programación con revisión; no es un coste obligatorio de cada vídeo. |

## Brecha entre la autonomía deseada y lo entregado

La mejora audiovisual demostrada es el piloto UltimateBet C de **76 segundos**,
con 17 escenas, audio existente conservado y revisión visual independiente. El
episodio original de **652,6 segundos no se ha reeditado completo**. La evidencia
y las mediciones de esa muestra están fechadas en
[PROJECT_STATUS.md](../PROJECT_STATUS.md); no son una garantía de igual rendimiento
o calidad en otro vídeo. Siguen pendientes recursos más específicos y una estética
más uniforme entre stock/3D; no consta audición subjetiva ni reproducción audiovisual
continua del episodio final completo.

Falta convertir la preparación editorial en un recorrido persistente de producto:
investigación con fuentes, selección y espera de aprobación, guion revisado,
perfil de canal y dirección general reutilizable. No hay miniaturas editoriales
automáticas, editor visual de timeline, doblaje automático, publicación YouTube,
CTR conectado ni optimizador autónomo de retención. Google necesita consentimiento
real del titular y una comprobación remota posterior. El código de lectura y sus
tests offline no prueban que el canal esté conectado.

Puedes producir y reeditar con lo implementado si aportas las decisiones y
revisiones que señala la matriz. Ampliar la muestra al episodio completo y
alcanzar un director multicanal autónomo son trabajos pendientes, descritos como
propuestas en [el roadmap](roadmap.md), no capacidades ocultas que se activen
instalando una skill.

## Entradas y archivos de referencia

| Entrada o módulo | Responsabilidad |
| --- | --- |
| `make studio`; `frontend/`; `src/kitok/api/` | Interfaz local y transporte HTTP. |
| `main.py`; `src/kitok/application.py`, `pipeline.py`, `generation.py` | CLI, borradores/trabajos y generación de shorts. |
| `longform.py`; `src/kitok/longform/`; `longform_studio.py`; `rendering/` | CLI, modelos, estudio y motor de largos. |
| `src/kitok/editing/director.py`, `storyboard.py`, `cinema.py` | Contratos de brief/plan, compilación y composiciones. |
| `scripts/direct_edit.py`; `scripts/render_edit.py` | Preparar un plan y renderizarlo/medirlo sin proveedores. |
| `scripts/media_library.py`; `src/kitok/media_library.py` | Catálogo de recursos y registro de procedencia. |
| `scripts/audio_library.py`; `src/kitok/audio_library.py` | Biblioteca musical, selección, mezcla y SFX. |
| `scripts/youtube_readonly.py`; `src/kitok/youtube/` | Conexión oficial opcional sólo lectura. Contrato en [YouTube](integrations/youtube-readonly.md). |
| `content_queue.json`; `state/`; `content/longform/studio/` | Borradores y estado privado del operador. |
| `outputs/ready/`; `outputs/longform/`; `outputs/evaluation/` | Vídeos cortos, largos y muestras/planes locales. |
| `presets/`; `cache/`; `assets/` | Catálogos versionados y recursos/cachés locales según ruta. |
| `examples/editorial/` | Plantillas públicas con marcadores; no son vídeos listos para producir. |

Para verificar cambios de código usa `make studio-check`, `make verify` y, con
Chromium disponible, `make verify-browser`. No conectan por sí solos una cuenta
real ni prueban una publicación o una voz nueva contra proveedores reales.
