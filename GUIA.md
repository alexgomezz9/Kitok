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
2. Pulsa «Comprobar sin generar». Valida el contenido y muestra requisitos locales. No hace llamadas a Fish, Pexels, Cloudinary ni Buffer.
3. Guarda el borrador. Después pulsa «Generar». Esta segunda acción sí usa los proveedores necesarios y puede consumir saldo.
4. Reproduce el resultado. Descárgalo o, para shorts, elige una fecha y revisa el envío a Buffer.

La comprobación local no demuestra que las claves sean válidas, que haya saldo ni que un servicio esté conectado. Tampoco puede saber la duración exacta antes de sintetizar la voz.

## Crear un short desde el frontend

En «Crear short» elige uno de los estilos básicos:

- Rick: una narración con voz Fish, personajes/subtítulos del formato existente y un fondo de assets/backgrounds/random/. No necesita MPT.
- Rick y Morty: diálogo por turnos, voces Fish y gameplay local. Los PNG transparentes van en assets/characters/rick/ y assets/characters/morty/. No necesita MPT con fondo local.
- Narración con Pexels: Fish, búsquedas y montaje FFmpeg nativos. Elige una voz Fish; Álvaro se conserva sólo como dato de borradores antiguos.

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
2. Elige narrador. Loose Thread conserva su voz original en inglés. En «Biblioteca de voces y favoritos» puedes escuchar muestras existentes, guardar favoritas y asignarlas a un canal sin sintetizar. El texto se lee tal como está escrito.
3. Elige música: «Desactivada», «Automática» o «Elegir manualmente». Automática elige pistas locales verificadas para inicio y cierre, rota entre trabajos y mezcla dos ambientes con crossfade y ducking bajo la voz. Usa una frontera de secciones cuando la alineación es válida; si falta, declara un cambio central estimado. En Manual aparece un reproductor de la pista; en Automática puedes desplegar la biblioteca para escucharla antes de generar. Manual conserva la pista seleccionada. Si faltan recursos, la comprobación lo indica; consulta [la biblioteca de audio](docs/audio.md).
4. Elige «Montaje básico» o «Documental enriquecido». El segundo añade preguntas, cifras, fechas, presentaciones explícitas y conceptos técnicos cuando reconoce una intención compatible. Con música automática puede añadir puntuación sonora discreta; no hay un efecto en cada corte. Antes de lanzar el vídeo completo revisa las muestras de «Montaje → Galería documental».
5. Comprueba sin generar y guarda el borrador. Se crean automáticamente un .txt y un .json en content/longform/studio/; no necesitas escribir un JSON ni preparar cada plano.
6. Después de revisar la calidad de las muestras, selecciona el borrador y pulsa «Generar vídeo largo». Kitok ejecuta el montaje elegido para todo el guion. Espera a «Terminado», reproduce y descarga el MP4 y sus créditos. Durante el montaje documental muestra el plano actual y el total.

En generación nueva y recuperación, Kitok calcula los tramos de stock con la duración real del vídeo local, no con los segundos redondeados de Pexels. Comprueba todos los planos antes de renderizar el primero. Si un archivo completo no alcanza la duración necesaria, se detiene antes de mezclar y conserva la narración; no estira ni congela el plano.

La interfaz y el CLI usan el motor nativo: Fish + Pexels + FFmpeg. El largo nativo sigue siendo experimental; no necesita MPT. No se ofrecen nuevos trabajos MPT. Los trabajos históricos se conservan para consulta y recuperación explícita.

La salida es horizontal 16:9, 1920×1080, sin subtítulos, en outputs/longform/. La duración depende del guion y de la voz; no se fija con un selector de minutos. Se admiten hasta 24.000 caracteres y 20 búsquedas. El montaje básico organiza el guion en secciones y usa esas búsquedas. Los tiempos de sección pueden ser estimados; esto no garantiza que cada plano ilustre exactamente la frase. El modo enriquecido sigue reglas conservadoras: no investiga, no entiende cualquier guion y no convierte automáticamente todas las frases en gráficos. Los tiempos sin alineación válida se declaran estimados. Para control por escena usa «Montaje». Las escenas locales también aceptan fotografías con encuadre completo, once movimientos de cámara y transiciones entre fuentes móviles; consulta [el contrato de montaje](docs/editing.md).

