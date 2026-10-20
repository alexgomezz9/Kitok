# Música, efectos y voces

Kitok mezcla recursos locales con FFmpeg. Guardar, comprobar o consultar el catálogo
no sintetiza voz. La selección automática sólo utiliza música cacheada y verificada;
no descarga ni contrata servicios durante la selección. Generar voz nueva sigue siendo
una acción distinta y puede consumir Fish.

## Biblioteca musical y derechos

El catálogo `presets/music_sources.json` contiene **20 pistas de Kevin MacLeod**.
Las 16 incorporadas el 20 de octubre de 2026 se descargaron desde Incompetech y
se comprobaron contra su catálogo oficial y su página individual de licencia.
Todas están bajo CC BY 4.0: permiten uso comercial con atribución, enlace a licencia
e indicación de los cambios. No se suben los MP3 a Git.

Cada carpeta `cache/audio-library/ID/` conserva música, página de licencia,
registro oficial de la pista y recibo con SHA256, duración, fecha y procedencia.
Una descarga con hash distinto o sin la licencia esperada se rechaza. Un cache hit
comprueba esos hashes; no vuelve a consultar la licencia remota.

La clasificación editorial orienta la selección; no demuestra calidad ni adecuación
sin escuchar. `source_feel` e instrumentos conservan descriptores del autor en las
pistas nuevas. Content ID permanece **desconocido**: licencia comercial y ausencia
de reclamaciones automáticas son cuestiones diferentes.

| Uso editorial | Pistas candidatas |
| --- | --- |
| Investigación y misterio | Long Note Two, Echoes of Time v2, Crypto, Lightless Dawn, Mesmerize, On the Ground |
| Avance y revelación | Deep Haze, The Descent |
| Reflexión y cierre | Dreams Become Real, Night Vigil, Despair and Triumph, Anguish, Immersed |
| Ambiente tranquilo | Floating Cities, Clean Soul, Deliberate Thought |
| Horror y tensión | Darkest Child, Ghost Story, Dark Walk, Anxiety |

Las categorías se solapan; el JSON conserva ambientes base y canales. Las afinidades
adicionales viven en `AUDIO_AFFINITIES`, separadas de la evidencia de licencia:
`technology` (Floating Cities, Deep Haze, Deliberate Thought), `business` (Crypto,
On the Ground, Deep Haze), `history` (Night Vigil, Despair and Triumph, Anguish,
Echoes of Time v2), `revelation` (The Descent, Lightless Dawn, Crypto). Se basan en
instrumentos y descriptores del autor; son decisiones editoriales de Kitok sin
audición humana acreditada. La API/CLI las expone junto a los ambientes base, pero
no modifica los recibos originales ni acepta discrepancias de procedencia.
Horror queda fuera de la selección de Loose Thread. No se elige música únicamente
por una palabra en el título del vídeo.

Fuentes evaluadas para esta fase:

