# Estado vigente de Kitok

Actualizado el **13/11/2026**. El checkout de producción local está en Ubuntu WSL.
La integración local usa `main`.
Consulta [GUIA.md](GUIA.md) y el diff vigente.

## Loose Thread

Usa `kitok-loose-thread` y el [método editorial](docs/research/loose-thread.md).
El agente investiga, escribe, descarga medios verificados y coloca los momentos
de archivo en el JSON parcial. Native valida las anclas, sincroniza con la
narración, anima fotos, conserva el encuadre de clips y monta stock en huecos.
Conserva fuentes, créditos y el reloj de cada inserto. Omite consultas de stock
para tramos cubiertos. Al cerrar un largo correcto retira planos y chunks
regenerables, y guarda voz y recibos. El fallo conserva el diagnóstico.
[Contrato de montaje](docs/editing.md).

La entrega de largos Native se genera desde el CLI en
`content/longform/<canal>/<episodio>/entrega`. Incluye MP4, miniatura,
subtítulos con reloj real y campos para subir manualmente desde Studio.
Los nuevos episodios se agrupan por canal. Las rutas históricas se conservan.
[Guía de entrega](GUIA.md#entrega-para-youtube-studio)

La muestra de UltimateBet dura 12,9 s y tiene 387 fotogramas. Combina dos
tramos de stock con una foto de Russ Hamilton animada a los 5,6 s según la
alineación Fish existente. El rótulo
identifica nombre y año. Se inspeccionaron fotogramas y se comprobaron la
decodificación y el nivel de audio. Queda la escucha editorial.

## YouTube

Loose Thread usa `local/youtube`. Se verificaron identidad, Data, 100 tramos
de retención y los siete permisos concedidos. `public-search` recuperó datos
públicos de una búsqueda real. `reporting-status` confirmó tres trabajos de
Reporting, de rendimiento, alcance y tráfico. Google aún no entregaba CSV.
Cuando aparezcan, descarga el informe de alcance y compara impresiones y CTR por
fuente antes de cruzarlos con retención. Ingresos sin filas, membresías 403.
[Comandos y perfiles](docs/integrations/youtube-readonly.md).

La consola OAuth sigue en Prueba, pendiente de completar marca. Trazo Maldito
usa `local/youtube-trazo-maldito`. El refresh devolvió HTTP 400 el 12/11 y
requiere un nuevo consentimiento del canal. Kitok verifica identidad antes de
reemplazar tokens.

## Trazo Maldito

La cola local marca Slenderman 012 como terminado técnicamente, con la entrega
en `content/longform/trazo_012_slenderman/revisiones/montaje_final`. Queda la
revisión audiovisual. Art 011 está en REVISAR por el requisito de preservar el
`LEEME.md` del operador. Consulta `local/stickman_jobs/ESTADO.md` y
`kitok-youtube` para continuar.

## Verificación

Usa `make test` y `make verify`. En terminal no interactiva, RTK puede resumir
un éxito de pytest comprobado. Los fallos y diagnósticos se leen completos.
El 12/11 pasaron `make verify` con 1.405 pruebas Python, 25 de frontend,
TypeScript/Vite e higiene. También pasaron el arranque del estudio y cinco
recorridos de Playwright.
