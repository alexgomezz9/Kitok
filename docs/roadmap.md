# Roadmap verificable

Estado: propuesta, sin director ni YouTube implementados. Riesgos en [la auditoría](audit/2026-10-15.md); contratos en [multicanal y producción](design/multichannel-production.md).

## 0. Base reproducible y operación sencilla

Mantener estudio Short/Largo, guía única, salida local, datos privados fuera de Git y código completo. Usar `make verify` y `make verify-browser`. No borrar MPT ni modificar el historial editorial.

Aceptación: copia Git sin `.env`, cola ni vídeos privados pasa las verificaciones; reconoce ausencia de claves sin generarlas; un dry-run no consume proveedores. Las pruebas con mocks no prueban generación real ni autonomía audiovisual.

## 1. Recuperación segura de operaciones de pago — prioridad máxima

Implementar registro duradero de intención/resultado y reutilización de audio, empezando por una síntesis Fish aislada. Eliminar reintentos automáticos de POST ambiguos. Integrar después diálogos y native; conservar MPT task IDs y reconciliación existentes. Persistir artefactos y checkpoints antes de otro despacho. Mantener un solo ejecutor.

Aceptación offline: fallos simulados antes de enviar, después de enviar, tras escribir audio y antes de confirmar estado; reinicio en cada punto; dos procesos intentando el mismo ID. Un resultado incierto queda visible y produce cero POST adicionales al reiniciar, abrir UI o repetir una consulta. Un audio confirmado evita nueva síntesis. Una reparación local no toca proveedores. Probar también disco lleno, JSON/registro corrupto y fallo de manifest sin perder resultados completos.

Validación real separada: sólo con autorización expresa, texto mínimo, límite de gasto y una llamada observada. Si el proveedor no permite reconciliar una solicitud incierta, documentar la intervención manual; no simular una garantía de cobro exactamente una vez.

## 2. Canales versionados y compatibilidad

Añadir esquema validado de perfil, selector sencillo y snapshot por trabajo. Extraer reglas Loose Thread a su perfil y mantener adaptador legacy para contenido sin canal. Compartir renderizador, catálogo de voces y servicios; no duplicar el pipeline por canal.

Aceptación: dos perfiles de prueba con distintos idiomas/formatos resuelven configuraciones independientes; editar uno no cambia trabajos ya creados ni el otro canal. Cola histórica, IDs, rutas y referencias Buffer conservan sus valores, incluida música 0.06. La migración ofrece preview y rollback; no genera ni publica. Los JSON anteriores y ambos defaults de renderer siguen funcionando. Verificar separación de configuraciones con pruebas de CLI y API.

## 3. Director editorial y espera duradera

Implementar primero un recorrido sin proveedores pagados: elegir canal, guardar investigación con fuentes, presentar candidatos, esperar selección, revisar guion y producir un `EditPlan` validado. La generación automática de guion será una capacidad futura habilitada expresamente. Reutilizar `VisualSection`. Añadir eventos persistidos y suscripción recuperable para UI/director; reservar el worker existente para ejecutar, sin un agente por etapa.

Aceptación: ninguna selección por silencio; cancelar investigación no produce voz; un candidato sin evidencia identifica sus lagunas. Reiniciar mantiene selección, revisiones y cursor; el consumidor recupera los eventos perdidos sin duplicar trabajo. Contratos de investigación, guion y ejecución se prueban con fixtures y una integración local completa. Probar también instrucciones maliciosas en páginas/transcripciones: no amplían herramientas, gasto ni autorizaciones. No se necesita vidIQ para operar; su falta de conexión se declara.

## 4. Montaje semántico, QA y reparación localizada

Introducir escenas temporizadas tras medir audio, consultas Pexels por sección, overlays y transiciones mediante plantillas de código. Añadir un tipo de gráfico y subtítulos selectivos antes de ampliar opciones. Construir informes técnicos y hojas de contacto; después, una ronda acotada de reparación local y bundle íntegro con miniatura editorial.

Aceptación: fixtures audiovisuales con negro, silencio, clipping, duración errónea y escena ausente producen hallazgos con evidencia; una muestra válida no dispara bloqueos injustificados. Cambiar texto gráfico recompone sólo nodos dependientes y hace cero síntesis. Alineación desconocida se muestra como tal. Antes de paralelizar: locks de caché entre procesos, temporales únicos, recuperación de descargas y límites de recursos probados. Una comparación real autorizada evaluará ritmo y calidad; los tests no sustituyen esa revisión.

## 5. YouTube oficial en lectura

Aplicar [el diseño YouTube](design/youtube.md): OAuth por canal, comprobación de identidad/permisos, ingestión idempotente Data/Analytics/Reporting, informes reach a1 y dashboard histórico local. Esta fase exige aprobación antes de crear credenciales o solicitar permisos. No incorporar upload aún.

Aceptación offline: CSV y respuestas versionadas prueban backfill, duplicados, periodos, expiración, revocación, borrado y aislamiento de canales. Con autorización real, demostrar identidad y acceso a un canal; comprobar disponibilidad y unidades de los informes antes de mostrar CTR. Datos ausentes se muestran como pendientes, nunca como cero. La retención sigue las políticas documentadas y se revalida antes de implementar.

## 6. Publicación separada y expansión controlada

Sólo después de una entrega fiable, diseñar un adaptador YouTube con aprobación ligada al bundle, scopes mínimos y reconciliación de resultados ambiguos. No alterar Buffer ni incorporar largos a su calendario sin un contrato específico.

Aceptación: modificar MP4, metadatos, destino o fecha invalida aprobación; reiniciar no publica; timeout de mutación no dispara otra. Las pruebas reales de subida requieren autorización independiente y comprobación del resultado remoto. Paralelismo multicanal sólo tras superar las pruebas de recursos y recuperación anteriores.

## Carril independiente: terminar la migración MPT

Inventariar tareas MPT pendientes y migrar primero un short Pexels completo a servicios nativos reutilizados; después diálogo Pexels y equivalencia de largos. Comparar audio, duración, subtítulos, validación, stock, recuperación y rendimiento con fixtures y generaciones reales autorizadas. Unificar contratos antes de cambiar defaults.

MPT se podrá retirar cuando todos los recorridos usados tengan sustituto verificado, no queden tareas pendientes sin decisión y la guía refleje la transición. Mantener la instalación y los IDs históricos hasta entonces. Este carril no bloquea diseñar canales, pero sí cualquier afirmación de independencia total de MPT.