Los vídeos largos no entran en el calendario ni en el publicador Buffer de shorts. Descárgalos y súbelos a YouTube Studio. Los largos antiguos creados sólo por CLI siguen en outputs/longform/; la nueva lista muestra los borradores creados en este estudio.

Si falla o se interrumpe, no se vuelve a generar automáticamente. Revisa logs/kitok-AAAAMMDD.log y los archivos antes de crear otra copia. Repetir una generación puede volver a consumir voz. El cliente Fish de Kitok no reintenta peticiones de voz tras un fallo; un resultado incierto requiere revisión. La caché permite reutilizar audio confirmado sin pedir otra síntesis. El montaje documental y la música de biblioteca conservan salidas exclusivas: `--start-over` no las reemplaza; usa una revisión/ID nuevos después de revisar el trabajo. Los modos nuevos sólo se admiten con Native, no en recuperación MPT.

CLI y web comparten Native. Un JSON antiguo con montaje básico y música manual
puede usar una rama distinta de uno con montaje documental o música de biblioteca;
usa la misma configuración al compararlos. El montaje documental comprueba ahora
los fotogramas exactos por plano y al unirlos. Un rechazo muestra valores medidos
y conserva los diagnósticos, planos y narración. Tras actualizar el código,
reinicia tu backend cuando esté inactivo para cargar la corrección; actualizar
la página no reinicia ni cancela el trabajo del servidor.

### Añadir fotos y documentos reales

En «Vídeo largo», despliega **«Fotografías y documentos del caso · opcional»**.
Selecciona la carpeta del episodio; `3_ultimatebet` ya encuentra las cuatro fotos
que has colocado en `real_images/`. Para otro episodio usa «Crear carpeta de
episodio» y añade JPG, PNG o WebP, o colócalos manualmente en `images/`.

Elige el archivo, copia una frase exacta del guion y pulsa **«Añadir imagen en
esta frase»**. Kitok elige duración (hasta 4 s), movimiento suave variado y
transición. Puedes añadir varias fotos así, sin escribir un JSON detallado.
Comprobar y guardar siguen sin generar voz ni descargar stock.

También puedes importar un guion `.txt` y un JSON visual preparado por ChatGPT.
El JSON describe sólo momentos importantes; el stock cubre lo restante. En «Ver
o ajustar JSON visual» puedes cambiar duración, cámara, encuadre, transición o
texto. [Ejemplo mínimo](examples/visuals/minimal.json) y
[contrato con parámetros](docs/editing.md). Las frases repetidas admiten
`occurrence` desde cero. Si no hay alineación precisa, Kitok declara los tiempos
estimados. Revisa identidad, contexto y permisos de las imágenes aportadas.

### Corregir el montaje usando la voz de otro trabajo

En «Narración para este montaje», selecciona un trabajo Native anterior terminado,
fallido o interrumpido. El estudio conserva su guion y narrador. Cambia el título,
fotos o JSON visual, comprueba y guarda un **borrador nuevo**. La salida original
se conserva; cada montaje usa un ID distinto.

En la ficha nueva pulsa **«Revisar voz original sin generar»** y después
**«Iniciar nuevo montaje · sin Fish ni red»**. La auditoría comprueba guion, voz,
velocidad, modelo, recibo Fish, alineación y hashes; confirma nuevamente esos
archivos antes de encolar. Falta de caché o cambio de identidad detiene el trabajo;
no hay alternativa automática que sintetice de nuevo. Este recorrido monta el
vídeo completo sólo cuando tú lo inicias. No uses el CLI normal del borrador
marcado para reutilizar voz: exige la confirmación del estudio.

La narración se reutiliza íntegra; la música puede mezclarse con las opciones
seleccionadas para el nuevo montaje. Un plan editorial con audio final aprobado
lo conserva sin normalizarlo. Windows, escucha y aprobación del montaje siguen
requiriendo revisión de su resultado.

