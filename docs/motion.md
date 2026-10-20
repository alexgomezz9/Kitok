# Documental enriquecido

Kitok conserva Native y FFmpeg. El repertorio usa filtros nativos, libass para
texto y vectores, y Pillow para fondos. No instala otro renderer ni llama a LLMs
por escena o fotograma. [Investigación y licencias](motion-research.md) explica
por qué Remotion, Motion Canvas, MotionCraft, MLT y frei0r se aplazan.

## Repertorio reutilizable

19 candidatos en `kitok.editing.motion_components.CATALOG`, agrupados por familia:

| Familia | Composiciones/tratamientos |
| --- | --- |
| Tipografía | Pregunta, frase en tres tiempos, palabra en contexto, capítulo |
| Contexto | Identidad, fecha, lugar |
| Datos | Cantidad explícita, comparación con dos valores, flujo con tres pasos |
| Documentos | Cita atribuida, fragmento textual resaltado |
| Stock | Congelación, acercamiento, reencuadre, desenfoque de entrada, color archivo |
| Transiciones | Disolución y barrido breves |

`MotionDesign` valida `effect`, `text`, `label`, `detail`, `emphasis`, `items`,
`values`, `symbols`, `display_text`, `preset`, `delay`, `hold` y reloj `elapsed`/`emphasis_delay`. `investigation`, `archive` y `signal` cambian
paleta y jerarquía. Los datos son aportados: no hay nombres ni cantidades históricas
por defecto. `display_text` permite un titular editorial breve explícito y conserva
`text` como fuente. No se recortan preguntas con regex: una cláusula puede ser
esencial. Sólo cantidades enteras sencillas en dólares/euros escritas con palabras
pueden mostrarse en dígitos, conservando calificador y escala; pounds, rangos y
fracciones quedan literales. Las comparaciones necesitan valores finitos no negativos y etiquetas;
el editor debe comprobar unidad, fuente y significado. Los diagramas/citas no se
convierten en evidencia documental por su apariencia.

La revisión visual añade títulos grandes con máscaras y aparición escalonada,
subrayados progresivos y diagramas de tres nodos con símbolos vectoriales
(`key`, `device`, `shield`, `database`, `lock`, `person`). Los símbolos son
decisiones explícitas del plan, no interpretación automática de cualquier guion.
El énfasis sobre stock usa un degradado y evita repetir la frase entera como
subtítulo. Si se convierte en placa completa, centra el concepto como título.
El reloj de crecimiento es lineal para conservar el mismo estado entre cortes.

Una escena del plan usa `graphic="motion"` y `motion_design` para una placa o
`asset` más `motion_design` para componer sobre stock. El render valida texto medido,
áreas seguras y duración; si no cabe, exige acortarlo. Escapa código ASS en texto.
Las disoluciones/barridos usan el último fotograma anterior durante 0,28 s máximo;
no solapan la narración ni acortan la duración total.

## Qué decide automáticamente

MotionDirector conserva stock cuando no encuentra una intención soportada. Detecta
preguntas, cantidades literales numéricas o escritas, porcentajes, fechas,
presentaciones explícitas mediante named/called/llamado y un vocabulario acotado de
conceptos técnicos en contexto. No investiga ni entiende cualquier guion. No infiere
identidades a partir de una capitalización. Diagramas, citas documentales, capítulos,
lugares y comparaciones complejas requieren decisiones explícitas en un plan.

Busca las frases en timestamps Fish sólo si la alineación coincide con el transcript
expandido completo (incluidos guiones divididos y tokens de duración cero). Si no,
conserva tiempos estimados declarados. Cada decisión registra razón y método.
Preguntas y cantidades tienen prioridad sobre contexto opcional. Máximo 38% de tiempo con énfasis, separación mínima 3 s y memoria de las dos familias
recientes en 45 s. Una pregunta ocupa una placa continua; no reinicia animación por
cada corte de stock. Los efectos sobre stock conservan un reloj global al cruzar cortes, incluidos
entrada/salida y énfasis anclado a Fish; un fragmento demasiado corto puede
convertirse en placa continua sin extender ni agotar el stock. Una falta de cobertura bloquea el render.

El modo básico mantiene su recorrido anterior. El puente `render_motion_longform`
produce un plan y reutiliza la ejecución por escenas. No altera Buffer, shorts,
permisos YouTube ni cola. Three.js y póker siguen opcionales históricos, fuera de la
selección automática de este modo.

## Demostraciones locales y caché

Las pruebas viven bajo `outputs/motion-gallery/ID/`: `preview.mp4`, `baseline.mp4`
cuando corresponde, `contact.jpg`, `qa.json`, `CREDITS.md` y plan. Medios privados,
no versionados. El estudio sirve sólo nombres permitidos por ID; rechaza traversal
y symlinks. Consultar la galería no genera ni contacta proveedores. El vídeo se
carga al pulsar «Reproducir muestra» o «Reproducir referencia básica»; sólo hay
un reproductor activo. El contacto se ofrece como imagen estática en un desplegable,
nunca como poster del vídeo. Un error de reproducción muestra la descarga del
archivo afectado y no se presenta como prueba de corrupción del MP4.

Para reconstruir efectos con stock existente y fuente/licencia revisadas:

```bash
.venv/bin/python scripts/motion_gallery.py effects --stock cache/pexels/videos/ID.mp4 --source-url https://www.pexels.com/video/ID/ --credit "Autor y procedencia comprobados" --revision r2
```

