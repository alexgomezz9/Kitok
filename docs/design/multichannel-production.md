# Propuesta: Kitok multicanal y director de producción

Estado: diseño para fases futuras; no añade configuración, endpoints, agentes ni automatismos al producto actual. La operación vigente sigue en [GUIA.md](../../GUIA.md). El [roadmap](../roadmap.md) delimita las entregas y sus pruebas.

## Punto de partida y límites

Kitok ya separa transporte FastAPI, interfaz React, servicios Python, generación, proveedores y publicación. El motor largo nativo reúne Fish, Pexels y FFmpeg; continúa experimental. Los shorts Pexels/locales y los nuevos largos usan generación nativa; el CLI largo selecciona native por defecto. MPT se conserva sólo para diagnóstico y recuperación explícita de tareas antiguas. Esta propuesta multicanal no altera los archivos anteriores ni la confirmación de Buffer. El estado comprobado está en PROJECT_STATUS.md.

Hoy la selección de stock largo usa búsquedas globales; no existe montaje semántico por frase. El arranque no reanuda trabajos de pago, native no recupera etapas y algunos fallos de transporte Fish pueden repetir solicitudes. Antes de dirigir producción sin supervisión hay que resolver esa recuperación. El objetivo es un director editorial sobre servicios comprobables, manteniendo Python y FFmpeg como ejecutores deterministas y salida local sin Google Drive.

## Perfil de canal y compatibilidad

Proponer un catálogo de perfiles inmutables por revisión. Cada perfil tendrá identidad estable, nombre visible, idioma/locale, temática, criterios de fuentes, estilo narrativo, voz por rol y formato, velocidad, duración objetivo y límites, relación de aspecto, resolución, política musical, subtítulos, gráficos, miniaturas y destinos de publicación. Los destinos serán referencias a conexiones privadas; nunca tokens. El catálogo de voces existente seguirá resolviendo identificadores: no se duplicarán voces ni referencias de proveedor en cada pantalla.

Ejemplo ilustrativo de contrato futuro, no un archivo aceptado actualmente:

```json
{
  "schema_version": 1,
  "channel_id": "loose-thread",
  "revision": 1,
  "language": "en-US",
  "editorial": {"topic": "stories", "style": "documentary", "sources_required": true},
  "voice_profile": "loose_thread",
  "formats": {
    "long": {"aspect": "16:9", "target_seconds": 600, "renderer": "native"}
  },
  "music": {"enabled": false, "volume": 0.06},
  "subtitles": {"mode": "selective"},
  "thumbnail": {"template_id": "documentary-v1"},
  "publication_targets": [{"connection_ref": "youtube-loose-thread"}]
}
```

El ejemplo no activa esas capacidades: subtítulos selectivos y plantillas editoriales de miniatura requieren implementación. Las reglas Loose Thread sólo pertenecerán a su perfil. No habrá una duración, idioma, voz, música o estilo global que se imponga a todos los canales.

La migración distinguirá canales editoriales de compatibilidad. Los contenidos antiguos sin canal conservarán un adaptador `legacy` que traduzca exactamente sus campos actuales, incluyendo música 0.06, restricciones Rick/random e idioma MPT heredado donde corresponda. No se asignará toda la cola a Loose Thread por inferencia. El operador podrá clasificarla después mediante una previsualización del cambio. Los IDs, rutas de READY, metadatos, posts remotos y archivos previos permanecerán intactos; no se regenerarán al abrirlos. Una nueva producción congelará perfil resuelto, versión del esquema, parámetros, semilla y versión del motor. Editar el perfil creará otra revisión; no alterará un trabajo en curso.

## Componentes y datos

El frontend tendrá cuatro momentos: canal e ideas, elección y guion, producción y revisión, entrega y aprobación. Sus vistas no implementarán presupuestos, estados ni reglas editoriales. El CLI y futuras herramientas del director invocarán los mismos servicios Python. El estudio sencillo actual seguirá disponible sin exigir investigación previa.

Los contratos propuestos son:

| Objeto | Contenido mínimo y límite |
|---|---|
| ResearchBrief | Canal/revisión, pregunta, ventana temporal, fuentes permitidas y presupuesto de investigación. |
| Candidate | Historia, evidencia de demanda, ángulo, títulos, concepto de miniatura, fuentes y límites de verificación. |
| Selection | Candidato elegido, actor, fecha y revisión; no autoriza publicación. |
| ScriptRevision | Texto, idioma, fuentes por afirmación, pronunciaciones y cambios editoriales. |
| EditPlan | Escenas, fragmentos de narración, consultas Pexels, overlays, transiciones y restricciones temporales. |
| ProductionJob | Entradas congeladas, autorización de ejecución, etapas, operaciones externas y resultados. |
| Artifact | Tipo, hash, tamaño, ubicación local controlada, dependencias, parámetros y procedencia. |
| QAReport / CorrectionPlan | Evidencia, severidad, regla aplicada y subgrafo que debe recalcularse. |
| DeliveryBundle / PublicationApproval | Archivos y metadatos exactos; aprobación posterior ligada a sus hashes y destino. |

