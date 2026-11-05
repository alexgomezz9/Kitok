# Estado vigente de Kitok

Actualizado: **05/11/2026**. Rama `feat/agent-browser-video-tools`, base local `4e1bf1b`
(sobre `feat/youtube-agent-api`). Operación: [GUIA.md](GUIA.md).

## Herramientas QA y vídeo opcional05/11

Playwright CLI0.1.23+MCP0.0.84 instalados en entorno Codex WSL, mismo
Playwright/Chromium1252. Inicialización/listado MCP y clic/captura/consola0errores
verificados con página local sintética; CLI también pasó. Descubrimiento real en
chat nuevo de VS Code WSL pendiente; no es QAcompleto de Curbops/Kitok.
HyperFrames0.9.16+dos skills del proyecto, wrapper fijado con telemetría apagada:
checkok, snapshot y renderMP4real2s640×360/12fps con fotograma visto.
WSLusa softwareWebGL/CPU; no prueba rendimiento de episodios. Native/Fish/inputs
existentes conservados. Skills/TOML/documentación/higiene validados y revisión
independiente sin hallazgosP1/P2. [Manual](docs/integrations/agent-tools.md).

## YouTube API para agentes

OAuth Desktop ampliado y **siete scopes concedidos en Google**, incluida gestión,
subida, ingresos y miembros. Identidad remota comprobada después del consentimiento:
Trazo Maldito `UC9h_aIbnfQUo0ylPsPNnbrg`, conexión `local/youtube-trazo-maldito`;
no LooseThread. Refresh token guardado, sin secretos en Git/frontend.
CLI `PYTHONPATH=src .venv/bin/python scripts/youtube_api.py catalog`:
99entradas discovery oficiales; excluidos RPC streaming (usar liveChatMessages.list)
y endpoint interno tests.insert. Consultas, plan/apply con SHA/canal/snapshot cuando
disponible, recibos históricos privados, transferencias y reconciliación sin retry.
[Contrato y ejemplos](docs/integrations/youtube-readonly.md).

Lecturas reales05/11:1vídeo,1lista,2tracks de subtítulos, comentarios consultables;
Analytics/ingresos aceptados sin filas.20tipos Reporting disponibles; creados y
releídos3jobs diarios: rendimiento combined_a3, alcance reach_combined_a1 y tráfico
traffic_source_a3. IDs/recibos en almacenamiento privado; esperar informes de Google.
Miembros devuelve403 pese al scope; canal observado sin monetización. No se subió,
editó, publicó ni borró contenido. Mutaciones de contenido verificadas con mocks,
no con una publicación real.

Google Cloud `kitok-youtube-analytics`: scopes guardados, sigue **Prueba** y
«Publicar app» deshabilitado por marca incompleta. URLs públicas vacías; no inventar
política/dominio. Mientras siga en Prueba, consentimiento/refresh con límite7días.
Pendiente URL pública de aplicación/privacidad del operador para continuar marca.

Verificación: suite global1380passed/14skipped (399,74s), después63pruebas focales
con historial/replay y fixes de revisión independiente; frontend25passed y build
TypeScript/Vite, studio-check, docs-check, source hygiene y whitespace. El wrapper
verify se paró al llegar a npm por PATH Windows; pasos frontend restantes pasaron
con `.tools/node/bin` explícito. No se repitió generación de episodios ni proveedores.
Cambios locales; no merge/despliegue ni push/CI remoto verificados.

Siguiente: usar catalog/query para agentes; plan/apply sólo con encargo concreto
de modificación/publicación. Resolver marca de Google y comprobar los CSV cuando
Google los genere. El trabajo editorial de abajo conserva su estado previo.

## Slenderman012 en cola GPU

Revisión activa: `content/longform/trazo_012_slenderman/revisiones/montaje_final`.
Guion1543palabras, voz499,278s conservada:1Fish,0cortes/resíntesis. ASR local
completo sin inserciones/omisiones ni actividad pendiente; reemplazos revisados
documentalmente. Sin escucha humana.111PNG vistos/validados,3reparaciones
materiales;108fuentes pequeñas y3individuales. Native escala sin detalle nuevo.
14capítulos reales,9etiquetas y miniatura1280×720 vista. Pacingpassed:
0-30s19imágenes/hold3,367s;30-60s10/hold4,8s;bodymedia5,23s/hold8,7s.
`prepare --reuse-images` exit0,111planos/499,3s,ready_to_render.

Cola **07a60b02e67c43888e1410e7034c11fc**, requireGPU; preflight NVENCp5
pasado, worker iniciado en mezcla local. Inputs activos congelados. Kitok sigue
render normal/subtitulado,QA,bundle y limpieza. Consultar
`local/stickman_jobs/ESTADO.md` y log delID; si needs_review investigar antes
retry. No esperar render ni repetir proveedores. No publicación. Revisión
audiovisual del operador pendiente. Originales/manifiestos conservados en padre.

## Corrección de marcas Fish

Se conservan JSON/audio originales y se admiten hasta20ms de solapamiento entre
palabras con inicios/finales ordenados; mayores/retrocesos siguen bloqueados.
Caso real15,283ms resuelto. Verificado04/11:169tests focales de audio,ASR,cortes,
planificador,subtítulos y pipeline; revisión independiente sin hallazgos materiales;
docs-check y whitespace. Sin push ni remoto/CI comprobados para esta rama.

## Otras producciones y límites

Cola observada04/11: Jason010 terminado; Art011 needs_review en cierre por
`Preserve the operator LEEME.md first`. No se intervino en esos episodios.
Estilo: stickman como Jason010, gesto/acción y horror contextual; algunas tomas
cercanas de secundarios012 tienen anatomía más llena, limitación registrada.
Música nueva horror_no_attribution muy baja (-34LUFS antes de ducking); fuentes,
licencias y recibos conservados. Ocho archivos en entrega, un parMP4 canónico.
El diagnóstico OAuthHTTP400 del04/11 quedó obsoleto: acceso ampliado
verificado05/11 según la sección YouTube anterior. vidIQ no usado. No se ha medido ahorro de tokens ni equivalencia
de calidad entre modelos.
