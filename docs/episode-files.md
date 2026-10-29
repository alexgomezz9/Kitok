# Carpetas y conservación de episodios

Cada proyecto editorial de vídeo usa el mismo esquema. Los borradores del estudio
siguen en `content/longform/studio/`; no son carpetas de episodios terminados.
Los shorts conservan su salida por ID en `outputs/ready/`.

```text
content/longform/EPISODIO/
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
  entrega/                 paquete revisable o vídeos históricos identificados
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
.venv/bin/python scripts/stickman_delivery.py organize content/longform/EPISODIO
.venv/bin/python scripts/stickman_delivery.py organize content/longform/EPISODIO --apply
# Sólo para revisiones cerradas, revisadas como históricas:
.venv/bin/python scripts/stickman_delivery.py organize content/longform/EPISODIO --archive-revisions
.venv/bin/python scripts/stickman_delivery.py organize content/longform/EPISODIO --archive-revisions --apply
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

Una carpeta `entrega/` vacía admite el paquete de seis archivos de `bundle`.
Si contiene vídeos históricos, se preserva; una entrega nueva requiere una revisión
nueva. Un nombre `video_final` o un ZIP no equivale a aprobación técnica/editorial.

Encargo del operador el 28/10: los remakes nuevos usan otra carpeta de episodio y
conservan ambos vídeos, normal y subtitulado. No retirar el máster normal al
exportar el bundle subtitulado. Las carpetas anteriores se mantienen para borrado
manual del operador; el inventario preparado antes de esta aclaración no se aplicó.
En la auditoría posterior el operador autoriza limpiar auxiliares resueltos al
terminar. `organize` se aplicó a Michael después de comprobar la entrega: retiró
765 archivos de trabajo, manteniendo 122 rutas fuente/finales con el mismo SHA.
Esto conserva las carpetas anteriores y ambos MP4; no elimina los PNG definitivos.

Las pruebas nuevas van en `local/pruebas/EPISODIO/`; las galerías globales útiles
siguen en `outputs/evaluation/` y `outputs/motion-gallery/`. No llenar episodios ni
`/tmp` de muestras permanentes. Guardar evidencia pequeña y borrar intermedios
cerrados. Conservar cachés de voz pagada, modelos ASR compartidos, stock reutilizable,
credenciales y trabajos activos. Una limpieza de episodios no desinstala MPT ni
otras dependencias y no borra otros proyectos.

## Cierre de trabajos de la cola stickman

La cola descrita en [GUIA](../GUIA.md#produccion-repetida-de-trazo-maldito) usa
`complete`: verifica ambos MP4/QA/recibos, reúne la entrega y aplica `organize`
sin archivar revisiones. `.stickman/completion-cleanup.json` persiste la lista
previa, intentos e integridad posterior. Si falla, no purgar carpetas manualmente:
leer el log del trabajo y reanudar conservando fuentes y cachés útiles.
`local/stickman_jobs/ESTADO.md` resume todos los trabajos nuevos; no modifica ni
importa automáticamente episodios históricos. No existe una carpeta cuyo borrado
completo sustituya esta limpieza por lista de archivos comprobados.
