# Montaje por escenas

El montaje básico de largos usa búsquedas y secciones del guion. El montaje por
escenas añade decisiones explícitas sobre una narración ya aprobada: qué explica
cada plano, qué fuente respalda el dato, qué recurso muestra y cuándo cambia.
No investiga hechos ni inventa esas decisiones. El modo automático documental
elige un subconjunto conservador de intenciones del guion; su repertorio, galería
y límites están en [Documental enriquecido](motion.md).

## JSON parcial sobre montaje automático

Para un largo nuevo basta guion, keywords y, opcionalmente, `visual_plan` en su
configuración. No escribas una escena por corte. Native selecciona stock, cubre la
narración y compila los momentos explícitos con prioridad sobre MotionDirector.
Fuera de ellos mantiene el stock automático. Una entrada mínima es:

```json
{
  "visual_cues": [
    {"asset": "images/person.jpg", "anchor": {"phrase": "A researcher named Alex"}}
  ]
}
```

En CLI el objeto anterior va bajo `visual_plan` y `visual_root` identifica la
carpeta del episodio relativa al proyecto. Por defecto se usa la carpeta del JSON
CLI. El estudio determina la carpeta por ID de episodio, sin aceptar rutas libres.
También admite `real_images/`; no hace falta mover imágenes existentes.
[Plantilla mínima y ejemplo avanzado](../examples/visuals/README.md).

Cada cue elige `anchor.phrase` y `occurrence` (desde cero), o `start` en segundos.
La frase debe existir en el guion antes de sintetizar. Con alineación Fish íntegra
se usa su tiempo real; en ausencia de alineación válida se declara
`estimated-script-words`. Duración automática de hasta 4 s, ajustada al siguiente
cue/final; `duration` permite sobrescribirla. Los límites se cuantizan a frames.
Los intervalos explícitos incompatibles se rechazan, no se sustituyen con stock.
Alrededor de cortes muy cercanos el compilador puede ampliar el intervalo técnico
manteniendo el reloj global del efecto; el manifiesto conserva instante pedido,
intervalo compilado y ajuste. No se promete alineación por palabra estimada.

`camera`, `image_fit` y `transition` sobrescriben sus valores sobrios automáticos.
`effect`, `text` y `motion_data` usan `MotionDesign` del repertorio común. Un cue
sin `asset` puede colocar tipografía sobre `background="automatic_stock"` (valor
predeterminado) o una placa `"black"`. Usa `transition="dissolve"`/`"wipe"` para
transiciones: esos nombres en `effect` se rechazan para evitar una orden inerte.
No hay subtítulos permanentes ni llamadas LLM al render.

Las imágenes admitidas por el flujo parcial son JPG/JPEG, PNG y WebP, de al menos
32 px y hasta 40 megapíxeles/40 MB en disco; el upload del estudio admite hasta
cuatro por petición de 6 MB cada una. Se comprueban decodificación, contención y
symlinks antes de Fish. `description`, `source_url`, `credit`, `usage`, `license`
y `license_url` permiten una procedencia mínima opcional, conservada junto con
SHA-256 en recibo/créditos. Un archivo aportado se declara como tal: su nombre no
verifica identidad ni permiso de uso. Una ilustración nunca es prueba del caso.

Los cues comparten escenas, fuentes, filtros, caché, ensamblador y validación con
el stock. Actualmente Native aún busca/selecciona stock para toda la narración,
incluso bajo fotos: éstas mandan en la imagen final, pero no evitan todas esas
consultas. No es un buscador autónomo de fotografías. Los ajustes de música del
plan parcial requieren `music_mode="off"`, `"auto"` o `"manual"`; se rechaza la
configuración musical histórica ambigua antes de Fish.

Los planes completos descritos a continuación siguen disponibles para dirección
por escena y audio aprobado. No son necesarios para el uso diario de fotos.

## Preparar un montaje

1. Conserva una referencia audiovisual con el audio final aprobado dentro del
   proyecto. Para la comparación, guárdala como
   `outputs/evaluation/MI_ID/A_current.mp4`.
2. Copia [la plantilla](../examples/editorial/plan.json) a
   `outputs/evaluation/MI_ID/plan.json`. Ajusta `episode_id`, `channel_id`, título,
   `audio_source`, duración y escenas al fragmento real. La plantilla tiene
   marcadores editoriales: no es un contenido terminado.
3. Todos los recursos deben existir dentro del proyecto. En `assets`, identifica
   cada archivo y su descripción, URL/autor y uso: `illustration`, `document` o
   `provided`. Una ilustración no es una prueba histórica. No se descarga stock
   ni se sintetiza voz durante este montaje.
