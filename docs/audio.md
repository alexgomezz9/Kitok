# Música, efectos y voces

Kitok mezcla recursos locales con FFmpeg. Guardar, comprobar o consultar el catálogo
no sintetiza voz. La selección automática sólo utiliza música cacheada y verificada;
no descarga ni contrata servicios durante la selección. Generar voz nueva sigue siendo
una acción distinta y puede consumir Fish.

## Biblioteca musical y derechos

El catálogo `presets/music_sources.json` contiene **24 pistas de Kevin MacLeod**.
Las 16 incorporadas el 20 de octubre de 2026 se descargaron desde Incompetech y
se comprobaron contra su catálogo oficial y su página individual de licencia.
El 27/10 se añadieron This House, Unnatural Situation, The Dread y Dark Fog
tras descargar y validar catálogo oficial, licencia individual, MP3 y SHA256.
Las ocho candidatas de horror están disponibles en caché local en esa fecha;
una instalación nueva debe ejecutar `fetch` para las que necesite.
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
| Horror y tensión | Darkest Child, Ghost Story, Dark Walk, Anxiety, This House, Unnatural Situation, The Dread, Dark Fog |

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

## Terror de Trazo Maldito

El perfil del canal prescribe `music.mode=auto`, `channel=horror`, `mood=horror`
y dos pistas; se trasladan a `configuracion.json` de episodios nuevos, sin cambiar
música de episodios ya producidos. No heredar el perfil documental de Loose Thread.
El selector usa sólo la caché verificada y no descarga durante render.

Usar un fondo instrumental discreto con ducking, tensión que cambie con el relato
y descansos breves donde el silencio ayude. The Dread y Unnatural Situation son
candidatas de ambiente; This House añade texturas más inquietantes y Dark Fog un
pulso más marcado, según los descriptores del autor. Hay que escuchar la muestra:
no se ha acreditado audición del agente ni una mejora medida de retención. Evitar
coros/vocalizaciones que puedan confundirse con habla del narrador; la música no
sirve para tapar anomalías. El mezclador normaliza las ramas a −19 LUFS para voz
y −29 LUFS para música antes de ducking y normalización final; no configura
todavía una curva musical editorial distinta por cada giro.

Voz: [instrucciones Fish y fidelidad acústica local](fish-voice.md). Las etiquetas
de interpretación no son palabras de subtítulos. El ASR de control no sustituye
la alineación de palabras del montaje ni autoriza cortes semánticos por sí solo.

## Comandos locales

