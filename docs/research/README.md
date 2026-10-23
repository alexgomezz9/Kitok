# Herramientas y formatos: decisiones actuales

El inventario implementado está en [capacidades](../capabilities.md), y su evidencia
fechada en [PROJECT_STATUS.md](../../PROJECT_STATUS.md). Esta página explica decisiones,
no promete ingresos ni convierte una biblioteca evaluada en una dependencia instalada.

## Componentes elegidos

| Herramienta | Uso real en Kitok | Límite |
| --- | --- | --- |
| FFmpeg/ffprobe | Montaje, audio, normalización, NVENC/libx264 y QA | No juzgan hechos ni narrativa |
| Pillow/ASS | Gráficos, fotografía con movimiento y rótulos | El editor aporta datos y textos |
| Three.js/Chromium local | Mesa y acciones 3D del piloto C | Reparto UltimateBet fijado; WebGL software puede ser lento |
| Fish | Narración y alineación/caché aprovechables | Cambiar guion/voz puede consumir saldo; resultados inciertos no se repiten solos |
| Pexels | Stock nativo y registro de clips cacheados | Ilustración, no evidencia histórica ni identidad |
| Commons | Imágenes raster con metadatos/licencia admitida | Buscar candidatos no verifica el sujeto ni el contexto |
| Biblioteca Incompetech auditada | Cuatro pistas con hashes/créditos, selector y mezcla | Ampliar repertorio requiere revisar contrato y fuentes |
| OAuth/Data/Analytics/Reporting oficiales | CLI YouTube de lectura preparado | Consentimiento real pendiente; sin CTR/CSV o dashboard |

La selección prioriza el equipo de 4 GB VRAM/8 GB RAM y la reutilización de audio.
No instalamos modelos grandes ni decenas de repositorios. Motion Canvas, Remotion,
PDFium, rembg y whisper.cpp siguen siendo candidatos para necesidades concretas;
no hay benchmark comparativo que acredite una superioridad general.

Los tres MCP YouTube y el repo Jakes se evaluaron como referencias. La decisión y
sus límites están en [la integración actual](../integrations/youtube-readonly.md).
No se han instalado globalmente ni concedido permisos de escritura a esos paquetes.

## Formatos viables

- Fraudes, empresas y mecanismos: narración, archivos con derechos y explicaciones
  visuales. El resultado depende de recursos específicos y una investigación seria.
- Historia con imágenes documentadas: viable si se resuelven identidad, contexto,
  derechos y legibilidad de cada documento.
- Terror/lore: requiere un paquete propio/autorizado de personajes, capturas o
  gameplay; un bosque genérico no sustituye ese material.

El render admite medios locales; Kitok no busca ni descarga automáticamente clips
de personajes desde YouTube. Idioma, guion y revisión se preparan por versión.
No existe un recomendador autónomo de temas ni pruebas de monetización/retención.

Los estudios y métricas recibidos en octubre se preservan únicamente en el
[archivo histórico](../archive/README.md). Sus números son snapshots y no deben
usarse como métricas actuales ni instrucciones del producto.

## Producción stickman: revisión actual

[Decisiones corregidas del 22/10/2026](2026-10-22-produccion/README.md): acceso real a WSL, evidencia del episodio, una imagen por escena y tres tareas propuestas. Plan pendiente de validación; no acredita la reparación concurrente como terminada.
