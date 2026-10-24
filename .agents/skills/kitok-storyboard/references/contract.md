# Decisiones compactas y salida real

Entrada: carpeta con `guion_final.txt` y `configuracion.json` válida de Kitok
(`init` puede crear una configuración, no un guion). Define estilo y personajes
en la configuración UNA VEZ; referencias existentes con roles `interior`,
`character`, `thumbnail`. No hace falta voz para preparar imágenes.

Lista de decisiones, no nuevo plan de producción:

```json
[
  {
    "through": "¿Por qué no volvió?",
    "visual_description": "Pregunta aislada sobre una puerta cerrada y una llave abandonada.",
    "scene_prompt": "Close-up of a locked wooden door and one abandoned iron key on a pale floor. Leave generous empty space above the door for the intentional question; no people.",
    "visual_type": "question",
    "display_text": "¿Por qué no volvió?",
    "camera": "slow_push_in"
  },
  {
    "narration": "En 1978 comenzó la búsqueda.",
    "visual_description": "El año 1978 domina un calendario sencillo con una hoja levantada.",
    "scene_prompt": "A single paper calendar leaf, large year centered, warm cream background, three-quarter view, clean ink outlines, no tiny day labels or decorative writing.",
    "visual_type": "date",
    "display_text": "1978"
  }
]
```

Este ejemplo sólo sirve para un guion cuyo texto sea exactamente
`¿Por qué no volvió? En 1978 comenzó la búsqueda.`. `through` toma desde el
cursor actual hasta esa cita literal inclusive; debe ocurrir una sola vez en
el resto del guion. Para frases repetidas usa `narration` completa. Ningún
campo de entrada admite timestamps. Incluye puntuación final en la cita;
no se permite partir palabras. El último elemento debe cubrir hasta el final.

Campos opcionales: `characters` (lista de IDs definidos en la configuración),
`camera` (nombre o estructura CameraMotion existente), `display_text` (texto
intencional), `visual_type` (`action`, `reaction`, `object`, `map`, `date`,
`quantity`, `question`, `comparison`, `timeline`, `diagram`, `place`,
`silhouette`, `document`). Nunca copies el protagonista en escenas que no lo
necesitan. La descripción admite 20–600 caracteres; el detalle del prompt,
30–4500; el prompt final debe caber en Direction (6000). Si el estilo existente
es demasiado largo, acórtalo editorialmente sin perder rasgos esenciales antes
de compilar; no trunques automáticamente.

Salida `planificacion_visual/plan_visual_prevoz.json`:

- `script_source` y `script_sha256`: fuente literal; si hay etiquetas de voz o
  espacios exteriores se crea `guion_lectura_limpia.txt` sin cambiar el original.
- `config_sha256`, `scene_count`, `spoken_token_count`, `timing: pending_real_alignment`.
- `scenes`: `id: escena_001`, `source_char_start/end`, `source_word_start/end`
  (final exclusivo), `narration` exacta, `visual_description`, `scene_prompt`
  COMPLETO en inglés con estilo y personajes, `characters`,
  `image_file: imagenes/escena_001.png`, `visual_type` y opcionales cámara/texto.

No escribir `start`, `end` ni estimaciones en este archivo. La skill 3×3 usa
`scene_prompt`; el auxiliar de lotes factoriza únicamente los prefijos exactos
creados por este compilador para enviar estilo y fichas una vez por bloque.
El manifiesto conserva los prompts completos. Los prompts antiguos se mantienen.
La compresión reduce texto repetido, no supone un ahorro exacto de tokens medido.

`check` reutiliza `reuse.source_spans(require_images=False)` para validar antes de
tener PNG. Producción mantiene la verificación de imágenes por defecto.
`check --timing` usa el planificador real y los tiempos Fish del MP3 existente;
su JSON por stdout contiene duraciones, bandas y correspondencia. No escribe
recibos de voz, planes de producción ni aprobación. Con SRT sin palabras deja
el reloj pendiente: no se crean subcortes. Para sincronizar este contrato de
spans al montar se necesita alineación real por palabras; el recorrido antiguo
de `direccion_visual.json` sobre IDs de `prepare` sigue admitiendo SRT.