| Fuente primaria | Decisión |
| --- | --- |
| [Incompetech, catálogo oficial](https://incompetech.com/music/royalty-free/pieces.json) y las páginas por ISRC del catálogo | Incorporada: identidades y descargas fijas, evidencia individual y licencia explícita. [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) exige conservar créditos/cambios. |
| [Biblioteca de audio de YouTube](https://support.google.com/youtube/answer/3376882?hl=es) | Alternativa de importación futura. La descarga y atribución se gestionan en YouTube Studio; no se cambió el OAuth ni se automatizó una sesión del titular. |
| [Licencia Pixabay](https://pixabay.com/service/license-summary/) | Permite adaptación y uso bajo sus condiciones; no se incorporaron pistas sin evidencia individual. No redistribuir el recurso aislado como producto propio. |
| [Licencias Mixkit](https://mixkit.co/license/) | Tiene licencias diferentes por recurso. No se auditó ningún MP3 individual ni se añadió un descargador; no se presume una licencia común para todo el sitio. |
| [Free Music Archive](https://freemusicarchive.org/Help) | Consulta oficial devolvió HTTP 403 en esta sesión. Sin evidencia actual suficiente para incorporar pistas de esa fuente. |

## Comandos locales

```bash
.venv/bin/python scripts/audio_library.py list
.venv/bin/python scripts/audio_library.py available
.venv/bin/python scripts/audio_library.py fetch all
.venv/bin/python scripts/audio_library.py select --job episodio_v1 --channel loose_thread --mood investigation
.venv/bin/python scripts/audio_library.py select --job episodio_manual_v1 --track mesmerize
.venv/bin/python scripts/audio_library.py mix --job episodio_v1 --narration RUTA_AUDIO_EXISTENTE.mp3 --duration 30 --output outputs/mi_mezcla_v1.m4a
```

Sólo `fetch` descarga. `available` lista archivos con hashes válidos, sin selección
ni creación de subcarpetas de pistas ausentes. `select` persiste la elección por
trabajo y rota la pista principal entre trabajos cuando hay alternativas. La misma
revisión conserva la selección; cambiar canal/ambiente/pista exige un ID nuevo.
La elección manual conserva exactamente la pista indicada. Se requieren dos pistas
cacheadas para la selección automática predeterminada y una para la manual.

`infer_audio_mood` examina el guion completo y el perfil del canal; nunca el título.
Usa vocabularios acotados, exige dos términos distintos, limita el peso de las
repeticiones y mantiene el ambiente predeterminado cuando hay empate o ambigüedad.
Para Loose Thread devuelve `investigation`, `reflective`, `resolution`, `ambient`,
`technology`, `business`, `history` o `revelation`; cada uno tiene al menos dos
pistas compatibles. `science` parte de `ambient`;
`horror` y `lore` pueden usar `horror`. Es una heurística conservadora, no comprensión
general del tono ni garantía de idoneidad musical. La caché/licencias se validan
después; inferir un ambiente nunca descarga pistas ni sintetiza voz.

El mezclador hace crossfade, filtra el fondo y baja su nivel bajo la narración.
Normaliza en dos pasos a −16 LUFS y comprueba un pico verdadero máximo de −1,5 dBTP,
con margen de codificación. El recibo `.m4a.json` o `.wav.json` conserva medidas,
créditos, hashes, cambios y eventos. La salida debe ser nueva; nunca sustituye la
narración ni un resultado anterior. Incluir los créditos del recibo en la entrega.

## Efectos discretos originales

Hay seis familias procedurales sin voces ni grabaciones externas:

| ID | Uso discreto |
| --- | --- |
| `soft_tick` | Aparición puntual de una cifra o marca |
| `low_pulse` | Dato relevante o cambio de peso narrativo |
| `air_swish` | Paso de una composición, con ruido filtrado breve |
| `paper_texture` | Resaltado de documento, textura de ruido en ráfagas |
| `key_click` | Interfaz o escritura, transitorio sintetizado |
| `ui_ping` | Confirmación o pequeño énfasis, parciales senoidales |

Son texturas originales, no Foley grabado ni recreaciones verificadas de objetos
reales. El ruido usa una semilla fija, sin dependencias ni modelos adicionales.
No se añaden indiscriminadamente a todos los planos. Se producen por separado:

```bash
.venv/bin/python scripts/audio_library.py sfx --kind soft_tick --output outputs/tick_v1.wav
```

Para incorporarlos a una mezcla, un archivo JSON contiene, por ejemplo:

```json
[{"time":3.0,"kind":"soft_tick"},{"time":13.0,"kind":"low_pulse"}]
```

Añade `--sfx-events RUTA_EVENTOS.json` a `mix`. Los tiempos son relativos al fragmento
mezclado, incluso cuando se usa `--offset`. Se validan tipo, límites del fragmento,
un máximo de 24 eventos y separación mínima de 1,5 s. Esta protección técnica no
sustituye el criterio editorial: no añade eventos automáticamente a cada plano.
No se aceptan rutas de grabaciones arbitrarias dentro de los eventos.

## Voces Fish sin nuevas síntesis

El narrador predeterminado de Loose Thread sigue siendo
`e686ae649ee44f219a108aacba206c1a`, por petición del operador.
El 20 de octubre se hicieron consultas reales `GET /model/{id}` para las cuatro
voces con muestras anteriores y `GET /model?licensed=true&language=en` para buscar
alternativas. No se llamó a TTS, Voice Design ni creación/clonación de voces.

`presets/voice_sources.json` conserva IDs, idiomas/tags declarados por Fish, fecha,
URLs de evidencia y muestras con hashes. Los tags describen metadatos del proveedor;
no representan una evaluación auditiva de Kitok.

| Voz | Reference ID | Estado comprobado |
| --- | --- | --- |
| Loose Thread Narrator | `e686ae649ee44f219a108aacba206c1a` | Predeterminada existente; API `licensed=false`. No acredita autorización del titular. |
| Adrian | `bf322df2096a46f18c579d0baa36f41d` | Autor Fish Official; API `licensed=false`. Sólo catálogo de muestras anteriores. |
| Ethan | `536d3a5e000945adb7038665781a4aca` | Autor Fish Official; API `licensed=false`. Sólo catálogo de muestras anteriores. |
| Narrator | `0327fdb5da9e4fd782899a8058c8ae2b` | API `licensed=false`. Sólo catálogo de muestras anteriores. |
| Dave — Australian Male | `a754ca8729d642d9a918a42b5b6a77d1` | Inglés; API `licensed=true`, publicada. |
| Calm Narrator Voice | `6d71c24e892b467ebef21f3dd3f4810a` | Inglés; API `licensed=true`, publicada. |
| Calm Reflective Male | `afe69eaecd7b49d1b564b06421ce3706` | Inglés; API `licensed=true`, publicada. |
| kevon | `bf4a01bacf1b43b188c2c13ebdc77166` | Inglés; API `licensed=true`, publicada. |
| Calm Observer | `0b2331767e7244218e1043a1b44ec6ea` | Inglés; API `licensed=true`, publicada. |

Según la [documentación de listado Fish](https://docs.fish.audio/api-reference/endpoint/model/list-models),
`licensed=true` filtra voces cuyos derechos Fish indica haber obtenido de su titular.
Esto no se deduce del nombre o de que una voz sea pública. Los
[términos Fish](https://fish.audio/terms/) condicionan el uso comercial al servicio
de pago y al respeto de derechos de terceros; una clave configurada no acredita
por sí sola esos derechos. Se conserva la excepción del narrador existente
solicitada por el operador, sin presentarla como una licencia comprobada.

Hay ocho muestras históricas en `outputs/voice-tests/`: plain/tags para cada una
de las cuatro voces anteriores. El runner usa un texto común, pero aquí no se
regeneró ni realineó ese audio. Las cinco alternativas nuevas tienen previews
preexistentes del proveedor en `cache/voice-library/`; sus textos difieren y no
constituyen una comparación controlada del mismo guion. Escuchar antes de elegir.

```bash
.venv/bin/python scripts/voice_library.py list
.venv/bin/python scripts/voice_library.py sample baseline
.venv/bin/python scripts/voice_library.py favorite dave
.venv/bin/python scripts/voice_library.py assign science dave
.venv/bin/python scripts/voice_library.py inspect baseline
.venv/bin/python scripts/voice_library.py discover --language en --limit 10
```

Sólo `inspect` y `discover` usan la clave Fish existente para una consulta GET
acotada, sin reintentos ni redirecciones. No actualizan automáticamente el catálogo:
los candidatos necesitan revisión de identidad y derechos. La salida no incluye
claves. Los otros comandos son locales. Favoritos/asignaciones se guardan en
`state/voice-preferences.json` con bloqueo y escritura atómica. Favorito permite
conservar una muestra histórica; asignar una voz nueva requiere `licensed=true`
o la predeterminada existente. Un catálogo no garantiza disponibilidad futura.

## Interfaces y verificación

`AudioLibrary.available(channel=None,mood=None)` consulta caché;
`select(job_id,channel=...,mood=...,count=2)` y
`select_manual(job_id,track_id,channel=...)` fijan selección;
`mix(job_id,narration,output,duration=...,offset=...,sfx_events=[...])` entrega una
mezcla separada. `VoiceLibrary.list/favorite/assign/assigned/sample` resuelven
preferencias y previews locales por ID; `sample` comprueba hash y rutas controladas.

Pruebas del módulo: procedencia, hash, licencia cambiada, redirecciones, descarga
acotada, symlinks, bloqueo, repetición, mezcla real FFmpeg, ducking, duración,
sonoridad/pico, SFX temporizados, estado corrupto, favoritos y límites de previews.
Estas pruebas no demuestran derechos de terceros ni calidad auditiva subjetiva.

Demostración real de 20 s:
`outputs/evaluation/audio_library/phase_mesmerize_sfx_20s.m4a`, narración cacheada
sin nueva síntesis, Mesmerize, tick a 3 s y pulso a 13 s. Medición del archivo:
−16,00 LUFS / −1,99 dBTP. No se modificó el audio original ni se generó el episodio
completo. La aprobación auditiva del operador sigue pendiente.

La ampliación de efectos añade `outputs/evaluation/audio_library/sfx_families/`:
seis WAV individuales, `six_families.wav` para comparar las texturas y
`narration_six_families_20s.m4a` para escucharlas bajo la misma narración existente.
El orden es tick, pulse, swish, paper, key, ping. Estos archivos no requieren Fish.