Usar SQLite mediante la biblioteca estándar para trabajos nuevos, operaciones, artefactos y eventos permite transacciones y restricciones únicas sin otro servidor. Es una decisión propuesta, pendiente de un prototipo de recuperación. No se sustituirá de golpe `state/state.json` ni el historial Buffer. Los adaptadores existentes seguirán leyéndolos; se definirá una sola autoridad por trabajo para evitar escritura doble. Un importador futuro será explícito, reversible y comprobará conteos e identidades antes de confirmar. SQLite, manifest y vídeos quedan locales, excluidos de Git.

## Operaciones de servicio propuestas

Estos nombres describen servicios futuros, no rutas HTTP ni comandos actuales.
Todas las mutaciones reciben actor, request_id y revisión esperada; un conflicto
devuelve el estado vigente sin ejecutar trabajo. La misma petición con iguales
entradas devuelve el resultado registrado; reutilizar su ID con entradas distintas
se rechaza. La validación precede a cualquier despacho.

| Operación | Entrada y precondición | Resultado persistido |
|---|---|---|
| research | Canal/revisión y ResearchBrief, herramientas autorizadas | ID de investigación y candidatos versionados con fuentes |
| select_candidate | ID/revisión del candidato y proyecto en awaiting_selection | Selection y nueva revisión; no paga ni publica |
| save_script_plan | Texto, fuentes y EditPlan; revisión de Selection | ScriptRevision/plan validados, diferencias y requisitos pendientes |
| start_production | Revisión congelada, aprobación de gasto/proveedores, request_id | ProductionJob/intent reservado y cursor; duplicado no despacha otra vez |
| wait_for_job | job_id y último cursor; lectura autorizada | Eventos posteriores y estado terminal, suscripción recuperable |
| request_repair | Hash del QA/master y CorrectionPlan autorizado | Revisión y subgrafo a ejecutar; coste nuevo exige aprobación aparte |
| prepare_delivery | Artefactos confirmados y QA aceptado | Bundle con hashes, archivos y metadatos versionados |
| approve_publication | Bundle/revisión, destino, fecha, visibilidad y declaraciones | Aprobación revocable ligada a esos valores; no ejecuta el envío |
| execute_publication | Aprobación vigente y request_id | Intento persistido y resultado/unknown; reconciliación antes de repetir |

Las herramientas externas de investigación, páginas, transcripciones y resultados
vidIQ son datos no confiables. Sus instrucciones no pueden ampliar herramientas,
gasto ni autorizaciones. El director extraerá evidencia a campos limitados,
mantendrá procedencia y aplicará las mismas invariantes aunque una fuente pida
ejecutar código, revelar credenciales o publicar.

## Dirección editorial y montaje

El director investigará sólo con herramientas autorizadas. Registrará URL, fecha de consulta, periodo medido y fragmento de evidencia necesario; distinguirá dato observado, estimación e interpretación. Un outlier necesita población comparable y periodo definido; un título atractivo no prueba demanda. Las métricas privadas llegarían por las APIs oficiales de YouTube; vidIQ sería una entrada opcional conectada y autorizada. La ausencia de acceso se mostrará como limitación, sin inventar estadísticas.

Presentará entre tres y cinco candidatos con historia, razones, incertidumbres y conceptos de packaging. Se detendrá en `awaiting_selection`; no elegirá por silencio. Tras selección, el flujo futuro de guion requerirá habilitación explícita del operador y revisión de afirmaciones. El producto actual sigue aceptando texto escrito por el usuario. La selección editorial tampoco autoriza llamadas pagadas: antes de ejecutarlas se guardarán proveedores permitidos, límite de gasto configurado y confirmación de producción. Si un proveedor no ofrece coste previo fiable, se indicará y el sistema no prometerá un importe cerrado.

El `EditPlan` separará semántica y tiempo. Reutilizará `VisualSection` de `src/kitok/longform/models.py`, que ya contiene sección, palabras clave y tiempos opcionales. No se creará otro modelo paralelo con esos mismos campos. Los tiempos definitivos se validarán después de medir el audio; alinear palabras requeriría un mecanismo específico, todavía ausente. No se presentará la ponderación actual por caracteres como alineación real.

Pexels será la fuente principal. Cada escena propondrá búsquedas concretas y alternativas; el selector determinista aplicará orientación, resolución, duración y diversidad, conservando asset ID y procedencia. El plano elegido no se considerará evidencia histórica de lo narrado. Los gráficos sencillos procederán de plantillas versionadas de SVG/texto y FFmpeg: cifras con fuente, comparaciones y mapas simples cuando haya datos suficientes. Subtítulos selectivos, texto cinético y transiciones tendrán límites por perfil para evitar sobrecarga. La miniatura editorial será un artefacto propio con zonas de texto y pruebas de legibilidad; la captura actual de previsualización no cumple ese contrato.

