# YouTube: API oficial para Kitok y sus agentes

## Estado verificado y alcance

El 12/11/2026 se verificó **Loose Thread**, `@loosethread1`, ID
`UCLnP8Kb1USd06TW3D1JLFvg`, conexión `local/youtube`. Google concedió los siete
permisos de `members`. Data devolvió tres vídeos y Analytics devolvió métricas
diarias y de tráfico. La consulta de ingresos fue aceptada sin filas y la de
membresías devolvió HTTP 403. Se crearon y se releyeron los tres informes privados
diarios `channel_combined_a3`, `channel_reach_combined_a1` y
`channel_traffic_source_a3`. Sus recibos están en el directorio privado. Google
genera los CSV después de crear los trabajos.

El05/11/2026 se verificó por API oficial **Trazo Maldito**, `@trazomalditoes`,
ID `UC9h_aIbnfQUo0ylPsPNnbrg`, conexión `local/youtube-trazo-maldito`:
un vídeo, Analytics diario/tráfico `no_data`, Reporting disponible. Ausencia de
filas no significa cero visitas. El 12/11 Google rechazó la renovación de Trazo
con HTTP 400. Para retomar ese canal, vuelve a autorizarlo con su propio perfil.

El mismo05/11 se completó consentimiento de los **siete scopes del perfil members**
y se comprobó de nuevo el ID remoto correcto. Listas, comentarios, subtítulos y
consulta monetaria aceptadas; ingresos sin filas, miembros403. Reporting devuelve
20tipos; se crearon y releyeron3jobs privados diarios de rendimiento, alcance y
tráfico (combined_a3, reach_combined_a1, traffic_source_a3). IDs/planes/recibos en
`local/youtube-trazo-maldito`; no recrearlos al continuar. No hubo mutaciones de
contenido ni publicación. Esto no demuestra elegibilidad de membresías.

El nuevo CLI de gestión es `scripts/youtube_api.py`. Reutiliza OAuth Desktop,
PKCE/state, almacenamiento privado y bloqueo existentes. El catálogo local recoge
los documentos oficiales de descubrimiento del05/11:83 métodos Data API,
Analytics y Reporting. Es una superficie de API para agentes, no un panel Studio
ni una garantía de elegibilidad del canal para todos los métodos.
Dos entradas se rechazan explícitamente: el RPC streaming del chat en directo
(usar `youtube.liveChatMessages.list`) y el endpoint interno `youtube.tests.insert`.
Las99entradas no equivalen a99operaciones verificadas en vivo.

Permite construir peticiones oficiales de vídeos (subir, metadatos, privacidad,
programación), miniaturas, subtítulos, comentarios/respuestas/moderación, listas,
secciones/opciones del canal expuestas por Google, suscripciones, directos,
consultas Analytics incluyendo ingresos, grupos Analytics y Reporting.
Los métodos se descubren con `catalog`; los permisos y restricciones de Google
siguen aplicándose. Content ID/Content Owner no forma parte de esta integración.
Membresías requieren el perfil adicional y un canal elegible. No existe API para
cualquier ajuste visible en YouTube Studio.

Preparar el acceso no autoriza subir/publicar/borrar ni cambiar contenido concreto.
El agente ejecuta una mutación cuando el operador la encarga, revisando su plan.
El SHA identifica el contenido exacto del plan; no certifica por sí mismo aprobación
humana ni reemplaza el encargo. Mantener esa procedencia en el contexto editorial.

## Conectar y comprobar

Requiere habilitar YouTube Data API v3, YouTube Analytics API y YouTube Reporting
API en Google Cloud y un cliente OAuth **Desktop app**. No pegar secretos en chats.
La conexión existente conserva su cliente; sólo usar setup para una conexión nueva:

```bash
PYTHONPATH=src .venv/bin/python scripts/youtube_readonly.py --directory local/youtube-trazo-maldito setup --client /ruta/privada/desktop.json
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py connect --profile manage
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py status
PYTHONPATH=src .venv/bin/python scripts/youtube_readonly.py --directory local/youtube-trazo-maldito sync

# Renovar Loose Thread con el cliente Desktop ya configurado:
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --directory local/youtube --channel UCLnP8Kb1USd06TW3D1JLFvg connect --profile members
```

Perfiles explícitos:

| Perfil | Permisos solicitados |
| --- | --- |
| `read` (predeterminado) | `youtube.readonly`, `yt-analytics.readonly` |
| `manage` | Los anteriores más `youtube`, `youtube.force-ssl`, `youtube.upload`, `yt-analytics-monetary.readonly` |
| `members` | Los de manage más `youtube.channel-memberships.creator` |

Hay solapamiento entre permisos de gestión; se conservan los permisos explícitos
para cubrir los métodos que declara el catálogo. No se aceptan scopes ajenos.
`status` muestra scopes guardados, nunca tokens, y **no acredita acceso remoto**.
Una conexión antigua de lectura sigue funcionando. Un nuevo consentimiento debe
conceder el perfil entero; un consentimiento parcial no sustituye los tokens previos.
El retorno OAuth escucha en127.0.0.1 temporal y el navegador debe llegar a WSL.
Cada canal usa un directorio independiente. Al reconectar, Kitok comprueba con
Google el ID esperado (por `--channel` o el vínculo guardado) antes de reemplazar
las credenciales. Si se elige el otro canal, el estado anterior se conserva.

En Google Cloud se comprobó el 12/11 el proyecto `kitok-youtube-analytics` en estado
**Prueba**, usuarios externos; «Publicar app» deshabilitado y la consola remite a
completar la marca. Las URLs públicas de app/privacidad/condiciones estaban vacías.
No inventar dominio/políticas ni afirmar paso a producción sin verlo confirmado.
En prueba, estos scopes pueden producir refresh tokens con caducidad de siete días.
Publicar la app OAuth y publicar un vídeo son operaciones diferentes.

## Consultas y catálogo para agentes

Desde la raíz de Kitok, el CLI nuevo usa por defecto la conexión de Trazo.
En consultas/mutaciones es obligatorio `--channel`; no deducirlo de un nombre:

```bash
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py catalog
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py catalog youtube.videos.update
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --channel UC9h_aIbnfQUo0ylPsPNnbrg query --request examples/youtube/channel.json
```

Peticiones JSON: `operation`, `params`, `body` opcional y `media` opcional (ruta
local para subir). Parámetros `repeated` del discovery se expresan como arrays;
por ejemplo `part:["snippet","status"]`, no un string. El CLI valida nombres,
tipos y enums; Google valida restricciones de negocio, campos editables y cuota.
`query` es GET sin body/media. Se devuelve la respuesta con procedencia/canal;
la paginación es explícita: repetir query con `pageToken`/`nextPageToken`.
No hay recolección histórica desatendida ni purga automática.

Analytics es `youtubeAnalytics.reports.query`; acepta métricas/dimensiones/filtros
oficiales, con `ids:"channel==MINE"`. Ingresos necesitan permiso monetario y datos
disponibles. La consulta de ingresos incluida es una muestra, no prueba de ingresos.
Las fechas son Pacific time. Conservar ausencia/denegación como tales, nunca ceros.