4. Los planos cubren toda la duración sin huecos ni solapamientos, duran al menos
   0,4 s y utilizan límites en la rejilla de fotogramas. Para anclar una frase a
   timestamps reales de Fish usa `phrase_time`; `frame_time` redondea cada límite
   global. Los tiempos estimados conservan esa etiqueta; no se presentan como ASR.
5. Renderiza a un nombre nuevo. Una salida existente se rechaza para conservarla:

```bash
.venv/bin/python scripts/render_edit.py outputs/evaluation/MI_ID/plan.json \
  --output outputs/evaluation/MI_ID/B_prueba.mp4 \
  --compare-to outputs/evaluation/MI_ID/A_current.mp4
```

`--compare-to` exige que el audio decodificado sea idéntico. Para comparar un
fragmento, utiliza A con ese mismo fragmento, no el episodio completo. El audio
final AAC se copia sin volver a normalizarlo. Un máster PCM se codifica una vez
a AAC para entregar un MP4 compatible, conservando el original y su nivel. El CLI también admite narración sin
mezclar con `audio_is_final_mix=false`, actualmente con offset cero.

## Opciones del plan

Cada escena elige un recurso existente (`asset`), una plantilla (`graphic`) o
una composición animada (`composition`). Las plantillas ofrecen:
identidad, cifra con significado o diagrama de información privada/expuesta.
`graphic_data` contiene textos y datos aprobados; no hay cifras por defecto.
Las imágenes y vídeos aportados también sirven como recursos. En vídeo,
`source_start` y la duración deben caber en el archivo; no se estira una toma
insuficiente ni se cambia por otra silenciosamente.

Native mide el stream de vídeo del archivo descargado para elegir el punto de
entrada, reservando el consumo que introduce el redondeo global a fotogramas.
Los segundos anunciados por Pexels y la duración del contenedor no determinan ese
límite: el audio del stock puede durar más que su imagen. Si no puede medirse el
stream de vídeo, se detiene. El recibo Native conserva duración anunciada y medida.
El render editorial comprueba todas las ventanas de stock antes de crear workspace,
arrancar encoder o renderizar escenas; el error incluye escena, entrada, fin
solicitado y duración real. No se amplió el margen de validación de 50 ms.

Cada plano reinicia sus timestamps antes de convertir a FPS y produce el número
exacto de fotogramas entre sus límites globales. Esto evita pérdidas acumuladas
al recortar stock de 29,97/23,976 FPS con entradas fraccionales. Se comprueban
fotogramas, inicio cero y duración de cada plano, caché, ensamblado y entrega.
Los diagnósticos `*.validation.json` conservan valores esperados y medidos;
un archivo rechazado se conserva. La duración del audio/contenedor no sustituye
la del vídeo. La versión de caché anterior queda invalidada.


`headline` y `kicker` son rótulos breves deliberados; no se extraen palabras sueltas
mediante regex. `camera` acepta un preset o un objeto con `preset`, `focus_x`,
`focus_y`, `start_scale`, `end_scale`, `displacement`, `rotation` y `easing`
(`linear` o `smoothstep`). Los once presets están en [motion](motion.md).
Los campos históricos `motion="none"`, `"push"` y `"pan"` siguen admitidos.
Las fotos usan encuadre completo sobre fondo desenfocado (`image_fit="auto"`
o `"contain"`); `"cover"` permite un recorte deliberado.

`transition` admite `cut`, `fade`, `dissolve`, `wipe`, `slide`, `fade_black`,
`focus` y `match_cut`. Las transiciones entre fuentes usan fotogramas de
continuación del plano anterior, sin congelar ni repetir su cola. Si el stock no
cubre ese margen opcional, se aplica corte y se registra el motivo en el recibo;
la narración y los límites de plano no cambian. `match_cut` es un corte preparado
por el editor: el motor no descubre correspondencias visuales.
`fade_in` y `fade_out` del plan sólo afectan al vídeo y están dentro de su duración.
Los planes históricos los omiten con valor cero; un plan parcial nuevo los fija a
0,6/0,8 s. `palette` marfil/verde y `accent`
fijan el estilo del plan; una escena puede cambiar la paleta. `channel_id` registra
el canal y permite conservar planes de estilos distintos, pero no resuelve un
catálogo multicanal ni abre canales de YouTube.

## Verificar y reparar

