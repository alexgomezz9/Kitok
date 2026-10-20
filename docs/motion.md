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
`values`, `preset`, `delay`, `hold` y reloj `elapsed`/`emphasis_delay`. `investigation`, `archive` y `signal` cambian
paleta y jerarquía. Los datos son aportados: no hay nombres ni cantidades históricas
por defecto. Las comparaciones necesitan valores finitos no negativos y etiquetas;
el editor debe comprobar unidad, fuente y significado. Los diagramas/citas no se
convierten en evidencia documental por su apariencia.

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
.venv/bin/python scripts/motion_gallery.py effects --stock cache/pexels/videos/ID.mp4 --source-url https://www.pexels.com/video/ID/ --credit "Autor y procedencia comprobados"
```

Para un fragmento preparado localmente:

```bash
.venv/bin/python scripts/motion_gallery.py sample local/motion-phase/MI_MUESTRA.json
```

La configuración de muestra identifica guion/audio/alineación/timeline/referencia
existentes y un intervalo 3–40 s. No puede lanzar el documental completo. Reutiliza
Fish y stock, mezcla música cacheada y prepara A/B con audio idéntico para comparar
imagen. La referencia original permanece intacta. No se solicitan proveedores.

Caché por escena, datos, hash de recursos, ASS, código del compositor y encoder.
El ensamblado de mezclas aprobadas copia vídeo/audio, sin normalizar de nuevo.
Las salidas nuevas son exclusivas; conserva originales y usa ID/revisión nueva.
El informe mide decodificación, geometría, duración, negros, LUFS/pico y audio A/B;
la hoja de contacto muestrea imágenes. No acredita audición subjetiva ni aprobación.

## Muestras y recursos comprobados en esta fase

Las demostraciones finales están bajo `outputs/motion-gallery/`: efectos
individuales `effect_*`, `ub_opening_v5` (31 s), `ub_development_v5` (31,5 s),
`ub_revelation_v5` (29,5 s), `generalization_mfa_v1` (20 s, sin voz nueva)
y `native_roundtrip_v2` (31 s, 720p, proveedores simulados/sockets bloqueados).
Las revisiones locales anteriores se conservan; la galería muestra sólo las
candidatas vigentes. Las muestras UB comparan imagen con audio A/B idéntico.
La muestra técnica sustituye mesas de casino poco pertinentes por servidores
y ordenadores vistos directamente; siguen siendo ilustrativos.

Autores de stock consultados mediante GET oficial de Pexels el 20/10, guardados
en `cache/pexels-credits/`, incluidos en los créditos de las muestras. Búsquedas
nuevas conservan autor y perfil en caché; las antiguas pueden carecer de ellos
y se declaran desconocidos hasta verificarlos.

La música utiliza dos pistas para inicio/cierre, con una frontera de secciones
validada o cambio central estimado declarado. No compone una banda sonora para
cada escena. Las voces nuevas tienen previews del proveedor de textos distintos;
las históricas plain/tags sí comparten texto. No se sintetizó voz en esta fase.
La inspección visual y medidas técnicas permiten revisar estas candidatas;
la escucha subjetiva y la aprobación editorial siguen pendientes del operador.