## Ejecución, espera y reinicios

Estados propuestos: `draft → researched → awaiting_selection → script_review → ready_to_produce → running → awaiting_qa → repair_required | delivered`. Cualquier etapa puede quedar `failed`, `interrupted` o `needs_reconciliation`, con motivo registrado. Publicación usa un ciclo separado. No se reutilizará `delivered` como prueba de envío remoto.

Una transacción reservará un trabajo, grabará un evento y devolverá su ID antes de despachar ejecución. El worker mantendrá un lease renovable y checkpoints duraderos. Al reiniciar, un lease vencido obliga a inspeccionar operaciones y artefactos; nunca a repetir toda la producción. Las etapas puramente locales podrán continuar tras verificar sus entradas. Los eventos llevarán secuencia por trabajo; la interfaz podrá recuperar eventos desde el último cursor y suscribirse a una conexión de eventos del servidor. El director se suspenderá hasta un evento terminal o una notificación de reanudación; no mantendrá un agente consultando estado continuamente. La recuperación de una conexión cerrada consultará el cursor una vez y volverá a suscribirse. Este transporte aún no existe y no se presupone una herramienta nativa de Codex para él.

Cada operación pagada guardará primero una intención con clave única derivada del trabajo, etapa y entradas normalizadas: texto exacto, voz, modelo, idioma, parámetros y revisión. Las credenciales no forman parte del hash ni del registro. Estados: `prepared`, `submitted`, `succeeded`, `failed_before_submit`, `unknown`, `reconciled`. Timeout o caída tras enviar deja `unknown`; no inicia otro POST automáticamente. Sólo una respuesta concluyente del proveedor o reconciliación documentada permite continuar. Si no existe consulta remota útil, la interfaz requiere una decisión humana para un nuevo intento y advierte del posible cobro previo. Una restricción local evita doble despacho conocido, pero no garantiza exactamente una ejecución remota.

El audio confirmado se registra y reutiliza por hash; diálogos tendrán un artefacto por turno para recuperar únicamente los pendientes. También se conservarán selección de stock, descargas, escenas renderizadas y mezcla. Antes de habilitar concurrencia entre canales, se probarán locks entre procesos para trabajo y recurso, temporales únicos por descarga y commit atómico de caché. Inicialmente habrá un solo trabajo de generación; límites de GPU, FFmpeg y proveedor serán explícitos. Borrar estado o cambiar de ID no será un mecanismo de recuperación.

## QA y reparación por dependencias

El grafo será aproximadamente: guion/voz → audio; plan/stock → escenas; audio/escenas/gráficos → master; master → QA y derivados; master/packaging → bundle. Hashes de entradas y parámetros identificarán qué nodos quedan invalidados. Cambiar un overlay recalcula esa escena, composición y QA; no llama a Fish. Cambiar el guion invalida el audio afectado y las escenas dependientes del tiempo. El montaje puede reutilizar audio coherente de una sola llamada sin volver a sintetizarlo por escenas.

QA tendrá dos capas. Las pruebas deterministas comprobarán decodificación completa, streams, geometría, duración, sincronía con narración medida, silencios, clipping, loudness, fotogramas negros/congelados, huecos y continuidad de timestamps. Los umbrales y excepciones serán versionados por formato; no se universalizará el requisito del smoke actual de 60–90 segundos. Un manifiesto guardará valores medidos y herramientas. La revisión audiovisual usará muestras por escena, transiciones, inicio y final, más reproducción del resultado cuando corresponda. Los detectores son evidencia de posibles fallos, no pruebas de veracidad narrativa ni garantías de calidad.

El supervisor recibirá un informe compacto con tiempos y archivos controlados. Un hallazgo tendrá severidad, evidencia, regla y reparación propuesta. La primera versión permitirá una ronda automática de reparaciones locales autorizadas, sin gasto adicional; superar ese límite o necesitar nueva voz devuelve control al usuario. Se verificará de nuevo el subgrafo afectado y las propiedades globales del master. El resultado anterior no se sobrescribirá hasta validar y registrar el nuevo.

## Entrega y publicación

La entrega contendrá MP4, miniatura(s), título/descripción, idioma, procedencia de medios, fuentes editoriales, informe QA y manifest con hashes. Preparará archivos temporales, verificará integridad y registrará el bundle completo antes de exponerlo como terminado. Un fallo al guardar un sidecar no debe forzar otra síntesis ni perder un MP4 válido.

Publicar será otra orden con destino, fecha, visibilidad, declaraciones y hashes aprobados. Cambiar cualquiera de esos datos invalida la aprobación. El camino Buffer actual conserva su revisión y reconciliación; los largos no entran en él por esta propuesta. La conexión YouTube futura tendrá permisos y contratos propios, descritos en [youtube.md](youtube.md). Nunca se derivará consentimiento de haber generado, elegido una fecha o entregado un bundle. Esta separación permite obtener producción útil antes de implementar cualquier integración de publicación nueva.
