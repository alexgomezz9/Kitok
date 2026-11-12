# Estado vigente de Kitok

Actualizado el **12/11/2026** en `feat/loose-thread-documentary`, sobre
`c9180e6`. Operación en [GUIA.md](GUIA.md). El checkout de producción local
está en `~/projects/Kitok` (Ubuntu WSL).

## Loose Thread

El largo Native admite fotos, documentos en imagen y MP4 en un JSON parcial
anclado al guion. El agente investiga, comprueba procedencia y licencia, y
prepara los recursos. Kitok valida entradas, aplica movimiento suave, conserva
el encuadre de clips y monta stock de relleno. Omite búsquedas y descargas
de los tramos cubiertos por completo. Se conservan las fuentes, el reloj de
cada cue y los créditos. [Contrato de montaje](docs/editing.md).

Siguiente producción con `kitok-loose-thread`. Preparar un borrador en inglés
con el narrador original, imágenes y clips comprobados, y el JSON parcial. Abrir
Vídeo largo y comprobar el borrador. Reutilizar narración si coincide guion, voz
y velocidad. Revisar la primera muestra antes de ampliar.

Prueba real local de UltimateBet: 12,9 s, 387 fotogramas, dos tramos de stock,
una foto de archivo animada en la frase a los 5,6 s, reloj Fish existente.
Se inspeccionaron fotogramas y se decodificó todo el MP4. Escucha editorial
pendiente. Se reutilizaron voz y recursos locales.

## YouTube

Loose Thread `local/youtube` se verificó el 12/11 por Data y Analytics,
incluida retención. Google concedió el perfil de siete permisos. Se crearon y
releyeron tres trabajos de Reporting (rendimiento, alcance y tráfico). La
primera consulta de archivos aún devolvía listas vacías. Ingresos sin filas,
membresías 403. Al reconectar, Kitok verifica la identidad antes de sustituir
tokens. Trazo Maldito `local/youtube-trazo-maldito` obtuvo los permisos el
05/11 y su refresh devolvió HTTP 400 el 12/11. Requiere nuevo consentimiento
propio. La consola OAuth sigue en Prueba, pendiente de completar marca.
[Comandos y perfiles](docs/integrations/youtube-readonly.md).

## Trazo Maldito

La cola local marca Slenderman 012 como terminado técnicamente, con la
entrega en `content/longform/trazo_012_slenderman/revisiones/montaje_final`.
Queda la revisión audiovisual. Art 011 está en REVISAR por el requisito de
preservar el `LEEME.md` del operador. Consultar
`local/stickman_jobs/ESTADO.md` y usar la skill `kitok-youtube` para continuar.

## Verificación

`make verify` completo el 12/11 con Node de `.tools/node/bin`: 1.400 pruebas
Python, 25 de frontend, TypeScript/Vite e higiene. `make studio-check` y los
cinco recorridos aislados de Playwright pasaron. El cierre editorial es local.
