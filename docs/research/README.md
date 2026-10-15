# Investigación y decisiones editoriales

Los catálogos y estudios fechados son referencias aportadas por el operador.
Sus métricas y recomendaciones no acreditan capacidades instaladas ni ingresos.
Lee PROJECT_STATUS.md para saber lo que funciona y GUIA.md para operarlo.

## Decisión técnica del incremento

Se revisaron49 candidatos. Para RTX 3050 Laptop 4 GB / RAM 8 GB elegimos los componentes
ya disponibles: FFmpeg, Pillow y ASS. El piloto real1080p valida ese camino;
no se instalaron decenas de repositorios ni modelos generativos. Se reutilizaron
el motor, audio Fish y stock en caché. Los filtros y mediciones usados están
cubiertos por la [documentación FFmpeg](https://ffmpeg.org/ffmpeg-filters.html).

| Candidato | Decisión y condición para reconsiderarlo |
|---|---|
| FFmpeg/Pillow/ASS | Adoptados: gráficos, movimiento suave, render por plano, hashes y QA real. Sin nuevo framework. |
| Motion Canvas | Posponer: animación vectorial cuando un plano concreto lo justifique. No se hizo benchmark comparativo; no declaramos que sea más lento. |
| Remotion | Posponer: otro runtime/Chromium no resolvía la selección de planos. Revisar su licencia específica antes de integrarlo. |
| pypdfium2 | Candidato para un PDF auténtico que necesite recorte/resalte. No instalado ni simulado como documento histórico. |
| rembg | Candidato para personajes con recursos autorizados; revisar licencia de pesos y usar modelo local explícito. No instalado. |
| whisper.cpp | Alternativa si faltan timestamps útiles; no se descargaron modelos porque ya había audio/alineación Fish. |
| Generación pesada de vídeo/avatares | Fuera del camino diario de 4 GB: no necesaria para el A/B, sin benchmark local. |

Referencias técnicas primarias: [Pillow](https://pillow.readthedocs.io/),
[Motion Canvas](https://github.com/motion-canvas/motion-canvas),
[Remotion](https://www.remotion.dev/license),
[PDFium](https://pypdfium2.readthedocs.io/),
[rembg](https://github.com/danielgatis/rembg),
[whisper.cpp](https://github.com/ggml-org/whisper.cpp).
Son candidatos, no dependencias ni garantías de compatibilidad con nuestros pesos.

## Qué canal encaja hoy

Mi decisión por capacidad de producción, no por promesa de ingresos: empezar por
historias de fraude, empresas o mecanismos sorprendentes, como UltimateBet.
Podemos mostrar objetos, cifras y diagramas precisos con stock ilustrativo;
la investigación y la selección por escena siguen necesitando revisión.
Dos pilotos posibles para investigar: un cheque promocional aceptado por un banco,
y un robo facilitado por acceso interno. Son premisas pendientes de verificar;
no copies las cifras ni el guion de un competidor.

Terror/lore es viable **con un paquete de imágenes o gameplay del personaje**.
Para Slender Man, por ejemplo, un bosque genérico no explica quién creó al
personaje ni sus distintas adaptaciones. Guarda tus clips/capturas autorizados
bajo `assets/episodes/ID/`, descríbelos en `assets` del plan y el montaje los
utiliza por escena. Ese flujo ya admite vídeo e imágenes locales; Kitok no busca
ni descarga automáticamente material específico de personajes desde YouTube.

Historia con archivos/fotos es otra buena opción si hay fuentes y recursos
adecuados. Empezaría con un canal y tres pilotos coherentes antes de abrir varios.
Inglés y español requieren guion/narración propios; un doblaje o una traducción
no prueba que el vídeo tenga valor original. La automatización acelera render y
reparación; no garantiza monetización.
[Políticas de YouTube](https://support.google.com/youtube/answer/1311392?hl=es).
La disponibilidad de un recurso tampoco sustituye su licencia; el stock Pexels
se usa según sus [condiciones](https://www.pexels.com/license/).

No se han gastado créditos vidIQ, publicado vídeos ni creado nuevos canales.
Los estudios de demanda enlazados son snapshots aportados: hay que actualizar
muestras comparables antes de tomar decisiones comerciales importantes.

## Referencias conservadas

- [Catálogo aportado](kitok_catalogo_herramientas_director_autonomo_2026-10-15.md): candidatos y arquitectura propuesta; no inventario instalado.
- [Personajes y lore](kitok_estudio_canales_personajes_lore_2026-10-15.md): hipótesis y métricas públicas del estudio recibido, no auditoría propia actual.
- [Outliers aportados](2026-10-15-youtube-outliers.md): snapshot histórico y precauciones de comparación.
- [Piloto UltimateBet](../episodes/ultimatebet-superuser-production.md): brief recibido y evidencia observada del A/B.
- [Encargo archivado](../archive/requests/kitok_prompt_codex_work_editor_autonomo.md): referencia histórica, no contrato de operación.
