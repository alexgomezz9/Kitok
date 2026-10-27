# Carpetas y conservación de episodios

Cada proyecto editorial de vídeo usa el mismo esquema. Los borradores del estudio
siguen en `content/longform/studio/`; no son carpetas de episodios terminados.
Los shorts conservan su salida por ID en `outputs/ready/`.

```text
content/longform/EPISODIO/
  LEEME.md                 índice de entradas, entregas y archivo histórico
  guion_final.txt          texto fuente; Fish recibe su contenido con strip()
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

Las pruebas nuevas van en `local/pruebas/EPISODIO/`; las galerías globales útiles
siguen en `outputs/evaluation/` y `outputs/motion-gallery/`. No llenar episodios ni
`/tmp` de muestras permanentes. Guardar evidencia pequeña y borrar intermedios
cerrados. Conservar cachés de voz pagada, modelos ASR compartidos, stock reutilizable,
credenciales y trabajos activos. Una limpieza de episodios no desinstala MPT ni
otras dependencias y no borra otros proyectos.