Se guardan el MP4, manifiesto `.editorial.json`, informe `.qa.json` y hoja
`.qa.contact.jpg`. El informe incluye decodificación completa, geometría,
duraciones por stream, sonoridad, negros, hashes y comparación de audio. La hoja
muestra hasta 80 puntos distribuidos: en planes mayores es una muestra declarada,
no la inspección de todos los planos. No acredita por sí sola sincronía semántica,
legibilidad, derechos ni buen ritmo; revisa esos aspectos visualmente.

Los planos se almacenan en `.editorial-work/EPISODIO/` con huellas de recursos,
estilo y filtros. Corregir una escena invalida sólo su render; el ensamblado final
se repite. No borres esa carpeta ni el audio para corregir un rótulo. Los render
secuenciales usan NVENC cuando la comprobación real funciona y libx264 como
alternativa; no necesitan modelos de vídeo ni descargas CUDA.

La integración del estudio ofrece reproducción A/B y render explícito del plan
local. No hay editor visual de timeline. El modo documental automático de largos
produce un plan acotado; no sustituye un brief investigado.

## Planos con acción y fotografía

Una escena puede elegir `composition` en lugar de `graphic`: `table` reconstruye
una mesa 3D; `records` muestra la relación entre informes, y `photo` anima una
fotografía existente con rótulo y crédito. `composition_data` valida modo, cámara,
texto, instante de revelación y punto de enfoque. `photo` requiere `asset`;
`table`/`records` no. En composiciones `source_start` debe ser cero y el plano
no puede superar 30 segundos.

Instalación opcional del navegador local, después de `make studio-setup`:

```bash
make cinema-setup
```

La mesa usa Three.js/Chromium local, sin modelos de generación ni servicios
externos. Cámaras: `wide`, `opponent`, `cards`, `chips`, `overhead`.
Modos 3D: `opponent`, `aggression`, `loss`, `question`, `private`, `exposed`.
Las cartas sólo se revelan en `exposed` después de `reveal_at`, expresado en
segundos desde el inicio del plano. La geometría3D máxima es 1920×1080.
Los actuales escenarios de mesa/informes representan Paredes/NioNio: no los
uses para otro reparto hasta parametrizarlo. No son capturas del software real
ni manos históricas. La fotografía sí admite otros sujetos con recurso revisado.

Estos planos se renderizan secuencialmente y se cachean por datos, recursos y
código 3D. Cambiar una cámara invalida ese plano, sin repetir Fish. Software WebGL
es compatible con la 3050/4 GB, pero resulta más lento que ensamblar stock.

## Compilar decisiones una vez y reutilizarlas

El agente prepara un brief con audio aprobado y beats contiguos: intención,
afirmación, fuente y recurso por entidad/función, o una reconstrucción explícita.
El compilador selecciona recursos locales con licencia, verifica sus hashes,
elige la cámara por intención y explica cada decisión. No llama a LLMs, stock ni
voz; si falta un recurso devuelve código 2 sin escribir un plan incompleto.

```bash
.venv/bin/python scripts/direct_edit.py outputs/evaluation/MI_ID/brief.json \
  --output outputs/evaluation/MI_ID/plan_nuevo.json
```

La muestra local conserva `brief.json` y `director_plan.json`. La CLI exige un
nombre de salida nuevo; no sobrescribe el brief ni un plan anterior. Las fuentes
están bajo `cache/media-library/`. Los recursos agotados no se repiten salvo
`reuse_asset` explícito. Las fotos y el stock sirven para otros episodios; las
reconstrucciones de póker actuales exigen el reparto UltimateBet declarado.
No interpreta un guion arbitrario ni investiga hechos automáticamente.

El plan fija el SHA del audio y de cada recurso seleccionado. Un cambio de bytes
tras la preparación bloquea el render; si un input cambia durante el trabajo,
se bloquea la entrega. Los planes antiguos sin SHA conservan compatibilidad.

## Fotografías de stock de Pexels: investigación adicional

La [API oficial](https://www.pexels.com/api/documentation/) admite fotos mediante
`GET /v1/search` con `query`, orientación y variantes de resolución. La prueba
read-only del 21/10/2026 respondió HTTP 200 y descargó una foto de muestra con
ID, autor, URL y licencia conservados. Eso verifica acceso a fotos; el proveedor
Native actual sigue buscando **vídeos**. No se presenta esta prueba como una
opción de fotos automáticas ya integrada en el producto.

Una futura mezcla opcional puede conservar keywords y montaje, separando la
caché por tipo y manteniendo prioridad de imágenes explícitas. Las fotos Pexels
serían ilustrativas, sin atribuirles identidad histórica del caso. No hacen falta
otro renderer ni un gestor de imágenes. Esta investigación no cambia el alcance
ni retrasa el cierre del editor solicitado.
