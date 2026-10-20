# Montaje por escenas

El montaje básico de largos usa búsquedas y secciones del guion. El montaje por
escenas añade decisiones explícitas sobre una narración ya aprobada: qué explica
cada plano, qué fuente respalda el dato, qué recurso muestra y cuándo cambia.
No investiga hechos ni inventa esas decisiones. El modo automático documental
elige un subconjunto conservador de intenciones del guion; su repertorio, galería
y límites están en [Documental enriquecido](motion.md).

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
final se copia sin volver a normalizarlo. El CLI también admite narración sin
mezclar con `audio_is_final_mix=false`, actualmente con offset cero.

## Opciones del plan

Cada escena elige un recurso existente (`asset`), una plantilla (`graphic`) o
una composición animada (`composition`). Las plantillas ofrecen:
identidad, cifra con significado o diagrama de información privada/expuesta.
`graphic_data` contiene textos y datos aprobados; no hay cifras por defecto.
Las imágenes y vídeos aportados también sirven como recursos. En vídeo,
`source_start` y la duración deben caber en el archivo; no se estira una toma
insuficiente ni se cambia por otra silenciosamente.

`headline` y `kicker` son rótulos breves deliberados; no se extraen palabras sueltas
mediante regex. Movimiento: ninguno, acercamiento o desplazamiento suave.
Transición: corte, entrada breve desde negro, disolución o barrido breve sin desplazar la voz. `palette` marfil/verde y `accent`
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
