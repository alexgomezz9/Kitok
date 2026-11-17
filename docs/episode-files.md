# Carpetas y conservación de episodios

Los episodios se numeran por canal en `content/longform/`. Reserva el siguiente
número con el CLI. Repetir el mismo nombre de tema recupera la misma carpeta.
Los borradores internos quedan en `state/longform/drafts/` y los shorts en
`outputs/ready/`.

```bash
.venv/bin/python longform.py new loose_thread mi_tema
.venv/bin/python -m kitok.youtube_stickman_es init mi_tema --channel trazo_maldito
```

El índice local `state/longform-episode-moves.json` mantiene las referencias de
recibos anteriores al traslado. Conserva el archivo junto al resto del estado.

```text
content/longform/CANAL/NNN_EPISODIO/
  LEEME.md                 índice de entradas, entregas y archivo histórico
  guion_final.txt          texto fuente; Fish nuevo recibe espacios únicos y [] intactos
  titulo.txt
  configuracion.json       esquema stickman o definición Native, según el flujo
  voz.mp3                  Fish original, cuando existe; nunca editarlo in situ
  voz.srt / voz.alignment.json
  imagenes/                PNG definitivos consumidos por el montaje
  referencias/             anclas, fuentes y licencias
  planificacion_visual/    plan, prompts y manifiestos de los lotes
  miniaturas/
  editorial/               investigación y estado actual
  entrega/                 paquete listo para YouTube Studio
  .stickman/               recibos y cachés internos; no son entradas del operador
```

Sólo existen archivos de las fases realmente ejecutadas. No crear voz, guion ni
un falso final para rellenar la estructura. `guion_lectura_limpia.txt` es un derivado
para offsets del storyboard, no la entrada enviada a Fish. El texto hablado y los
marcadores de interpretación se tratan según [el contrato de voz](fish-voice.md).

El agente investiga, escribe, decide escenas/prompts y genera/revisa imágenes.
Kitok valida, recorta, alinea, mezcla, subtitula y renderiza mediante sus comandos.
Una recuperación manual excepcional debe registrarse como tal y corregirse en el
código reutilizable cuando sea un defecto; no repetir montajes artesanales por vídeo.

## Limpieza explícita y comprobable

```bash
.venv/bin/python scripts/stickman_delivery.py organize content/longform/CANAL/NNN_EPISODIO
.venv/bin/python scripts/stickman_delivery.py organize content/longform/CANAL/NNN_EPISODIO --apply
# Sólo para revisiones cerradas, revisadas como históricas:
.venv/bin/python scripts/stickman_delivery.py organize content/longform/CANAL/NNN_EPISODIO --archive-revisions
.venv/bin/python scripts/stickman_delivery.py organize content/longform/CANAL/NNN_EPISODIO --archive-revisions --apply
```

Sin `--apply` lista los candidatos. `--report local/cleanup/ID/informe.json` guarda
el detalle fuera del episodio y muestra sólo recuentos. No contacta proveedores ni
codifica vídeo. `init` crea la estructura y el índice; el montaje actualiza el índice.
La limpieza y el archivo no se ejecutan como efecto oculto de guardar o renderizar.

Se retiran clips, placas de render y fotogramas de QA regenerables. Las láminas,
contactos y crops sólo se retiran cuando su propio lote está resuelto y los PNG
finales conservan hashes y decodificación válidos. Una reparación pendiente no se
descarta porque exista otra imagen con el mismo ID. Un recorte obsoleto necesita
una sustitución aceptada y declarada mediante `cleanup_superseded_by` con el ID
del lote que lo reemplazó. Se conservan prompts, cajas, revisiones y hashes de las
láminas retiradas en los manifiestos y `.stickman/workspace-history.json`.
Los recursos referenciados por planes/configuración se conservan.
En proyectos Native también se toma el bloqueo global `longform-ID`; no basta
con comprobar el bloqueo de episodio usado por stickman.

`--archive-revisions` saca las revisiones cerradas del árbol diario: conserva los
vídeos únicos en `entrega/`, fuentes únicas en ZIP verificado y duplicados como
referencias a archivos canónicos con SHA256. Destino:
`local/archivo_episodios/EPISODIO/REVISION.zip`. Bloquea una revisión utilizada por
las entradas actuales. Cada ZIP contiene `restauracion.json`: extraer sus miembros
en la ruta `revision`, copiar cada archivo `retained` desde la ruta registrada a
su ruta original y comprobar todos los hashes antes de reanudar. Restaurar rutas
no recupera cachés borradas; éstas requieren otro render. No reabrir ni sintetizar
automáticamente una revisión archivada.

## Una entrega canónica para subir

