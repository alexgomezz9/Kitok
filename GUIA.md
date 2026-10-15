# Kitok: guía de uso

## Abrir el estudio

Desde la carpeta del proyecto, ejecuta:

```bash
make studio
```

Abre http://127.0.0.1:8000 en el navegador. Una sola terminal sirve el frontend y el backend. Déjala abierta mientras se genera un vídeo. El cierre puede esperar al trabajo en curso; no hay un botón de cancelación.

Los vídeos se guardan localmente: shorts en outputs/ready y largos en outputs/longform. No necesitas Google Drive ni una carpeta sincronizada; puedes descargarlos desde el navegador. READY_DIR está configurado para la carpeta local. Las rutas y los archivos de vídeos anteriores se conservan. Si configuras expresamente otro destino y no está disponible, Kitok avisa y usa la carpeta local durante esa sesión.

Si es la primera instalación, necesitas Python 3.11+, Node 22.12+ o 24, npm y FFmpeg (incluye ffprobe). Después:

```bash
make studio-setup
make studio-check
make studio
```

studio-check comprueba las herramientas instaladas, sin generar vídeos ni conectar con proveedores. Si faltan claves, la comprobación de cada vídeo te lo indicará. Las claves van en .env, nunca en el guion ni en el navegador.

## Los cuatro pasos

1. Escribe el título y el guion. Kitok no inventa el texto por ti.
2. Pulsa «Comprobar sin generar». Valida el contenido y muestra requisitos locales. No hace llamadas a Fish, MPT, Pexels, Cloudinary ni Buffer.
3. Guarda el borrador. Después pulsa «Generar». Esta segunda acción sí usa los proveedores necesarios y puede consumir saldo.
4. Reproduce el resultado. Descárgalo o, para shorts, elige una fecha y revisa el envío a Buffer.

La comprobación local no demuestra que las claves sean válidas, que haya saldo ni que un servicio esté conectado. Tampoco puede saber la duración exacta antes de sintetizar la voz.

## Crear un short desde el frontend

En «Crear short» elige uno de los estilos básicos:

- Rick: una narración con voz Fish, personajes/subtítulos del formato existente y un fondo de assets/backgrounds/random/. No necesita MPT.
- Rick y Morty: diálogo por turnos, voces Fish y gameplay local. Los PNG transparentes van en assets/characters/rick/ y assets/characters/morty/. No necesita MPT con fondo local.
- Narración con Pexels: guion y palabras para buscar imágenes. Todavía necesita la API de MoneyPrinterTurbo encendida. Álvaro es la voz inicial.

1. Introduce el título y el guion; en diálogo, escribe lo que dice cada personaje en su bloque.
2. Si usas Pexels, escribe búsquedas concretas separadas por comas; por ejemplo: brain, science, laboratory.
3. Comprueba sin generar y corrige los requisitos que aparezcan pendientes.
4. Guarda el borrador. En la ficha pulsa «Generar vídeo» y espera a que aparezca listo.
5. Reproduce y descarga el MP4. La validación del modo corto exige entre 5 y 60 segundos con los valores predeterminados; amplía o acorta el texto si hace falta.

El texto para redes se toma del título si no escribes otro en opciones avanzadas. El fondo se elige automáticamente. Las semillas, personajes, voces y ajustes detallados no son necesarios para empezar.

## Enviar un short a Buffer

Generar, dar fecha y enviar son acciones diferentes. Un MP4 listo o una fecha local no significan que Buffer tenga una publicación.

1. En «Mis shorts», abre un vídeo listo y pulsa «Elegir fecha local».
2. Elige fecha, hora y plataformas. La pantalla indica la zona horaria configurada; por defecto Europe/Madrid.
3. Pulsa «Previsualizar envío (dry-run)». Revisa las plataformas, las subidas, los avisos y el número de publicaciones. Este paso usa información local/cache y no envía nada.
4. Pulsa «Confirmar envío a Buffer». Kitok comprueba el estado remoto, puede subir el vídeo a Cloudinary y programa las publicaciones permitidas por la revisión.
5. Revisa el estado por plataforma. «Calendario → Actualizar Buffer» consulta los posts guardados. Las reprogramaciones de posts ya enviados se gestionan en Buffer.

Configura una vez en .env: PUBLISH_ENABLED=true, BUFFER_API_KEY, los canales de destino y CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET. Usa .env.example como referencia y reinicia el backend si cambias .env.

Si la protección de uso de Cloudinary pide un informe reciente, puedes actualizarlo con este comando (hace una consulta remota, sin subir vídeos):