Los comandos `public-search` y `reporting-status` dan una salida compacta para
descubrimiento y seguimiento de CSV. Las vistas y suscriptores proceden de
Data API. La búsqueda hidrata una sola página y preserva su orden. La consulta
de informes incluye el trabajo y los IDs disponibles para `download-report`.
[Método y ejemplos](../research/loose-thread.md#consultar-datos-sin-copiar-archivos-de-petición).

## Mutaciones con vista previa

```bash
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --channel UC9h_aIbnfQUo0ylPsPNnbrg plan --request /ruta/privada/cambio.json
# Revisar canal, body completo, before, hash de media y aviso de reemplazo.
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --channel UC9h_aIbnfQUo0ylPsPNnbrg apply --approve SHA256_DEL_PLAN_REVISADO
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py receipt
```

`plan` hace lecturas, no cambios remotos. Es privado, caduca a los30minutos y
puede prepararse antes del consentimiento ampliado (`scope_ready:false`).
`apply` comprueba SHA, caducidad, canal remoto, scopes, archivo y snapshot remoto
cuando exista. Guarda recibo **antes** del envío y conserva planes/recibos privados por SHA entre operaciones; un plan antiguo enviado tampoco se puede repetir. No reintenta automáticamente.

**PUT reemplaza las partes indicadas**: una actualización de snippet debe incluir
las propiedades que se quieren conservar (título, descripción, categoryId, tags,
idioma, etc. según las reglas del recurso). No hace merge silencioso. El campo
`before` muestra el snapshot cuando hay un listado directo por ID compatible;
si es null no hay comparación de concurrencia ni lectura posterior automática.
Esto afecta, por ejemplo, a subtítulos sin videoId y métodos sólo de acción.
Para subtítulos con contexto, `body.snippet.videoId` permite obtener el snapshot.
Si otra aplicación cambia un recurso con snapshot, hay que crear un plan nuevo.
DELETE puede ser irreversible y requiere encargo específico.

Las subidas usan el protocolo oficial resumible y streaming del archivo, sin
cargarlo entero en RAM. También hay subida binaria simple para endpoints que la
declaran. Se conservan la URL privada de sesión y el hash del archivo en el recibo;
la salida CLI oculta esa URL. No hay un bucle de recuperación automática de bytes:
`reconcile` consulta el estado de la sesión, pero no reenvía el archivo. Revisar
manualmente un envío parcial antes de continuar; no iniciar otra subida a ciegas.

Para programar un vídeo nuevo, usar videos.insert con status.privacyStatus private
y status.publishAt RFC3339 futuro; para uno existente, respetar las restricciones
de videos.update (no haber sido publicado, etc.). Los proyectos sin auditoría
pueden tener subidas restringidas a privado; el consentimiento no elimina esa
restricción. No se ha probado una publicación real durante esta ampliación.

## Resultados inciertos y descargas

Un rechazo definitivo4xx queda `failed` y permite preparar otro plan corregido.
Timeouts, errores5xx y fallos ambiguos quedan `uncertain`; bloquean otros envíos.
No borrar recibos ni tokens para desbloquearlos:

```bash
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --channel UC9h_aIbnfQUo0ylPsPNnbrg reconcile
# Tras comprobar el resultado remoto concreto, cierre local documentado:
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --channel UC9h_aIbnfQUo0ylPsPNnbrg resolve --approve SHA256_DEL_RECIBO --outcome not_applied --evidence 'Evidencia remota concreta revisada y su fecha'
```

`resolve` no envía una mutación, conserva resultado/evidencia; no permite repetir
el mismo plan. Si procede otro intento, preparar/revisar un plan nuevo.

Reporting: `youtubereporting.reportTypes.list`, `jobs.list`, `jobs.create`,
`jobs.reports.list`. Crear un job configura generación diaria remota y pasa por
plan/apply; no crear duplicados. El CSV no aparece inmediatamente.

```bash
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --channel UC9h_aIbnfQUo0ylPsPNnbrg download-report --job JOB_ID --report REPORT_ID --output /ruta/privada/informe.csv
PYTHONPATH=src .venv/bin/python scripts/youtube_api.py --channel UC9h_aIbnfQUo0ylPsPNnbrg download-caption --caption CAPTION_ID --format srt --output /ruta/privada/subtitulos.srt
```

Las descargas no sobrescriben archivos, quedan0600 y se transmiten por streaming
con límite512MiB. Reporting obtiene la URL del recurso oficial y sólo admite
HTTPS en youtubereporting.googleapis.com/v1/media/; rechaza redirecciones/hosts
alternativos antes de transmitir Bearer. No hay fetch de URL arbitraria.

Cliente, tokens, snapshot, plan y recibo viven en el directorio privado, fuera de
Git/frontend, con0700/0600, escritura atómica y bloqueo. No exponerlos por HTTP ni
copiarlos a documentación. Los errores no incluyen cuerpos de Google ni tokens.

## Fuentes oficiales y verificación

- [Data API y métodos](https://developers.google.com/youtube/data/reference/rest).
- [OAuth Desktop](https://developers.google.com/identity/protocols/oauth2/native-app).
- [Analytics reports.query](https://developers.google.com/youtube/analytics/reference/reports/query).
- [Reporting jobs.create](https://developers.google.com/youtube/reporting/v1/reference/rest/v1/jobs/create).
- [Subidas resumibles](https://developers.google.com/youtube/data/guides/using_resumable_upload_protocol).
- [Caducidad de tokens](https://developers.google.com/identity/protocols/oauth2#expiration).
- [Políticas del desarrollador](https://developers.google.com/youtube/terms/developer-policies).

La compatibilidad de lectura y los límites de gestión se prueban con MockTransport
sin tocar recursos reales. Los tests no demuestran elegibilidad, subida pública,
moderación real ni disponibilidad de ingresos. Ver PROJECT_STATUS.md para el
último consentimiento y comprobación en vivo, separados de la implementación.
