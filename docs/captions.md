# Subtítulos de palabra activa

El CLI stickman puede entregar una segunda versión con subtítulos incrustados.
La versión limpia se conserva. Sólo usa alineación real ya validada; no genera
voz ni estima tiempos por longitud del texto.

```bash
.venv/bin/python -m kitok.youtube_stickman_es produce content/longform/mi_episodio --reuse-images --subtitles
# Si ya existe el vídeo limpio y su QA:
.venv/bin/python -m kitok.youtube_stickman_es subtitles content/longform/mi_episodio
```

La salida es `video_subtitulado.mp4`; `video_final.mp4` conserva su imagen limpia.
El ASS y el recibo fijan texto, tiempos y hashes. Las frases muestran unas tres
palabras blancas EN MAYÚSCULAS con contorno oscuro; sólo la palabra que está sonando cambia
a amarillo y crece un 10 %. El tamaño vuelve al normal al terminar la palabra;
no hay rebotes ni transiciones adicionales. El texto procede del guion
aprobado y conserva puntuación. Escucha y revisión visual siguen siendo humanas.

## Qué apoya la evidencia

[YouTube explica](https://support.google.com/youtube/answer/2734796) que los
subtítulos amplían la accesibilidad. Esto no prueba un aumento concreto de
retención ni que tres palabras sea un óptimo universal.

Un [estudio de seguimiento ocular sobre formato y carga cognitiva](https://www.tandfonline.com/doi/abs/10.1080/1475939X.2024.2433259)
encuentra diferencias de procesamiento entre formatos. Otro estudio de
[resaltado textual y aprendizaje](https://www.cambridge.org/core/journals/applied-psycholinguistics/article/investigating-the-effects-of-prolonged-exposure-to-textual-enhancement-on-attention-and-learning-a-preposttest-measures-eyetracking-study/AC5C9DE823DEC3613B31C260393D32A8)
observa mayor atención a palabras resaltadas, en un contexto de aprendizaje
lingüístico. Atención, aprendizaje y retención en YouTube son medidas distintas.

La decisión editorial aquí es una opción legible y discreta para probar, no
una promesa de crecimiento. En un vídeo horizontal de doce minutos conviene
comparar con la versión limpia y consultar después la retención real del canal.
