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

`voice.transcript_verification: "local_asr"` en `configuracion.json` activa un
reconocimiento independiente **local**, antes de planificar/mezclar/renderizar.
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
Las diferencias y ventanas con energía suficiente bloquean la continuación.
Una ventana energética puede ser respiración, música o voz: **no demuestra habla**.
El ASR puede confundir nombres, cifras o sonidos: **no autoriza cortes**.
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
