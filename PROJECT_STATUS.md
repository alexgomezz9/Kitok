# Estado vigente de Kitok

Actualizado: **2026-10-26**. Rama **main**: storyboard `7897f8b` y corrección
histórica `7d1747d` integrados por avance rápido desde `ef8370c`.
Perfil/flujo Trazo Maldito subidos: `ae4c05b`, SHA remoto confirmado.
CI [40381416777](https://github.com/alexgomezz9/Kitok/actions/runs/40381416777): **success**.

Manual: [GUIA](GUIA.md), [flujo editorial](docs/youtube-editorial.md),
[stickman](docs/youtube-stickman-es.md), [audio](docs/audio.md).

## Capacidades y verificación

- Storyboard guion → escenas/prompts con cobertura exacta, personajes, referencias
  y cámara explícita; compatible con lotes 3×3/reutilización. Prueba focal nueva
  (26/10): **32 tests** storyboard/lotes pasados. No genera medios al planificar.
- Native/FFmpeg/ASS/Pillow monta con voz/alineación e imágenes. Fish nuevo requiere
  opción expresa y voz configurada; no repetir resultados inciertos. No ASR automático.
- Progreso CLI por etapas/planos, stdout JSON, `--quiet`; QA final sólo al completar
  controles. Imágenes aportadas conservan tamaño nativo con avisos, sin inventar detalle.
- Subtítulos opcionales exportan otra versión, grupos de unas tres palabras,
  MAYÚSCULAS y palabra activa amarilla/110 %, con reloj real y audio conservado.
- Gate 26/10: **1154 Python**, **25 React**, TypeScript/Vite y studio-check
  pasados. Frontend tuvo timeouts intermitentes en pruebas distintas; pasada
  completa independiente 25/25 sin cambios. Causa del reloj aún en diagnóstico.
- `docs-check`, contexto offline y validación de skill correctos; revisión
  independiente acotada del flujo sin hallazgos. 3319 inputs protegidos conservan
  sus hashes tras el cambio de rama.

## Trazo Maldito

Canal `@trazomalditoes`, ID `UC9h_aIbnfQUo0ylPsPNnbrg`, independiente de Loose
Thread. OAuth oficial de lectura **comprobado el 26/10** mediante `sync` en
`local/youtube-trazo-maldito`: cero vídeos, Analytics diario/tráfico `no_data`,
Reporting disponible. No se infieren métricas ni permisos futuros de este snapshot.
Tokens y snapshot privados permanecen ignorados.

«Siguiente» delega al agente selección, investigación, guion y coordinación hasta
entrega local, usando skills existentes; Kitok/helpers hacen voz, tiempos, recortes
y montaje. Decisiones y QA se guardan por fase. No publica ni funciona con Codex
cerrado. Cuotas ImageGen/Fish no verificadas; gasto significativo exige consulta.

Encargo activo: producir el siguiente episodio completo tras cerrar main; comparar
personajes/referencias públicas y conservar evidencia de miniaturas, intervalos de
vídeo y audio realmente observados. Episodio local `content/longform/trazo_003_jason_voorhees`: guion1411palabras,
109escenas compiladas, ancla y primeros lotes generados; voz476,891s guardada.
109PNG finales revisados y validados; miniatura1280×720 revisada en móvil.
Reloj bloquea escena092 por salto401,711–410,993s con audio real. Muestra de
escucha solicitada al operador antes de cortar. No repetir voz. Entrega final
única subtitulada, base limpia sólo intermedio.

## Michael Myers: recursos anteriores conservados

Ruta: `content/longform/stickman_2_michael_myers/revisiones/montaje_720p_sin_ruidos`.
Los recibos existentes `qa.json` y `qa_subtitulado.json` indican **passed** para
vídeo limpio y subtitulado; leídos el 26/10. No se han vuelto a reproducir ni escuchar
completos en este encargo. Aprobación audiovisual humana no acreditada aquí.
No usar la copia diagnóstica anterior `sin_ruidos`. No se han repetido proveedores.

Corrección de mezcla `sample-clock-v4-decoder-tail`: rellena sólo la cola de
decodificador MP3 hasta la duración declarada. Regresión FFmpeg fallaba antes y
pasa ahora; **53 tests audio**, revisión independiente y docs-check correctos.
Muestra real33,5s: 9planos/1005frames, QA limpio y subtitulado **passed**,
−16,1LUFS/−2,29dBTP; contactos vistos, escucha completa no realizada. Ruta:
`content/longform/trazo_003_jason_voorhees/editorial/muestra_inicio/revisiones/decoder_tail/video_subtitulado.mp4`.

Siguiente: respuesta del operador sobre el tramo de audio; reparar sólo si se
confirma ruido sin palabras, en revisión nueva. Después montaje completo Kitok
y única entrega subtitulada. No volver a generar voz ni imágenes.
[Historia técnica](docs/archive/README.md).
