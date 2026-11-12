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
3. Ejecuta la validación local y revisa si existe una narración compatible.
   Para un largo nuevo usa `.venv/bin/python longform.py CONFIG --dry-run` y luego
   el mismo comando sin `--dry-run` cuando el encargo incluya producir.
   Para reusar una voz del estudio sigue la auditoría documentada. El agente
   puede usar la API local cuando haga falta ese recorrido.
   [Guía de operación](../../GUIA.md)
4. Comprueba el MP4, la entrada y salida de cada prueba visual y la narración.
   Los créditos acompañan a la entrega. Conserva un estado breve con el siguiente
   paso y referencias. Elimina capturas de QA, descargas duplicadas y archivos de
   montaje de prueba que ya no hagan falta.

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
