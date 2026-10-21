# Experimento opcional Remotion

Composición original de comparación; **no es una dependencia ni un renderer
activado de Kitok**. El motor de producción sigue siendo Native + FFmpeg/ASS/Pillow.
[Resultado medido y decisión](../../docs/motion-research.md).

Para repetir en una carpeta temporal, copia estos archivos, crea public/ y coloca
una foto revisada como public/photo.jpg. No hay medios ni voz incluidos.

```bash
npm install
npx remotion studio index.ts --no-open
npx remotion render index.ts Portrait portrait-silent.mp4 --concurrency=1 --codec=h264 --pixel-format=yuv420p
ffmpeg -i portrait-silent.mp4 -i approved-four-second-mix.m4a -map 0:v:0 -map 1:a:0 -c copy portrait-with-audio.mp4
```

FFmpeg añade el mismo AAC final a las dos variantes. La composición no sintetiza,
mezcla ni descarga audio. Para el benchmark de Kitok se usaron una fotografía del
operador, nombre/rótulos aportados y exactamente ese mismo fragmento de audio.
Los archivos concretos y hashes son privados, bajo outputs/evaluation/.

Comprueba la [licencia propia de Remotion](https://www.remotion.dev/license) antes
de otro uso; no es MIT. No se han comprado servicios ni copiado plantillas externas.
Los tiempos de un único retrato de 4 s no acreditan superioridad general de un motor.
Remotion Studio usa un servidor adicional; para la prueba local se restringió
su escucha a 127.0.0.1 mediante un preload Node temporal, sin cambiar Kitok.