`--revision` crea IDs nuevos y conserva las pruebas anteriores; sin revisión,
los archivos ya existentes se omiten.

Para un fragmento preparado localmente:

```bash
.venv/bin/python scripts/motion_gallery.py sample local/motion-phase/MI_MUESTRA.json
```

La configuración de muestra identifica guion/audio/alineación/timeline/referencia
existentes y un intervalo 3–40 s. No puede lanzar el documental completo. Reutiliza
Fish y stock, mezcla música cacheada y prepara A/B con audio idéntico para comparar
imagen. La referencia original permanece intacta. No se solicitan proveedores.

Caché por escena, datos, hash de recursos, ASS, código del compositor y encoder.
El ensamblado de mezclas aprobadas copia vídeo y audio AAC sin normalizar de nuevo.
Si el máster es WAV/PCM u otro códec, codifica el audio una vez a AAC para la
entrega MP4 y conserva el original; el recibo identifica esta conversión.
Las salidas nuevas son exclusivas; conserva originales y usa ID/revisión nueva.
El informe mide decodificación, geometría, duración, negros, LUFS/pico y audio A/B;
la hoja de contacto muestrea imágenes. No acredita audición subjetiva ni aprobación.

## Muestras revisadas tras el feedback visual

El operador rechazó la primera presentación por parecer tarjetas/subtítulos.
El mosaico enviado era `contact.jpg`, una imagen estática; no se utiliza ahora
como portada del vídeo. Ese hecho no convierte la calidad inicial en aceptada.
La revisión conserva los MP4 anteriores y los retira de la galería vigente.

Las candidatas actuales están bajo `outputs/motion-gallery/`:

- `effect_r2_*`: 19 demostraciones individuales de cuatro segundos.
- `ub_opening_v7`: 31 s; pregunta con titular editorial explícito y cifra grande.
- `ub_development_v7`: 31,5 s; flujo de información con objetos/conexiones animados.
- `ub_revelation_v7`: 29,5 s; dato de reembolso y contexto financiero.
- `generalization_mfa_v3`: 20 s; tipografía y diagrama llave/dispositivo/escudo,
  sin narración nueva.

Las tres UB conservan la mezcla de voz y música de las versiones anteriores, con referencia A/B de audio decodificado idéntico. Se retiraron los
planos de solitario, pantallas de compras y mesas de blackjack señalados en la
revisión; el stock sigue siendo ilustrativo, no imágenes históricas. Las preguntas
breves y etiquetas de estas pruebas fueron decisiones editoriales explícitas;
no se prometen esas mismas decisiones mediante recortes automáticos de frases.
El recorrido Native anterior se conserva como prueba técnica histórica, fuera
de esta selección visual; no se renderizó un episodio completo.

Autores consultados mediante GET oficial de Pexels el 20/10 y guardados en
`cache/pexels-credits/`; los créditos de la revisión identifican las sustituciones.
Las búsquedas nuevas conservan autor/perfil; cachés antiguas pueden carecer de
ellos y se declaran desconocidos hasta verificarlos.

El operador confirmó después el error de decodificación tanto en Kitok como en
la descarga Windows. La auditoría completa encontró **seis MP4** que empezaban
como H.264 High/4:2:0 pero cambiaban a High 4:4:4 dentro del archivo al entrar en
una transición. La cabecera inicial y el decoder software de Linux toleraban ese
cambio; las comprobaciones previas no bastaban para validar una entrega portable.

En FFmpeg 6.1.1, `xfade` negocia formatos de trabajo 4:4:4. El renderer ahora
convierte a `yuv420p` después del filtro y fija ese formato al codificar; una versión
nueva de caché invalida las escenas afectadas. Regresión: disolución y barrido
reales, comprobando **todos** los fotogramas y la conservación del AAC.

La galería vigente usa los IDs de arriba con sufijo **`_compat1`**, incluidos los
19 `effect_r2_*_compat1`. Son copias nuevas con H.264 High/4:2:0 uniforme; 5.640
fotogramas de los 23 previews comprobados, decodificación completa y paquetes AAC
idénticos. Las referencias A/B compatibles se copian sin recodificación. Los
originales y metadatos anteriores se conservan con respaldo; cada carpeta nueva
tiene `repair.json` con hashes y procedimiento. No se sintetizó voz ni se renderizó
el episodio para esta reparación. El decoder Windows no está disponible aquí;
la comprobación en el equipo del operador sigue siendo necesaria.

Para reparar otra candidata corta activa, sin sobrescribirla ni usar proveedores:

```bash
.venv/bin/python scripts/repair_motion_delivery.py --item ID_ACTIVO --revision compat1
```

El comando rechaza medios de más de 60 segundos y salidas existentes. Publica la
nueva entrada sólo después de validar todos los fotogramas, duración y AAC;
archivar la entrada anterior es una operación separada con respaldo.
Para ver el movimiento abre el estudio y pulsa «Reproducir muestra»; el contacto
es una imagen de revisión, no una animación.

La música utiliza dos pistas para inicio/cierre, con una frontera de secciones
validada o cambio central estimado declarado. No compone una banda sonora para
cada escena. Las voces nuevas tienen previews del proveedor de textos distintos;
las históricas plain/tags sí comparten texto. No se sintetizó voz en esta fase.
La escucha subjetiva, sincronía audiovisual continua y aprobación editorial
siguen pendientes del operador, aunque se revisen frames y reproducción técnica.
