# Dirección Fish y fidelidad de la narración

Consulta oficial: **27/10/2026**. Una marca temporal del proveedor corresponde al
texto que Fish declara haber generado; no acredita todo lo que se oye. La
comprobación independiente reconoce únicamente el audio, sin darle el guion como
prompt. Sus diferencias también pueden ser errores de reconocimiento.

## Instrucciones que admite Fish

El modelo usado por Jason es `s2.1-pro-free`. La documentación S2 indica corchetes;
los paréntesis corresponden a S1 antiguo. Algunas indicaciones documentadas:

| Intención | Marcadores S2 |
| --- | --- |
| Pausa breve / larga | `[break]` / `[long-break]` |
| Susurro / voz suave | `[whispering]` / `[soft tone]` |
| Énfasis | `[emphasis]` antes de la palabra |
| Intriga / miedo / inquietud | `[curious]`, `[scared]`, `[nervous]` |
| Calma / sorpresa / determinación | `[calm]`, `[surprised]`, `[determined]` |
| Sonidos humanos | `[sighing]`, `[gasping]`, `[laughing]` |

Fish admite además descripciones libres breves, por ejemplo `[mysterious]`.
`[pausa]` en español no es un token canónico documentado. Las pausas no prometen
milisegundos exactos; no reemplazan la comprobación del audio. Usar pocas señales,
normalmente al inicio de la frase, y reservar susurro/énfasis para giros concretos.
No fabricar voces de fondo, cánticos, risas ni respiraciones que el relato no pide.

El cliente actual transmite el texto de síntesis con `[]`; `clean_script` retira
esas señales al calcular texto hablado y subtítulos. **No se ha sintetizado una
muestra real con etiquetas en este encargo**, ni demostrado su expresividad o
alineación acústica con esta voz. No añadirlas retrospectivamente a Jason ni
presentar esa combinación como verificada. Conservar guion hablado limpio y
decisiones de interpretación aparte hasta validar una muestra corta y el
contrato texto limpio → texto TTS → timestamps. No mezclar la sintaxis de Drama3,
S1 y S2, ni cambiar modelo para habilitar una señal sin revisar compatibilidad.