Native prepara el MP4, miniatura, SRT y textos de publicación mediante
[`longform.py --deliver`](../GUIA.md#entrega-para-youtube-studio). Stickman usa
`bundle`, que exige ambos QA y recibos coincidentes. Su paquete incluye:

- `video_final.mp4` y `video_subtitulado.mp4`.
- `voz.srt` del audio efectivo y `miniatura.png`.
- `titulo.txt`, `descripcion.txt`, `etiquetas.txt` y `ajustes_youtube.txt`.

El agente de Trazo Maldito prepara `editorial/publicacion_youtube.json`
(`title`, `description`, `tags`, `settings` opcional). Ese texto prevalece sobre
la descripción técnica y conserva capítulos reales y atribuciones obligatorias.
No altera la voz, guion o recibos del montaje. Las decisiones de Studio que
requieren ver el contenido se dejan para revisión del operador.

El informe de hashes está en `.stickman/delivery.json`. El bundle publica mediante
links temporales y retira sólo nombres de vídeo con el mismo SHA que los dos finales
canónicos; no vuelve a codificar. Al finalizar hay un único nombre por MP4 final,
dentro de `entrega/`. Los recibos históricos mantienen sus hashes y Kitok resuelve
las rutas canónicas al reanudar. Exportar cualquier edición a una versión nueva.

Para migrar una entrega histórica, primero inspecciona:

```bash
.venv/bin/python scripts/stickman_delivery.py normalize content/longform/CANAL/NNN_EPISODIO --report local/cleanup/ID/antes.json
.venv/bin/python scripts/stickman_delivery.py normalize content/longform/CANAL/NNN_EPISODIO --apply --report local/cleanup/ID/despues.json
# Para una revisión activa, entrega visible en la carpeta padre:
.venv/bin/python scripts/stickman_delivery.py normalize content/longform/CANAL/NNN_EPISODIO/revisiones/ACTIVA --destination-episode content/longform/CANAL/NNN_EPISODIO
```

`normalize` valida los hashes del paquete anterior y bloquea textos editados por el
operador o un vídeo anterior distinto. Guarda el plan antes de borrar y conserva
el historial de textos/recibos fuera de `entrega/`. El informe distingue duplicados
SHA idénticos y vídeos distintos preservados. No borra estos últimos, ni fuentes,
PNG o audios pagados. Una revisión sólo puede entregar a sí misma o a su padre;
los bloqueos de producción y de revisiones se respetan. Esta migración no publica.
El encargo del 04/11 sustituye la entrega de seis archivos y la conservación de
nombres redundantes de MP4: ambos vídeos seleccionados viven en la entrega visible.

Las pruebas nuevas van en `local/pruebas/EPISODIO/`; las galerías globales útiles
siguen en `outputs/evaluation/` y `outputs/motion-gallery/`. No llenar episodios ni
`/tmp` de muestras permanentes. Guardar evidencia pequeña y borrar intermedios
cerrados. Conservar cachés de voz pagada, modelos ASR compartidos, stock reutilizable,
credenciales y trabajos activos. Una limpieza de episodios no desinstala MPT ni
otras dependencias y no borra otros proyectos.

La limpieza autorizada del 29/10 compactó las pruebas cerradas de Freddy004,
Michael005, Chucky006 y Pennywise007 en
`local/archivo_episodios/EPISODIO/pruebas_cerradas_20261029.zip`. Estos ZIP usan
`restauracion.json` con `original` como destino, `archived` como miembros/SHA y
`retained` como rutas canónicas/SHA: extraer, copiar las referencias y comprobar
los hashes antes de reutilizar. Cada miembro y fuente conservada se comprobó
antes de retirar las copias de pruebas. El audio Fish del reintento de Pennywise
permanece en su ruta original; también se conservan los diagnósticos de Jason en pausa.
El WAV reparado de Jason está en su episodio, `voz_reparada.wav`; se retiró sólo
su enlace redundante de `local/pruebas/`. Las herramientas/modelos ASR compartidos
siguen en `local/`, aunque un episodio ya haya terminado.

## Cierre de trabajos de la cola stickman

La cola descrita en [GUIA](../GUIA.md#produccion-repetida-de-trazo-maldito) usa
`complete`: verifica ambos MP4/QA/recibos, reúne la entrega y aplica `organize`
sin archivar revisiones. `.stickman/completion-cleanup.json` persiste la lista
previa, intentos e integridad posterior. Si falla, no purgar carpetas manualmente:
leer el log del trabajo y reanudar conservando fuentes y cachés útiles.
`local/stickman_jobs/ESTADO.md` resume todos los trabajos nuevos; no modifica ni
importa automáticamente episodios históricos. No existe una carpeta cuyo borrado
completo sustituya esta limpieza por lista de archivos comprobados.
