# Estado vigente de Kitok

Actualizado: 2026-10-18. Rama **feat/documentary-director**; main intacto.
Manual de operación: [GUIA.md](GUIA.md). Montaje: [docs/editing.md](docs/editing.md).

## Disponible

- Nuevos shorts locales/Pexels: Fish + FFmpeg; Pexels cuando corresponde.
- Nuevos largos: native predeterminado en CLI y estudio; la interfaz lo
  identifica como experimental.
  MPT sólo para diagnóstico y recuperación explícita de tareas históricas.
  Álvaro/Edge queda como dato histórico; las voces nuevas son Fish.
- Montaje: comparación A/B, descarga y render de un plan local por escenas.
  Reutiliza audio/recursos; cachea planos; gráficos de identidad, cifras y acceso
  a información. No prepara el plan automáticamente ni ofrece editor de timeline.
- Fish: caché compartida entre modos y bloqueo de peticiones ambiguas; no repetir
  una síntesis incierta para reparar efectos. Datos, cachés y vídeos preservados.
- Generación y publicación separadas. Buffer conserva revisión/confirmación.
  Sin publicación de vídeos ni merge a main en este incremento.

## Evidencia actual

- UltimateBet: A/B **76 s, 1920×1080, 30 fps**, local en
  outputs/evaluation/ultimatebet_ab/{A_current,B_improved}.mp4.
  Original de 652,6 s conservado. B es la versión 3 revisada visualmente; mismo
  audio decodificado que A, decode completo correcto, sin negros detectados,
  -16,13 LUFS y -1,8 dBTP. Sin nueva voz ni APIs durante la reedición.
- Render NVENC: primera versión 65,9 s; corrección final 19,6 s,
  1 plano renderizado y 16 reutilizados. Las medidas no incluyen todo el QA.
- 55 pruebas editoriales/graphics pasan; relectura adversarial cerró enlaces,
  promoción interrumpida, muestreo a 80 puntos y revisión de caché del navegador.
- 13 pruebas React, build TypeScript/Vite y **5 E2E Chromium** pasan. El E2E de
  Montaje hace render FFmpeg real sobre medios temporales; Fish/Buffer no se usan.
- Gate integrado: **487 Python, 13 React, build y 5 E2E** pasan con datos
  temporales y red externa bloqueada en pytest. make studio-check pasa.
- Guard CLI: una tarea MPT pendiente bloquea native incluso con --start-over,
  bajo lock y antes de crear proveedores. Relectura independiente: 17 pruebas pasan.
- Código integrado e5ac321 subido y
  [CI correcta](https://github.com/alexgomezz9/Kitok/actions/runs/38807115646)
  comprobada. Este checkpoint añade documentación revisada y conserva la investigación recibida.

## Límites y siguiente paso

No hay director autónomo, catálogo multicanal operativo ni nuevos episodios
completos mejorados. YouTube: CLI oficial sólo lectura implementado y revisado,
38 pruebas aisladas pasan; OAuth real pendiente. No importa todavía CTR/CSV.
VidIQ reconoce LooseThread mediante consulta gratuita; exige verificación reciente. Revisión visual por muestras; audición
subjetiva continua no realizada. No se ha probado cada estilo con una nueva
llamada real Fish/Pexels; las pruebas de proveedores son aisladas.

[PR de borrador preparada](https://github.com/alexgomezz9/Kitok/pull/1), sin merge.
Trabajo en curso: C de UltimateBet con fotografía específica licenciada y
composición animada/3D; los prototipos no son el piloto terminado.
Siguiente mejora editorial:
recursos más específicos por episodio y ampliar el plan al resto de UltimateBet
reutilizando audio; no presentar ese trabajo como ya terminado.
Mantener esta página breve; historial de diseño en docs/archive/.
Hardware: RTX 3050 Laptop 4 GB / RAM 8 GB; render secuencial FFmpeg/Pillow/ASS.
APIs existentes autorizadas cuando hagan falta; evitar consumo duplicado.
