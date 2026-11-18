# Documentales de Loose Thread

Este índice recoge decisiones reutilizables. Las fuentes originales, créditos y
artefactos de un caso viven en su carpeta de episodio. Al retomar, lee el estado,
el guion y la fuente completa de cada dato relevante. Registra una conclusión
nueva donde sirva al siguiente episodio y enlázala a su evidencia.

## Elegir tema y promesa

- Empieza por datos propios disponibles y una muestra acotada de vídeos públicos
  de edad, duración y formato comparables. `public-search` junta datos oficiales
  en una salida corta. Las vistas, el tamaño del canal, la actualidad y el
  potencial visual responden a preguntas distintas. Verifica más de un canal
  cuando afirmes un patrón de mercado.
- Antes de guion, formula el resultado que promete el título y lo que debe
  entenderse de la miniatura en móvil. Elige una promesa que el caso pueda probar.
  Compara referencias para extraer un mecanismo, no para copiar el título.
- La primera escena entrega parte de la promesa con una acción o prueba concreta.
  Usa cambios reales en la historia para recuperar atención. Anota qué preguntas
  abre el vídeo y dónde las resuelve. Escucha y cronometra la apertura antes de
  producir el resto.
- Revisa impresiones y CTR por fuente con Reporting. Contrasta con retención,
  especialmente al comienzo, y con el tramo que realmente vieron. Para saber si
  una variante de título o miniatura gana en un vídeo propio, usa la prueba de
  Studio cuando esté disponible. El resultado se basa en tiempo de reproducción.
  [Recomendaciones](https://support.google.com/youtube/answer/16559650),
  [retención](https://support.google.com/youtube/answer/9314415),
  [A/B](https://support.google.com/youtube/answer/16391400)

## Producir con archivo

Para estudiar una apertura, analiza sólo los tramos que aporten decisiones de
ritmo, música o puesta en escena. [Flujo de referencias](reference-media.md).

Prioriza los recursos que hagan visible la promesa en la apertura, identifiquen
a una persona o lugar, o demuestren un giro. Revisa primero el archivo oficial
y Commons con una búsqueda por persona, fecha o caso. Selecciona sólo lo que
tiene un lugar en el guion. Si ya explicaste el hecho con una prueba legible,
continúa con el siguiente tramo del montaje.

Deja que un documento se pueda leer. Un retrato admite movimiento suave hacia
el rostro. Un clip sirve cuando la acción o el cambio de lugar aporta contexto.
Si una foto de stock describe mejor un objeto o detalle, puedes insertarla
desde Pexels con `usage: "illustration"`, la página, el autor y la licencia.
La [búsqueda de fotos de Pexels](https://www.pexels.com/api/documentation/#photos-search)
permite orientar el resultado a horizontal. Guarda sólo los recursos elegidos.
El resto puede seguir como stock de vídeo de Kitok. Corta al aparecer información
nueva y comprueba el ritmo en la apertura real. [Licencia Pexels](https://www.pexels.com/legal-pages/license/)

Antes de sintetizar la voz larga, traduce la promesa del título en una imagen
de apertura, una prueba que cambie la historia y una imagen para el cierre.
Para cada momento, apunta en el brief qué afirmación respalda el recurso y qué
permite su licencia. Resuelve los huecos con un gráfico propio o cambia la
promesa si no puedes sostenerla visualmente. Comprueba esa secuencia con el
texto y las imágenes elegidas. El JSON parcial fija esos recursos y Kitok
resuelve el montaje entre ellos.

Para una cronología breve, superpón un momento verificable a la foto o plano
que lo sitúa. Revela la siguiente hora o fecha cuando cambia algo en el relato.
Si necesitas mostrar dos sucesos a la vez, compón ambos en el mismo plano con
una jerarquía clara. Prueba dos fotogramas a tamaño pequeño antes de exportar.
Para planos específicos puedes usar [HyperFrames o Remotion](../integrations/agent-tools.md).
Renderiza sólo los planos cuya explicación mejore con un compuesto a medida.
Las fotos reales y las de stock admiten panes, recortes y rótulos del motor nativo.
Usa la colección habitual de stock entre puntos explícitos. Un sonido ligado a
una acción o a la aparición de una prueba puede usar el mismo ancla de guion.
[Edición y previsualización por escena](../editing.md#preparar-un-montaje),
[efectos anclados](../audio.md#efectos-en-el-montaje-de-un-largo-native).

1. Busca y descarga el documento, foto o clip verificable antes de pedir trabajo al
   operador. Registra fuente original, identidad, fecha, derechos y cambios. Usa
   stock para ambiente. Para un mecanismo sin imagen directa, considera un gráfico
   claro o una ilustración de IA. Si la reconstrucción realista puede confundirse
   con un hecho grabado, aclárala y aplica la declaración de YouTube.
   [Política sobre contenido sintético](https://support.google.com/youtube/answer/14328491)
2. Guarda `guion_final.txt`, los medios que se usan y `configuracion.json` con
   `visual_plan`. Para cada inserto marca una frase breve del guion. Por ejemplo,
   al decir “the domains were seized”, el archivo `images/doj-2011-04-15.png`
   entra en el tiempo de esa frase según el reloj Fish. El agente escribe el JSON
   y Kitok calcula segundos y cortes. Ajusta `occurrence` si la frase se repite.
   [Contrato](../editing.md#json-parcial-sobre-montaje-automático)
3. Guarda los episodios en `content/longform/loose_thread/<NNN_tema>`.
   Prepara los campos de Studio y la miniatura final. Valida con
   `longform.py CONFIG --deliver --dry-run`. Cuando toque producir, ejecuta
   `--deliver` y reutiliza voz, alineación y montaje confirmado. Con un MP4
   validado, `--deliver-only` sólo empaqueta los archivos.
   [Guía de operación](../../GUIA.md#entrega-para-youtube-studio)
4. Comprueba la apertura y los insertos que demuestran un giro. Atiende los
   avisos técnicos y revisa créditos y ajustes de Studio. Kitok monta el stock,
   mezcla la voz y prepara la carpeta `entrega/`. Conserva un estado breve
   con el siguiente paso y retira capturas de QA y descargas duplicadas.

## Consultar datos sin copiar archivos de petición

```bash
export PYTHONPATH=src
.venv/bin/python scripts/youtube_api.py --directory local/youtube \
  --channel UCLnP8Kb1USd06TW3D1JLFvg reporting-status
.venv/bin/python scripts/youtube_api.py --directory local/youtube \
  --channel UCLnP8Kb1USd06TW3D1JLFvg public-search "online poker Black Friday documentary" \
  --limit 20 --min-views 1000 --max-subscribers 20000
.venv/bin/python scripts/youtube_api.py --directory local/youtube \
  --channel UCLnP8Kb1USd06TW3D1JLFvg query --request /dev/stdin <<'JSON'
{"operation":"youtubeAnalytics.reports.query","params":{"ids":"channel==MINE","startDate":"2026-10-01","endDate":"2026-11-10","metrics":"audienceWatchRatio,relativeRetentionPerformance","dimensions":"elapsedVideoTimeRatio","filters":"video==K6e14xzpolI","sort":"elapsedVideoTimeRatio"}}
JSON
```

La última petición ilustra retención por tramo para el vídeo de UltimateBet.
Cambia el ID y el periodo por los del vídeo que analizas.

La muestra usa una página de búsqueda y recuentos publicados. Se mantienen los
suscriptores ocultos como dato ausente. Las comparaciones históricas y métricas
derivadas para un producto de análisis tienen condiciones específicas.
[Políticas de métricas derivadas](https://developers.google.com/youtube/terms/derived-metrics-policy)