```bash
.venv/bin/python main.py --cloudinary-usage --refresh
```

Si pide un presupuesto reciente de Buffer:

```bash
.venv/bin/python main.py --buffer-usage --refresh
```

Los errores de fecha, cuota o publicación incierta se revisan antes de repetir el envío. No borres IDs ni estado para forzar otra publicación. Las opciones avanzadas conservan las protecciones existentes contra duplicados.

## Crear un vídeo largo desde el frontend

1. Abre «Vídeo largo». Pega el título, todo el guion y las búsquedas para Pexels separadas por comas. La última frase debe terminar con puntuación, normalmente un punto.
2. Elige narrador. Loose Thread es el narrador original en inglés; también aparecen las voces Fish del catálogo. El texto se lee tal como está escrito.
3. Deja la música desmarcada para empezar. Si la activas, tiene que existir assets/music/loose_thread/level.mp3.
4. Comprueba sin generar y guarda el borrador. Se crean automáticamente un .txt y un .json en content/longform/studio/.
5. Selecciona el borrador y pulsa «Generar vídeo largo». Espera a «Terminado», reproduce y descarga el MP4.

La interfaz selecciona el motor nativo experimental de forma explícita. Usa FISH_API_KEY y PEXELS_API_KEY de Kitok. No necesita MPT. En opciones avanzadas puedes seleccionar MPT para un nuevo borrador; en ese caso necesita su API encendida y sus credenciales/configuración propias.

La salida es horizontal 16:9, 1920×1080, sin subtítulos, en outputs/longform/. La duración depende del guion y de la voz; no se fija con un selector de minutos. Se admiten hasta 24.000 caracteres y 20 búsquedas. Las búsquedas son globales, sin sincronización semántica por frase.

Los vídeos largos no entran en el calendario ni en el publicador Buffer de shorts. Descárgalos y súbelos a YouTube Studio. Los largos antiguos creados sólo por CLI siguen en outputs/longform/; la nueva lista muestra los borradores creados en este estudio.

Si falla o se interrumpe, no se vuelve a generar automáticamente. Revisa logs/kitok-AAAAMMDD.log y los archivos antes de crear otra copia. Repetir una generación puede volver a consumir voz. El cliente Fish existente reintenta algunos fallos de transporte; no hay garantía de cobro exactamente una vez.

## Usar shorts desde el backend / terminal

No necesitas activar el entorno si usas .venv/bin/python. Todos los comandos siguientes se lanzan desde la raíz del proyecto.

Comprueba la cola y el estado sin generar:

```bash
.venv/bin/python main.py --dry-run
.venv/bin/python main.py --status
```

El formulario guarda los shorts en content_queue.json. Para generar sólo un borrador, sustituye MI_ID por su ID:

```bash
.venv/bin/python main.py --id MI_ID
```

Para importar varios shorts desde un JSON, primero valida y después confirma:

```bash
.venv/bin/python main.py --import-batch mi_lote.json --dry-run
.venv/bin/python main.py --import-batch mi_lote.json --confirm
```

Plantilla mínima de short local Rick (requiere Fish y fondos random):

```json
[{"id":"mi_short_001","subject":"Mi tema","script":"Aquí va toda la narración, con al menos veinte caracteres.","caption":"Texto para las redes","keywords":["tema"],"voice_profile":"rick_es","visual_profile":"random","schedule_enabled":false}]
```

Para asignar las próximas horas libres sin publicar, usa el frontend o estos comandos:

```bash
.venv/bin/python main.py --queue-ready-all --dry-run
.venv/bin/python main.py --queue-ready-all --confirm
.venv/bin/python main.py --schedule-fill --dry-run
.venv/bin/python main.py --schedule-fill --confirm
```

Para revisar lo que se enviaría a Buffer (sin red):

```bash
.venv/bin/python main.py --publish-dry-run
```

Para consultar Buffer y reconciliar posts existentes, sin crearlos:

```bash
.venv/bin/python main.py --sync-buffer-status
```

Para enviar, el frontend permite confirmar un vídeo. El comando siguiente procesa un lote de candidatos según las plazas disponibles; puede subir medios y crear posts. Revisa primero el dry-run y úsalo sólo si quieres rellenar Buffer:

```bash
.venv/bin/python main.py --buffer-maintain
```

## Usar vídeo largo desde el backend / terminal

Puedes reutilizar el JSON que crea el frontend. En los detalles del borrador verás sus rutas y el comando. No ejecutes el mismo trabajo simultáneamente en la interfaz y la terminal.

