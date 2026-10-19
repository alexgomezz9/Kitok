# YouTube: conexión local de lectura

Implementado: OAuth Desktop y CLI oficial. Verificado con pruebas aisladas y
revisión de seguridad. **La autorización real de Google y las métricas de tu canal
no se han comprobado todavía.** El MCP vidIQ existente reconoce LooseThread;
su comprobación de autorización reciente pide verificar la cuenta. Esa conexión
no entrega sus credenciales al proceso Python de Kitok.

## Preparar la cuenta una sola vez

1. En tu proyecto de Google Cloud habilita YouTube Data API v3, YouTube Analytics
   API y YouTube Reporting API. Configura el consentimiento; si la aplicación está
   en prueba, añade tu cuenta como usuario de prueba.
2. Crea un cliente OAuth de tipo **Desktop app** y descarga su JSON privado.
   No lo pegues en chats ni lo guardes dentro de archivos versionados.
3. Desde la raíz de Kitok, utiliza el archivo descargado:

```bash
PYTHONPATH=src .venv/bin/python scripts/youtube_readonly.py setup --client /ruta/privada/desktop.json
PYTHONPATH=src .venv/bin/python scripts/youtube_readonly.py connect
```

Autoriza la cuenta en el navegador. Google exige esa interacción; ningún MCP
puede sustituir el consentimiento del titular. El retorno usa 127.0.0.1 temporal,
PKCE S256 y state con caducidad y uso único. Sólo se solicitan youtube.readonly y
yt-analytics.readonly, sin upload, force-ssl ni permisos monetarios.
[Flujo oficial Desktop](https://developers.google.com/identity/protocols/oauth2/native-app).

## Consultar

```bash
PYTHONPATH=src .venv/bin/python scripts/youtube_readonly.py status
PYTHONPATH=src .venv/bin/python scripts/youtube_readonly.py sync
PYTHONPATH=src .venv/bin/python scripts/youtube_readonly.py sync --start 2026-10-01 --end 2026-10-17 --video ID_DEL_VIDEO
```

status muestra estado local: no prueba una sesión remota válida. sync comprueba
identidad, catálogo, vistas/AVD diarios, tráfico y, si indicas un vídeo del canal,
su retención. Las fechas de Analytics corresponden a Pacific time. Se conserva
un snapshot privado con procedencia y resultados; los datos ausentes o denegados
no se convierten en ceros. No se atribuyen causas automáticas a una caída.

Conexiones de varios canales: utiliza un --directory privado distinto antes del
subcomando; se comprueba y conserva el ID remoto. No deducir identidad por nombre.

## Límites actuales

Reporting enumera tipos, jobs e informes existentes. **No crea jobs ni descarga
CSV**, por lo que impresiones/CTR todavía no se importan. Google ofrece esas
métricas mediante los informes channel_reach_basic_a1/combined_a1; no las inventes
con vistas totales ni las confundas con CTR de anotaciones. Si no existe un job,
crearlo sería una configuración remota adicional, fuera de esta lectura estricta.
[Informes oficiales](https://developers.google.com/youtube/reporting/v1/reports/channel_reports#reach-reports).

No hay dashboard analítico, subidas, modificaciones, borrado de vídeos o respuestas
a comentarios. No se han gastado créditos de investigación vidIQ. El snapshot
permanece en local/youtube con permisos restrictivos; aún no hay purga automática
ni verificación programada a 30 días. Esta primera versión no es un almacén
histórico desatendido; revisar políticas antes de habilitarlo como tal.
[Políticas](https://developers.google.com/youtube/terms/developer-policies).

Cliente, tokens y snapshot viven bajo local/youtube, fuera de Git y del frontend;
archivos 0600, carpeta 0700, escritura atómica y bloqueo. El transporte usa
endpoints Google fijos y no sigue redirecciones. Los errores no muestran tokens
ni cuerpos sensibles. No copies estos archivos a documentación o informes.

## Repositorios estudiados

- [ConorBronsdon](https://github.com/conorbronsdon/yt-analytics-mcp): buena superficie GET acotada como referencia, sin Reporting y
  con algunas afirmaciones documentales obsoletas; no instalado globalmente.
- [Modbender](https://github.com/modbender/youtube-analytics-mcp): alcance demasiado amplio, OAuth sin state/PKCE y recorrido CSV sin
  completar en el código inspeccionado.
- [FelipeFontoura](https://github.com/felipefontoura/youtube-studio-mcp): scopes y herramientas de escritura, y descarga de URL arbitraria
  con Bearer; descartado para una conexión estrictamente de lectura.
- [Jakeschincariol](https://github.com/Jakeschincariol/youtube-agent-skill): instrucciones y utilidades editoriales MIT, no un conector ni
  un orquestador completo. Sus scores son heurísticos; parser de pausas/retención
  tiene casos de unidades, decimales y JSON que requieren corrección antes de uso.

La implementación local reutiliza httpx/stdlib existentes y evita instalar tres
servidores completos o copiar herramientas de publicación que no necesitamos.

Del último repo adoptamos la separación de voz editorial, intención del montaje
y revisión de retención con fuentes. No copiamos sus seis parsers ni instalamos
las once skills globalmente: no conectan YouTube y sus heurísticas no prueban
retención futura. El compilador local ejecuta decisiones explícitas verificadas.
