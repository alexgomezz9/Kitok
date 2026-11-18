# Analizar una referencia audiovisual

Usa una ventana de 15 a 45 segundos centrada en una decisión. Para material que
puedas descargar o un vídeo propio, basta el [script local](../../scripts/reference_media.py).

```bash
.venv/bin/python scripts/reference_media.py /ruta/autorizada/video.mp4 \
  --start 0 --duration 25 --language en --sound --sheet /ruta/temporal/fotogramas.jpg
```

[yt-dlp](https://github.com/yt-dlp/yt-dlp) descarga una referencia cuando le das
una URL HTTPS habilitada para descargar. FFmpeg recorta el tramo y extrae
fotogramas y candidatos de corte. [Faster Whisper](https://github.com/SYSTRAN/faster-whisper)
transcribe en local con tiempos por palabra. `--sound` ejecuta
[Earshot](https://github.com/Leonxlnx/earshot) para proponer eventos y medir
el nivel. El JSON se escribe en stdout y la hoja sólo se guarda si se pide.
Usa `--no-asr` si sólo necesitas imagen o si ya tienes la transcripción.

Kitok tiene las herramientas locales en `local/tools/yt-dlp`,
`local/tools/whisper-asr/` y `local/tools/earshot/`. Faster Whisper utiliza el
modelo `local/asr-models/whisper-small/`. Earshot lee sus pesos de
`local/tools/earshot/models/hf/`. Se reutilizan los pesos y los archivos de
análisis descartables se retiran al terminar. Una instalación sin esos
componentes puede analizar fotogramas con `--no-asr` y sin `--sound`.

Para estudiar YouTube, empieza por el reproductor y la transcripción disponible
en la página. Con el archivo propio o una descarga autorizada puedes analizar
un tramo localmente. Confirma lo que parezca un corte, comprueba el sonido
si es determinante y explica en una frase qué decisión cambia para el episodio.
Los cortes suaves y el tipo de música pueden requerir comprobación a oído.

## Referencias de apertura para Loose Thread

Fotogramas muestreados en YouTube el 18/11/2026. La muestra permite estudiar
encuadres, continuidad, rótulos y tipos de recurso. Los tiempos de corte y la
mezcla sonora requieren ver y escuchar el intervalo continuo.

| Referencia | Observación y aplicación |
| --- | --- |
| [fern, Västberga](https://www.youtube.com/watch?v=PSHQ_MuxxNw&t=15s) | A 0:05 y 0:15 muestra a la misma trabajadora con auriculares desde distintos encuadres. A 0:35 cambia de perspectiva y aparece un policía en el coche. Para un episodio propio, vuelve al mismo lugar u objeto desde otra escala antes de cambiar de tema. |
| [VAUX, Fortaleza](https://www.youtube.com/watch?v=ChlkHIJ4ASA&t=50s) | A 0:10 sitúa el lugar con imagen aérea y a 0:50 reduce el interior a líneas y un dato legible. Guarda el compuesto para explicar algo que la foto exterior no puede enseñar. |
| [Lume, Fortaleza](https://www.youtube.com/watch?v=3kY4Oo5Bmrs&t=25s) | A 0:10 muestra un detalle junto a la furgoneta y a 0:25 se entiende el papel de la furgoneta gracias al rótulo de la empresa. El texto puede trabajar sobre un objeto en escena, sujeto a la legibilidad. |
| [Lume, Don Johnson](https://www.youtube.com/watch?v=gy3kbrmm4R0&t=60s) | Se vieron exterior, mesa y monitor de vigilancia en las muestras de 0:00 a 0:20. En 1:00 aparece una foto real del protagonista con la cifra de resultado. Al identificar a alguien, reserva una prueba visual que pague esa parte de la promesa. |

Para una muestra de Västberga se probó exterior a tejado, una foto del aparato
con rótulo nativo y una composición de la cifra del expediente. Se usó música
de la biblioteca, un soplo discreto en el cambio de plano y efectos al aparecer
rótulo y cifra. Son decisiones propias de montaje. Para un largo con voz,
comprueba los efectos a su nivel final y deja respirar los cortes ordinarios.

Aplica la decisión en el [plan visual](../editing.md), la
[biblioteca de audio](../audio.md) o el guion. Por ejemplo, colocar un sonido
de carta en el momento en que se demuestra el giro y reservar el resto de la
frase para la voz. El agente prepara esos datos. Kitok temporiza imágenes y
clips, aplica movimientos, mezcla y entrega el vídeo. Guarda en el episodio la
fuente, el intervalo y la lección aplicable. Retira la hoja de fotogramas al cerrar
si ya cumplió su función.

## Visor de montaje y editor Concat

El concat de FFmpeg de Kitok ensambla fragmentos normalizados por copia de
stream. El historial de main registra el ensamblado Native desde f1dbc90
(15/10/2026) y el editorial desde 631ba3b (20/10/2026). El modo
`--preview-scenes` del render editorial ya usa la mezcla y los planos cacheados
para rehacer una selección. Consultar [montaje](../editing.md#preparar-un-montaje).

El editor de escritorio [Concat](https://github.com/jub0t/Concat) sí aporta
línea de tiempo multipista, reproducción y cortes manuales. Su
[API y MCP](https://github.com/jub0t/Concat/blob/main/docs/MCP.md) permiten crear
un proyecto e importar archivos locales. La sincronización en vivo con el
proyecto abierto en pantalla sigue descrita en la
[incidencia 337](https://github.com/jub0t/Concat/issues/337).

Un piloto útil importaría, por orden y sin copias, los planos ya normalizados
y la mezcla del episodio usando un reloj común. Habría que verificar duración
por frame, alineación, medios accesibles desde Windows y que se pueda editar y
exportar una revisión conservando el plan de Kitok como fuente. Abrir el MP4
final sirve para verlo de forma inmediata. Editar el MP4 no recupera las capas
ni conserva la reutilización de los planos al devolver cambios. Mantener el
editor como opción de revisión hasta validar esas cuatro condiciones. Fuente
consultada el 18/11/2026. Integración y compilación no probadas.