### Recuperar un largo fallido conservando la voz pagada

En la ficha de un trabajo Native fallido o interrumpido, pulsa **«Revisar recuperación sin generar»**. La auditoría sólo lee: comprueba guion/configuración guardados, MP3 y alineación, manifiesto de montaje y recibo Fish confirmado para esa voz, modelo y velocidad. Muestra duración y SHA-256. Si algo falta, cambió, no coincide o ya existe una salida, se detiene. No llama a Fish ni a Pexels.

Sólo después de revisar esa información, **«Recuperar montaje usando esta voz · sin Fish ni red»** retoma el mismo trabajo con el mismo ID. Esta acción sí monta el vídeo completo. Usa el ejecutor y bloqueo compartidos; conserva el error previo y trabaja en una nueva subcarpeta `recovery-*`, sin borrar el audio, cachés ni temporales anteriores. Comprueba las búsquedas que usa el montaje, no las palabras de búsqueda descartadas del borrador. Si falta stock o música local necesarios, falla sin descargar ni sintetizar. No crees otro borrador ni uses el comando normal de generación para esta recuperación.

Desde terminal, la auditoría es el comportamiento predeterminado y no inicia ningún montaje:

```bash
.venv/bin/python scripts/recover_longform.py lf_cf5e16bb422547aabfb4f5b8b9ef131a
```

Para iniciar explícitamente la recuperación, usa los dos valores completos que devuelve la auditoría actual:

```bash
.venv/bin/python scripts/recover_longform.py MI_ID --recover --narration-sha256 SHA256_NARRACION --audit-fingerprint HUELLA_AUDITORIA
```

La confirmación se vuelve a validar bajo bloqueo antes de poner el montaje en cola. Si cambian los archivos, se rechaza; no hay alternativa automática que vuelva a generar voz. La auditoría acredita la identidad de la narración; el resultado del montaje se verifica cuando termina la recuperación.

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

Omitir --renderer selecciona native. Para recuperar una tarea MPT **ya enviada**,
se conserva únicamente este recorrido histórico, que requiere su API:

```bash
.venv/bin/python longform.py content/longform/mi_video.json --renderer mpt --resume TASK_ID
```

No admite nuevas tareas MPT ni --start-over con ese motor. Conserva su ID y revisa
los archivos antes de una recuperación. Los trabajos terminados por CLI se
consultan en la terminal y en su carpeta; la lista del estudio no se sincroniza
con ejecuciones manuales.

## Mejorar un montaje sin volver a pagar la voz

Con un MP4 y audio ya aprobados, puedes preparar un plan por escenas y reutilizar
los recursos locales. El montaje guarda cifras con significado, diagramas,
rótulos y movimientos elegidos por escena. Cambiar un plano reutiliza el resto.

En «Montaje», selecciona «UltimateBet — C» para comparar el montaje anterior
(A) con la nueva versión (B). Conservamos también la comparación original.
El enlace de fuentes y licencias acompaña a la muestra nueva.
La «Galería documental» ofrece efectos individuales y fragmentos con reproducción, descarga, referencia A/B y créditos. Pulsa «Reproducir muestra» o «Reproducir referencia básica»: se carga un vídeo cada vez. «Ver fotogramas de revisión» muestra un mosaico estático, no la animación. Si el navegador avisa de un error, conserva el enlace para descargar ese MP4 y probarlo en un reproductor local. Revisa primero las tres muestras UltimateBet y la de otro tema. «Renderizar plan guardado» vuelve a montar los recursos sin sintetizar voz.
Para otro vídeo prepara un brief o un plan local; no hay editor visual de timeline.
Los planos 3D opcionales requieren `make cinema-setup` una sola vez.
La nueva biblioteca de composiciones y sus comandos locales están en
[docs/motion.md](docs/motion.md).

La preparación y el comando están en [docs/editing.md](docs/editing.md), con una
plantilla en examples/editorial/plan.json. No genera guion ni hace llamadas a
Fish/Pexels. El informe comprueba el archivo real y puede exigir el mismo audio
que la referencia; la revisión visual sigue siendo necesaria.