Fuentes principales: [control emocional Fish](https://docs.fish.audio/developer-guide/core-features/emotions),
[modelos Fish](https://docs.fish.audio/developer-guide/models-pricing/models-overview).

## Comprobación local antes de montar

`voice.transcript_verification: "local_asr_autocut"` es el valor de `init` para
episodios stickman nuevos: reconoce la voz cruda, recorta inserciones verificables
en una copia PCM y reconoce de nuevo ANTES de planificar/mezclar/renderizar.
`"local_asr"` conserva el modo anterior de diagnóstico sin recortes.
`"off"` conserva compatibilidad con episodios antiguos. No cambia el modelo Fish,
no vuelve a sintetizar, no sube audio y no necesita tarjeta. No activa ASR en todos
los shorts/documentales; este control pertenece a `youtube_stickman_es`.

El runtime opcional está separado del `.venv` principal. Usa faster-whisper con
Whisper small multilingüe, CPU/int8, cuatro hilos, sin CUDA. Reutiliza los modelos
ya descargados y desactiva descargas durante el reconocimiento. Los valores
predeterminados son `local/tools/whisper-asr/bin/python` y
`local/asr-models/whisper-small`; `LOCAL_ASR_PYTHON` / `LOCAL_ASR_MODEL` permiten
cambiarlos en `.env`. Preparación explícita de un entorno nuevo:

```bash
python3 -m venv local/tools/whisper-asr
local/tools/whisper-asr/bin/python -m pip install faster-whisper==1.2.1 av==16.0.1
local/tools/whisper-asr/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('Systran/faster-whisper-small',
    revision='536b0662742c02347bc0e980a01041f333bce120',
    local_dir='local/asr-models/whisper-small',
    allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'])
PY
.venv/bin/python scripts/verify_stickman_voice.py content/longform/mi_episodio --transcribe
```

La descarga requiere Internet; analizar después no. PyAV16.0.1 está fijado porque
PyAV19 produjo una incompatibilidad reproducida con faster-whisper1.2.1.
Modelo y runtime ocupan aproximadamente **0,94GB combinados** en esta instalación,
compartidos por episodios, fuera de Git; no se copian dentro de cada vídeo.
[Implementación y CPU/int8 oficiales](https://github.com/SYSTRAN/faster-whisper).

El informe queda en `.stickman/voice-fidelity/HASH/`: transcript ASR, diferencias,
actividad audible fuera de las marcas de palabras y hashes de audio/guion/modelo.
Se conserva y reutiliza; los cambios en entradas/modelo crean otra identidad.
En el modo de diagnóstico, las diferencias y ventanas con energía suficiente
bloquean la continuación. El modo de recorte intenta quitar sólo inserciones
con anclas y separaciones válidas y vuelve a comprobar todo el audio.
Una ventana energética puede ser respiración, música o voz: **no demuestra habla**.
El ASR puede confundir nombres, cifras o sonidos: **una diferencia sola no
autoriza un corte**. Reemplazos y omisiones no se eliminan automáticamente.
Las voces/susurros que coincidan temporalmente con palabras pueden escapar al
detector energético; tampoco se garantiza detectar todas las alucinaciones.

El revisor comprueba las diferencias contra audio/guion y registra motivo real:

```bash
.venv/bin/python scripts/verify_stickman_voice.py content/longform/mi_episodio \
  --accept-differences --reviewer OPERADOR --reason 'Motivo concreto tras revisar todas las diferencias'
```

Ese comando acepta explícitamente el informe; no convierte al ASR en infalible ni
certifica sincronía humana. No usarlo para saltarse habla extra sin resolver.
Para importar una transcripción local ya hecha existe `--import-asr ARCHIVO.json`;
debe declarar `audio_sha256`, `engine: "faster-whisper-cpu-int8"` y `model_files`
con los hashes exactos de los archivos del modelo. La importación se etiqueta
como declaración externa de procedencia; no se confunde con ejecutar el worker.
Un fallo conserva audio e informe y no lanza otra síntesis. Los cortes existentes
siguen exigiendo intervalos revisados, margen respecto a palabras y revisión nueva.

## Jason: hallazgo actual

La voz original contiene numerosas inserciones candidatas, además del hueco de
9,28s retirado anteriormente. La transcripción local reconoce variantes como
«non tantaneni», «montantani» y «tannen asadn», ausentes del guion. Incluye también
diferencias benignas posibles, como nombres o cifras escritas en números.
La investigación distingue esas categorías y conserva las ventanas originales;
no declara escucha humana ni elimina automáticamente palabras.


Una revisión adicional del original cerca393.72–401.78s detecta pseudo-habla
antes del corte anterior. Una frase de14palabras marcada por Fish tampoco se
recupera en reconocimiento local de esa zona: posible omisión/sustitución en el
TTS original, pendiente de escucha. Cortar añadidos no reconstruye contenido
faltante. No confundir conservar1411palabras en JSON con verificar1411palabras
pronunciadas. La auditoría real y sus límites están en
[producción](youtube-production-audit.md#comprobacion-real-de-voz).


## Recorte automático antes del montaje

```bash
.venv/bin/python scripts/verify_stickman_voice.py content/longform/mi_episodio --cut-insertions
```

No monta vídeo ni llama a Fish. Busca inserciones entre anclas exactas y únicas
del guion, conserva margen de40ms junto a palabras reconocidas y prefiere silencios
medidos para fijar cortes. Los timestamps ambiguos se contrastan en ventanas con
ASR local, sin prompts ni guion. Se guarda PCM de muestra exacta, plan, recibo y
hashes en `.stickman/voice-cleaning/`; `voz.mp3` y su recibo Fish no se modifican.

La segunda transcripción se compara con el guion completo. Sólo un resultado
coincidente, con palabras individuales observadas y sin inserciones ambiguas,
puede convertirse en narración de montaje. Kitok usa entonces ese WAV, su SRT y
su reloj ASR real también en mezcla, QA y subtítulos; no etiqueta esos tiempos
como si procedieran de Fish. Un resultado parcial permanece disponible para
inspección y bloquea el montaje: no se acepta porque existan un WAV o un recibo.

Una frase realmente sustituida por cánticos necesita reparar esa frase; cortar
no recupera su texto. Las diferencias de nombres/cifras pueden exigir revisión.
Este mecanismo no promete detectar todas las alucinaciones de cualquier voz.
Los episodios antiguos conservan `off`/`local_asr` y sus hashes; no activar el modo
editando una entrega ya preparada: usar una revisión de entradas independiente.


## Comparación API realizada27/10

Mismo texto de64palabras tomado de los dos primeros párrafos de guion_final.txt,
modelo s2.1-pro-free, speed0.98, dos referencias (Jason/Loose Thread), endpoint
directo y endpoint con timestamps. Jason presenta una inserción en ambas rutas;
Loose Thread también da diferencias al leer español pese a ser referencia inglesa.
No apareció repetición de bloques binarios en los16/18eventos de audio recibidos.
Esto descarta que sea únicamente la mezcla o el quemado de subtítulos; no aísla
una causa universal del modelo ni prueba que todas las diferenciasASR sean habla extra.

La captura del operador muestraDrama3. La documentación oficial permite usar
model:drama-3 en el mismo POST/v1/tts; esa muestra corta devolvióHTTP402 y no se
reintentó. No se ha comprobado por API el mismo modelo de la web ni se cambió el
modelo global. Ver [Drama3](https://docs.fish.audio/features/text-to-speech/drama-3)
y [tarifas oficiales](https://docs.fish.audio/developer-guide/models-pricing/pricing-and-rate-limits).
La web pública puede mostrar etiquetas antiguas; no usar su HTML cacheado para
contradecir el modelo que el operador vio realmente seleccionado.

Jason se reparó sobre el original:24recortes automáticos,1recorte editorial por
ancla ambigua del nombre y2frases/19palabras recuperadas con la misma voz. La
segunda ASR completa no encontró inserciones y dejó14diferencias(nombres/cifras,
variantes de reconocimiento). No acredita escucha humana ni guion acústicamente
perfecto. El WAV resultante dura435.728708s; todavía no es un MP4 final ni cumple
por sí solo el objetivo de duración del canal. No alargar con cánticos/silencios.
