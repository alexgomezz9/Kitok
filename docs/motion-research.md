# Selección del motor documental

Actualizado el **21 de octubre de 2026**. Kitok conserva FFmpeg como ensamblador,
ASS/libass para tipografía y Pillow para preparar imágenes. Remotion se ha probado
con un render real; no se añade como dependencia de producción porque esta prueba
no ha demostrado una ventaja que compense mantener otro runtime.

## Comparación ejecutada

Remotion **4.0.537**, instalado únicamente en /tmp/kitok-remotion-proof, frente al
renderer editorial actual. El complemento disponible aporta skills de creación,
markup, render y documentación; no había proyecto Remotion en Kitok ni MCP suyo.
Se abrió Studio y se comprobó la composición en Chromium local. No se modificó
el servidor del operador ni se instalaron proveedores nuevos en Kitok.

Se usó la misma foto aportada, nombre, rótulo, detalle y extracto de mezcla existente:
retrato horizontal 1280×720, 30 FPS, 4 s/120 fotogramas, acercamiento discreto y
fundidos .6/.8 s. Las propuestas de composición difieren (CSS frente a ASS).
FFmpeg remuxeó el mismo AAC final en ambas: audio decodificado idéntico y decode
completo correctos. No se volvió a pedir Fish ni se normalizó la mezcla.

| Medida local | Native actual | Remotion |
| --- | --- | --- |
| Tiempo total de proceso | 11,53 s | 31,50 s |
| Máximo RSS observado por /usr/bin/time | 279.664 KB | 654.240 KB |
| Entrega | 120 frames H.264 4:2:0 + AAC | 120 frames H.264 4:2:0 + el mismo AAC |
| Cadena adicional | Ninguna | Node, React, bundler y Chromium |

Es un único retrato, no un benchmark general ni la suma simultánea de memoria de
todos los procesos. Los logs originales, fuentes y MP4 están en
outputs/evaluation/editor-final-20261021/. Se conservan la primera propuesta
Native y una revisión tipográfica: el nombre más grande, detalle y degradado
se trasladaron al componente ASS reutilizable. Esa ganancia no requiere otro
motor. La composición CSS sigue como [ejemplo opcional](../examples/remotion/README.md),
sin ejecutar npm al instalar/arrancar Kitok.

La observación de contactos muestra encuadre y jerarquía; las verificaciones de
reproducción y movimiento de la entrega se registran en PROJECT_STATUS.md.
No se afirma escucha humana ni aceptación del operador a partir de estas medidas.

## Referencias examinadas

| Referencia primaria | Evidencia y decisión |
| --- | --- |
| [Remotion renderMedia](https://www.remotion.dev/docs/renderer/render-media) y [CLI render](https://www.remotion.dev/docs/cli/render) | Documentación actual, paquete 4.0.537 y render local. Licencia [propia](https://www.remotion.dev/license), no MIT. Viable para escenas multicapa futuras; no necesario para la ruta de fotos actual. |
| [snapcn text](https://snapcn.dev/docs/text) | Documentación de títulos/entrada/salida, componentes para un proyecto Remotion existente. No se copió código ni se instaló su registro. No se atribuye una licencia global a todos sus componentes gratuitos/Pro. |
| [Shotpack animations](https://www.getshotpack.com/animations) | Catálogo de referencias de tipografía/cámara/transiciones, con material gratuito y de pago. No se copiaron plantillas ni se adquirió un pack. |
| [remotion-video-templates](https://github.com/AleBrito124356/remotion-video-templates) | Clon temporal, SHA 90149464d51a43fcb90e15491bf0d681c1b0fa49; LICENSE MIT y lectura de KineticText.tsx/Root.tsx: cálculo único de duración, secuencias y entrada por palabra. No se incorporó código externo. |
| [Motion Canvas](https://github.com/motion-canvas/motion-canvas) y [quickstart](https://motion-canvas.io/docs/quickstart/) | Núcleo MIT, generators/signals, `yield* all` y exportación imagen/FFmpeg. No se instaló: otro motor no resuelve una carencia comprobada en estos planos. No hay benchmark local suyo. |
| [procedural-film](https://github.com/kuhnhomeuk-cell/procedural-film) | Clon temporal, SHA f59413999ae24f6e1f9165b73a0eaa97a0b1c407, LICENSE MIT; lectura de scene-anatomy: continuidad global, geometría/semillas reproducibles y gates por frame. Está orientado a cortos dibujados/canvas; no sustituye voz ni stock del documental. Sin código copiado. |

La investigación más amplia anterior y sus límites permanecen en
[el índice de archivo](archive/README.md). Sólo esta página documenta la decisión
vigente. No se instalan listas de motores ni se añade un LLM al render.