```bash
.venv/bin/python scripts/audio_library.py list
.venv/bin/python scripts/audio_library.py available
.venv/bin/python scripts/audio_library.py fetch all
.venv/bin/python scripts/audio_library.py select --job episodio_v1 --channel loose_thread --mood investigation
.venv/bin/python scripts/audio_library.py select --job episodio_narrativo_v1 --script RUTA_GUION_EXISTENTE.txt
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

La selección narrativa `select_narrative` analiza por separado el inicio (45% de
palabras) y el cierre (35%), conserva sus razones y el hash del guion, y fija dos
pistas distintas compatibles con esos ambientes. En guiones de menos de 36 palabras
usa el ambiente del texto completo. `narrative_options` comprueba que existe una
pareja elegible sin escribir selección ni contactar proveedores. Un cambio de
guion o selección exige una revisión/ID nuevo; se mantienen los contratos del
selector por ambiente y de la elección manual.

`narrative_transition` busca un límite de secciones de transcript validado, con
preferencia por un cambio entre ambientes de inicio/cierre. Comprueba palabras,
orden y tiempos antes de usarlo. Si no hay una alineación válida, declara
`fallback-central-estimated`: un crossfade central estimado, sin afirmar sincronía
semántica. `mix(...,transition_at=segundos)` centra el crossfade en ese instante;
la duración de ambas pistas se adapta para mantener toda la narración. El CLI
equivalente admite `--transition-at`. Omitirlo conserva el centro anterior.

El mezclador hace crossfade, filtra el fondo y baja su nivel bajo la narración.
Normaliza en dos pasos a −16 LUFS y comprueba un pico verdadero máximo de −1,5 dBTP,
con margen de codificación. El recibo `.m4a.json` o `.wav.json` conserva medidas,
créditos, hashes, cambios y eventos. La salida debe ser nueva; nunca sustituye la
narración ni un resultado anterior. Incluir los créditos del recibo en la entrega.

### Duración y diagnóstico de una mezcla fallida

El mezclador conserva los límites: duración solicitada ±80 ms, −16 LUFS ±1 LU,
pico verdadero ≤−1,5 dBTP y mediciones finitas de LUFS, LRA y pico. LRA=7 es el
objetivo del normalizador; la validación no impone una nueva frontera rígida de LRA.
Después de cada normalización/remuestreo reconstruye los timestamps desde el número
de muestras (`asetpts=N/SR/TB`); así los cambios de frecuencia del modo dinámico de
`loudnorm` no acortan el archivo al aplicar el límite temporal de salida.
La regresión usa seis minutos de MP3 sin metadatos Xing/gapless, transitorios que
activan la normalización dinámica, dos músicas automáticas, crossfade y SFX. La
ausencia de esos metadatos es válida; no requiere sustituir la voz de Fish.

Cada intento crea un directorio exclusivo `.audio-mix-*` junto a la salida. Conserva
la petición, selección, SFX, máster PCM/AAC, logs de análisis/codificación y
`validation.json`; un fallo añade `failure.json`. No se eliminan al lanzar una
excepción. La salida validada se enlaza al máster sin duplicar sus bytes y el recibo
indica `mixer_revision` y `diagnostics_directory`. Un error de validación identifica
el límite incumplido y muestra duración esperada/real, LUFS, LRA y pico medidos.

El fallo del trabajo `lf_cf5e16bb422547aabfb4f5b8b9ef131a` se reprodujo sólo con su
voz existente y dos músicas cacheadas, sin red: la mezcla duraba **654,599 s** frente
a **654,733 s** solicitados (−134 ms). Sus **−15,99 LUFS / 3,50 LU LRA / −1,80 dBTP**
eran válidos. Con el reloj de muestras corregido, la misma mezcla conserva esos
niveles y mide **654,733 s**. No fue necesario volver a sintetizar voz ni renderizar
todo el documental para comprobar la corrección.

Evidencia local conservada del incidente (no se distribuyen estos medios por Git):

- `local/audio-failure/final-1792507776156545090/confirmed.wav.json`:
  recibo actual `sample-clock-v2`, con `verification.json` que acredita hashes
  originales intactos y cero intentos de red. El WAV tiene SHA
  `fe1b6d352f82e489c928c7cd8a18273351029e8ce5beaf11357a00ca5970c930`.
- `outputs/evaluation/lf_cf5e16bb422547aabfb4f5b8b9ef131a_recovery_check/`:
  `mix_transition_22s_v1.mp4` y `smoke-evidence.json`; fragmento 397–419 s de esa
  mezcla, incluido cambio musical y SFX, 660 frames 4:2:0 y AAC con decode completo.
  Mide −15,28 LUFS / −2,11 dBTP. El job original sigue fallido; no es su render completo.

El intento antiguo no conservaba su máster: `TemporaryDirectory` lo retiraba al
propagar el error. La reproducción fallida y todos los intentos de esta investigación
se han conservado; el arreglo mantiene también los futuros diagnósticos fallidos.

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
| GABRIEL VO — Professional Spanish Narrator | `53ac6dc4ad314fed88aa28732ad9c87d` | Español castellano según descriptor; API `licensed=true`, publicada. |
| BRIAN — Voz Tranquila y Reflexiva | `f40c5dc43e7e4e3ba641b6e8b53ad7c2` | Español, tono tranquilo/reflexivo declarado; API `licensed=true`, publicada. |

Según la [documentación de listado Fish](https://docs.fish.audio/api-reference/endpoint/model/list-models),
`licensed=true` filtra voces cuyos derechos Fish indica haber obtenido de su titular.
Esto no se deduce del nombre o de que una voz sea pública. Los
[términos Fish](https://fish.audio/terms/) condicionan el uso comercial al servicio
de pago y al respeto de derechos de terceros; una clave configurada no acredita
por sí sola esos derechos. Se conserva la excepción del narrador existente
solicitada por el operador, sin presentarla como una licencia comprobada.

Hay ocho muestras históricas en `outputs/voice-tests/`: plain/tags para cada una
de las cuatro voces anteriores. El runner usa un texto común, pero aquí no se
regeneró ni realineó ese audio. Las siete alternativas nuevas tienen previews
preexistentes del proveedor en `cache/voice-library/`; sus textos difieren y no
constituyen una comparación controlada del mismo guion. Escuchar antes de elegir.
Son **11 voces y 15 muestras** en este checkpoint. Las dos españolas se comprobaron
con GET individual: entrenadas, publicadas, sin retirada DMCA declarada y con
`licensed=true`; no se incorporó la candidata con nombre de una personalidad.
Esto acredita los metadatos del proveedor, no una comprobación independiente de
la identidad ni el contrato privado de consentimiento. Sus previews descargados
conservan hash y procedencia por modelo/task; no se guardan URLs de acceso firmadas.

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
`select_narrative(job_id,script,channel=...)` fija inicio/cierre;
`narrative_options(script,channel=...)` es el preflight sin mutación y
`preview(track_id)` resuelve un MP3 cacheado con hash y symlinks comprobados.
`mix(job_id,narration,output,duration=...,offset=...,sfx_events=[...],transition_at=...)`
entrega una mezcla separada. `VoiceLibrary.list/favorite/assign/assigned/sample` resuelven
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

`outputs/evaluation/audio_library/narrative_boundary_22s.m4a` reutiliza las primeras
cuatro secciones de UltimateBet: 21,805 s, dos pistas y crossfade fuera del centro,
con límite obtenido de la alineación Fish existente tras validar el transcript
completo. El archivo `.narrative.json` guarda las secciones y la razón del cambio.
No es un render del episodio ni una nueva síntesis; queda pendiente escuchar la
adecuación subjetiva de la transición.

## Quitar ruidos de síntesis confirmados

Un hueco de timestamps puede contener ruido, no silencio. Escúchalo antes de
editar. Este auxiliar sólo corta intervalos expresos que no intersecten ninguna
palabra Fish. Puede retirar también habla sintética ajena al guion cuando el
operador la haya identificado expresamente. No detecta artefactos ni decide
cortes por su cuenta.

```bash
.venv/bin/python scripts/repair_stickman_audio.py content/longform/mi_episodio --output content/longform/mi_episodio_sin_ruido --cut 12.1:14.9 --reviewer operador
.venv/bin/python -m kitok.youtube_stickman_es prepare content/longform/mi_episodio_sin_ruido --reuse-images
```

Los tiempos del ejemplo son ilustrativos: sustituir por huecos escuchados y
verificados del episodio. Se puede repetir `--cut`, en orden, para varios tramos.
La salida debe ser una carpeta nueva; no sobrescribe ni reintenta una reparación.
No llama a Fish, ASR ni proveedores y no monta el vídeo. El modelo configurado
no cambia y no se solicita ninguna síntesis nueva.

`--tempo 0.94` es opcional: ralentiza un 6 % mediante FFmpeg `atempo`, conservando
el tono. Admite ajustes suaves entre 0.9 y 1.1; el valor predeterminado es 1.
Los tiempos originales se desplazan por los cortes y se dividen por el tempo,
sin interpolar palabras. El recibo registra y verifica esa transformación y
`--reason` conserva el motivo de revisión. La sincronía acústica sigue sin medirse.

La copia archiva voz, alineación y SRT originales en `audio_original/`; conserva
guion e imágenes con hashes. Recorta PCM a muestras exactas, aplica fundidos de
hasta 5 ms sólo en empalmes y codifica una vez a MP3. Desplaza los tiempos por
la duración eliminada sin borrar ni inventar palabras. La alineación derivada
se identifica como `fish_provider_timestamps_after_audio_cuts`, incluye los
cortes, hashes y revisor, y se contrasta de nuevo con el original al preparar.
La revisión acústica de los empalmes sigue correspondiendo al operador.

Después de preparar y revisar la copia, `produce RUTA_COPIA --reuse-images`
monta con la voz reparada, sin `--generate-voice`. Las validaciones de seguridad y hashes de imágenes siguen vigentes; las fuentes
pequeñas aportadas se escalan al montar y llevan aviso de resolución.

Desde `sample-clock-v3-aac-headroom`, las mezclas nuevas dejan 0,8 dB de margen
antes de AAC (objetivo PCM −2,3 dBTP). Se sigue comprobando el AAC decodificado
con límite −1,5 dBTP. La revisión anterior sigue identificando recibos históricos.

Desde `sample-clock-v4-decoder-tail`, la mezcla conserva también la duración
declarada cuando el decodificador MP3 omite unas muestras de relleno: añade sólo
cola silenciosa hasta el final solicitado, sin recortar ni volver a sintetizar voz.
Los archivos y recibos anteriores se conservan; una mezcla anterior demasiado
corta necesita una revisión nueva, no borrar su caché ni relajar el control del montaje.
