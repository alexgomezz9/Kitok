# Estado vigente de Kitok

Actualizado: **2026-10-23**. Rama **main**, integrada por fast-forward con
autorización expresa del operador desde base `1f879b6`;
checkpoints de esta entrega: audio `7673b34`, fuentes nativas `8f3e92b`,
subtítulos `bf3bc49`. Verificación local completa pasada. El SHA remoto y CI se consultan tras el push;
no se presenta una ejecución remota pendiente como CI aprobado.

Manual: [GUIA](GUIA.md), [stickman](docs/youtube-stickman-es.md),
[audio](docs/audio.md), [subtítulos](docs/captions.md).

## Capacidades verificadas

- Native/FFmpeg/ASS/Pillow monta con voz/alineación e imágenes existentes. No
  hay publicación automática. Fish nuevo requiere opción expresa; modelo
  `s2.1-pro-free` del episodio conservado sin nuevas solicitudes.
- CLI muestra etapas, planos actual/total y tiempo; `--quiet` oculta progreso.
- `--reuse-images` conserva imágenes pequeñas sin ampliación previa, valida
  formato/hashes/seguridad y avisa de resolución. Miniaturas y nuevas entregas
  individuales mantienen su contrato. Skill de lotes conserva tamaño nativo.
- `--subtitles` exporta otra versión: grupos de unas tres palabras EN MAYÚSCULAS,
  palabra activa amarilla y 110 %, con tiempos reales. `subtitles` funciona
  sobre un vídeo limpio aprobado. Conserva AAC y valida ambos archivos.
- Cámaras y transiciones siguen el plan reproducible: zoom/paneo son movimientos;
  las disoluciones son transiciones entre planos. No se eligen al azar.

## Verificación (23/10)

- `make verify`: **1125 Python**, **25 React**, TypeScript/Vite, higiene y whitespace
  correctos; `docs-check` y `studio-check` correctos.
- Pruebas reales FFmpeg de subtítulos, tamaño, color, reloj y audio copiado.
  Revisión independiente cerrada tras corregir grupos de palabras instantáneas.
- Mezcla real del episodio: **−16,01 LUFS / −1,78 dBTP**; margen AAC 0,8 dB
  antes de codificar y límite final −1,5 dBTP. Intento rechazado conservado.

## Michael Myers: vídeo solicitado en curso

Entrada: `content/longform/stickman_2_michael_myers/revisiones/montaje_720p_sin_ruidos`.
Dos ruidos confirmados por el operador retirados en copia: **14,88 s**;
**2165 palabras**, **125 imágenes**, **135 planos**, **726 s / 21780 frames**.
Originales e inputs conservados por hashes. La copia parte de `montaje_720p`
aportada por el operador. No usar la copia diagnóstica previa `sin_ruidos`.

El render completo está autorizado y ejecutándose con GPU local. Mientras
exista sólo el log no se presenta como MP4 terminado ni QA aprobado. Después
se exportará la variante subtitulada; escucha completa y aprobación audiovisual
siguen pendientes del operador. No se ha publicado ni desplegado.

Progreso del montaje: `tail -f /tmp/kitok-michael-gpu-progress.log`.
La continuación subtitulada usa `/tmp/kitok-michael-finalizacion.log`.

[Historia técnica](docs/archive/README.md). La investigación editorial fechada
se conserva como contexto; sus métricas no son datos actuales del canal.