## ¿Puedo borrar MoneyPrinterTurbo?

Para **generar nuevos shorts y largos**, Kitok ya usa Fish + FFmpeg, con Pexels
cuando corresponde. Interfaz y CLI no necesitan que MPT esté instalado o encendido.
Álvaro/Edge se conserva sólo para leer datos antiguos: elige una voz Fish al
preparar nuevos vídeos. No existe una dependencia nueva de Edge TTS.

Queda compatibilidad histórica: --check-mpt y la recuperación de una tarea larga
mediante --renderer mpt --resume TASK_ID necesitan su API. No son el modo normal
de generación. Si tienes una tarea MPT sin recuperar o medios guardados dentro
de su carpeta, recupéralos/conserva esos archivos antes de desinstalarlo.
No se ha borrado ninguna instalación ni convertido automáticamente sus tareas.

Se han probado los recorridos nativos con FFmpeg real y proveedores simulados,
y se ha reeditado UltimateBet con audio y stock ya existentes. Esto no equivale
a una nueva generación completa de cada estilo contra Fish/Pexels reales.

## Conectar YouTube para lectura

La conexión oficial opcional está preparada como CLI. La configuración de cuenta,
los comandos y los límites están en docs/integrations/youtube-readonly.md.
Necesita una autorización de Google en el navegador y un cliente OAuth Desktop;
no publiques ni pegues sus credenciales. No permite subir, modificar o borrar vídeos.
El acceso real a las métricas sigue pendiente del consentimiento de tu cuenta.

## Dónde vive cada cosa

- GUIA.md: este manual; lo lee también «Cómo usarlo» en el frontend. Actualizar aquí mantiene ambos sincronizados.
- AGENTS.md: reglas del proyecto para los agentes.
- content_queue.json: borradores y fechas de shorts. Ejemplo público: examples/shorts/queue.json.
- main.py y longform.py: entradas CLI; la implementación está en src/kitok/.
- scripts/dashboard.py: entrada del panel Streamlit opcional, separado del estudio diario.
- state/state.json: intentos, rutas y publicaciones de shorts. No borrar para reintentar.
- content/longform/studio/: guiones y configuraciones creados desde la interfaz.
- content/longform/ID/assets/: recursos específicos aportados para un episodio; excluidos de Git.
- state/longform/: estado de trabajos largos del estudio.
- outputs/ready/: vídeos cortos terminados; es también el destino READY_DIR predeterminado, sin copia a Google Drive.
- outputs/longform/: vídeos largos terminados.
- outputs/evaluation/: comparaciones A/B, planes y comprobaciones locales.
- PROJECT_STATUS.md: estado técnico breve y siguiente paso; no sustituye este manual.
- assets/backgrounds/: fondos locales; assets/characters/: poses PNG; assets/music/: música.
- presets/generation_profiles.json: catálogo de voces y estilos.
- .env: claves y configuración privada. Nunca compartir ni subir a Git.
- README.md y docs/README.md: entradas e índice de documentación vigente.
- docs/capabilities.md: qué se automatiza y cómo adaptar el flujo a otros vídeos.
- docs/archive/README.md: índice histórico separado de los manuales actuales.

## Si algo falla

- «No se puede conectar»: ejecuta make studio y abre el puerto 8000. Para desarrollo con Vite se usan dos terminales: .venv/bin/python -m kitok.api y npm --prefix frontend run dev (puerto 5173).
- «Falta configurar»: corrige la herramienta, clave o archivo señalado; las claves se aplican tras reiniciar el backend.
- «No hay fondo»: añade un MP4 compatible a assets/backgrounds/random/ o gameplay/, según el estilo. En herramientas avanzadas también puedes importar un archivo local.
- Un borrador histórico con MPT o Álvaro no se reenvía automáticamente. Prepara uno nuevo con voz Fish; conserva los IDs antiguos para consultar o recuperar tareas ya enviadas.
- «Interrumpido», timeout o resultado incierto: consulta logs y el proveedor antes de repetir. No borres el historial para forzar un reenvío.

## Desarrollo y siguientes fases