Si preparas los archivos a mano, guarda el guion en content/longform/mi_video.txt y un JSON en content/longform/mi_video.json con este contenido:

```json
{
  "id": "mi_largo_001",
  "subject": "Mi documental",
  "script_file": "content/longform/mi_video.txt",
  "keywords": ["city", "science"],
  "music_enabled": false
}
```

script_file se resuelve desde la raíz del repositorio. El guion debe acabar con puntuación. Primero comprueba, después genera:

```bash
.venv/bin/python longform.py content/longform/mi_video.json --renderer native --dry-run
.venv/bin/python longform.py content/longform/mi_video.json --renderer native
```

El dry-run largo valida el guion y los requisitos locales sin llamadas de red, bloqueos ni escrituras. Devuelve un error si falta alguna herramienta o clave requerida.

Para usar MPT, indícalo explícitamente:

```bash
.venv/bin/python longform.py content/longform/mi_video.json --renderer mpt --dry-run
.venv/bin/python longform.py content/longform/mi_video.json --renderer mpt
```

Omitir --renderer sigue seleccionando MPT, por compatibilidad. El CLI conserva --resume TASK_ID para recuperar una tarea MPT conocida. --start-over pide otra generación y puede consumir saldo: no lo uses como reparación automática. Los trabajos terminados por CLI se consultan en la terminal y en su carpeta; la lista del estudio no se sincroniza con ejecuciones manuales.

## ¿Puedo borrar MoneyPrinterTurbo?

Todavía no si quieres conservar todas las funciones. La migración es parcial, según el código actual:

- Rick con random y diálogos con fondos locales generan sin MPT.
- El vídeo largo con --renderer native genera sin MPT; sigue marcado como experimental.
- Las narraciones cortas con Pexels siguen usando MPT para generación.
- Los diálogos cortos con fondo Pexels siguen pidiendo el visual a MPT.
- El vídeo largo predeterminado por CLI y la opción MPT de la interfaz siguen usando MPT.

Usar sólo los caminos locales/nativos permite trabajar con MPT apagado, pero no demuestra que la migración completa esté terminada. No se ha eliminado ninguna instalación. Antes de borrarla habría que migrar los shorts Pexels, validar ambos formatos con generaciones reales y decidir qué hacer con tareas MPT pendientes.

## Dónde vive cada cosa

- GUIA.md: este manual; lo lee también «Cómo usarlo» en el frontend. Actualizar aquí mantiene ambos sincronizados.
- AGENTS.md: reglas del proyecto para los agentes.
- content_queue.json: borradores y fechas de shorts.
- state/state.json: intentos, rutas y publicaciones de shorts. No borrar para reintentar.
- content/longform/studio/: guiones y configuraciones creados desde la interfaz.
- state/longform/: estado de trabajos largos del estudio.
- outputs/ready/: vídeos cortos terminados; es también el destino READY_DIR predeterminado, sin copia a Google Drive.
- outputs/longform/: vídeos largos terminados.
- assets/backgrounds/: fondos locales; assets/characters/: poses PNG; assets/music/: música.
- presets/generation_profiles.json: catálogo de voces y estilos.
- .env: claves y configuración privada. Nunca compartir ni subir a Git.
- README.md y PROJECT_GUIDE.md: entradas al proyecto; docs/ contiene auditoría, diseños y roadmap. Las referencias históricas están en docs/archive/.

## Si algo falla

- «No se puede conectar»: ejecuta make studio y abre el puerto 8000. Para desarrollo con Vite se usan dos terminales: .venv/bin/python -m kitok.api y npm --prefix frontend run dev (puerto 5173).
- «Falta configurar»: corrige la herramienta, clave o archivo señalado; las claves se aplican tras reiniciar el backend.
- «No hay fondo»: añade un MP4 compatible a assets/backgrounds/random/ o gameplay/, según el estilo. En herramientas avanzadas también puedes importar un archivo local.
- «MPT»: comprueba su API; la WebUI sola no basta. Sistema incluye un botón de consulta explícita.
- «Interrumpido», timeout o resultado incierto: consulta logs y el proveedor antes de repetir. No borres el historial para forzar un reenvío.

## Desarrollo y siguientes fases

Para verificar cambios usa make verify; para incluir navegador, make verify-browser. El plan multicanal, el director y YouTube directo están en docs/roadmap.md y docs/design/. Son propuestas: no están implementados todavía. Los ejemplos públicos están en examples/; los contenidos del operador no se suben a Git. Los pilotos, backups e importaciones antiguos se conservan en local/.