Para verificar cambios usa make verify; para incluir navegador, make verify-browser. El compilador de briefs y el CLI de YouTube de lectura están implementados con los límites de este manual. La orquestación editorial general y los perfiles multicanal completos siguen siendo propuestas en docs/roadmap.md. Los ejemplos públicos están en examples/; los contenidos del operador no se suben a Git. Los pilotos, backups e importaciones antiguos se conservan en local/.

## Recursos específicos con licencia

El catálogo local conserva procedencia, autor, licencia, hash, entidad y función de
cada imagen. Buscar devuelve candidatos; no identifica automáticamente a una
persona ni convierte una fotografía de contexto en prueba del caso.

```bash
.venv/bin/python scripts/media_library.py search "Russ Hamilton"
.venv/bin/python scripts/media_library.py fetch "File:Russ Hamilton 2007.jpg" --entity "Russ Hamilton" --role portrait --usage identity
.venv/bin/python scripts/media_library.py list
```

Sólo `search` y `fetch` consultan Commons. `fetch` acepta imágenes raster con una
licencia comercial explícita compatible y conserva las obligaciones de atribución
y ShareAlike. Revisa la página y el contexto antes de anotar identidad/función.
`list` lee `cache/media-library/`; no descarga ni genera voz. Content ID figura
como desconocido: la licencia no garantiza ausencia de reclamaciones automáticas.

## Música y efectos locales

La biblioteca incluye 20 pistas auditadas de Kevin MacLeod (CC BY4.0), con
fuente oficial, autor, licencia, hash y créditos por archivo. Las búsquedas y las
mezclas no generan voz. El catálogo, licencias y voces se explican en [docs/audio.md](docs/audio.md). La primera descarga usa Internet; las siguientes reutilizan
la caché verificada. No es una suscripción ni un servicio de generación de pago.

```bash
.venv/bin/python scripts/audio_library.py list
.venv/bin/python scripts/audio_library.py fetch all
.venv/bin/python scripts/audio_library.py select --job mi_episodio --channel loose_thread --mood investigation
.venv/bin/python scripts/audio_library.py mix --job mi_episodio --narration RUTA_AUDIO_EXISTENTE.mp3 --duration 60 --output outputs/mi_mezcla.m4a
```

Sustituye la ruta y usa un nombre de salida nuevo. La selección por trabajo queda
estable; un nuevo trabajo rota la pista principal cuando hay alternativas. El
mezclador enlaza dos pistas y baja la música mientras habla el narrador, conserva
la voz hasta el final y mide sonoridad/pico. No reemplaza el audio original. En los largos del formulario puedes elegir la
biblioteca mediante «Automática» o «Elegir manualmente». Entrega un `.m4a.json` con fuentes,
créditos y cambios: inclúyelos cuando uses el resultado. Content ID es desconocido.

Para un efecto original discreto sin muestras externas:

```bash
.venv/bin/python scripts/audio_library.py sfx --output outputs/mi_tick.wav
```

## Preparar automáticamente un plan desde decisiones editoriales

Los agentes pueden guardar un brief con escenas, afirmaciones respaldadas y roles
visuales. El compilador busca recursos del catálogo local y propone cámaras sin
volver a generar voz ni contactar proveedores:

```bash
.venv/bin/python scripts/direct_edit.py outputs/evaluation/MI_ID/brief.json --output outputs/evaluation/MI_ID/plan_nuevo.json
```

Si falta un recurso, lo indica y no entrega un plan a medias. La preparación
requiere ese brief; no basta con pegar un guion arbitrario. Detalles y límites en
[docs/editing.md](docs/editing.md). La muestra C conserva su brief para reutilizarla.

Para anotar un clip Pexels ya descargado y revisado, sin volver a pedirlo:

```bash
.venv/bin/python scripts/media_library.py register-pexels 7328530 --entity "Poker table and chips" --role footage
```

Siempre queda como ilustración, con la licencia Pexels y su página de origen;
no como una imagen histórica ni como identidad de una persona. El catálogo usa
la resolución realmente medida. Si no coincide con la declarada, exige revisión
expresa; no modifica la caché original para ocultar la diferencia.
