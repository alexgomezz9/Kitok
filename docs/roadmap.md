# Roadmap verificable

Estado: roadmap pendiente; base nativa, C editorial, compilador de briefs y CLI YouTube de lectura implementados; sin director general ni autorización Google real. Estado comprobado en [PROJECT_STATUS.md](../PROJECT_STATUS.md). Riesgos en [la auditoría](audit/2026-10-15.md); contratos en [multicanal y producción](design/multichannel-production.md).

## 0. Base reproducible y operación sencilla

Mantener estudio Short/Largo, guía única, salida local, datos privados fuera de Git y código completo. Usar `make verify` y `make verify-browser`. Conservar el historial y los medios originales; MPT sólo permanece para recuperar tareas antiguas.

Aceptación: copia Git sin `.env`, cola ni vídeos privados pasa las verificaciones; reconoce ausencia de claves sin generarlas; un dry-run no consume proveedores. Las pruebas con mocks no prueban generación real ni autonomía audiovisual.

## 1. Recuperación segura de operaciones de pago — prioridad máxima

Implementado: registro Fish por payload, caché validada/compartida entre modos, bloqueo de resultados ambiguos y cero retry de POST de voz. Integrado en nativo y diálogos, con regresiones offline y revisión independiente. Pendiente: ampliar reconciliación operativa de casos ambiguos que el proveedor no permite consultar; conservar IDs históricos y un solo ejecutor.

Aceptación offline: fallos simulados antes de enviar, después de enviar, tras escribir audio y antes de confirmar estado; reinicio en cada punto; dos procesos intentando el mismo ID. Un resultado incierto queda visible y produce cero POST adicionales al reiniciar, abrir UI o repetir una consulta. Un audio confirmado evita nueva síntesis. Una reparación local no toca proveedores. Probar también disco lleno, JSON/registro corrupto y fallo de manifest sin perder resultados completos.

Validación real separada: sólo con autorización expresa, texto mínimo, límite de gasto y una llamada observada. Si el proveedor no permite reconciliar una solicitud incierta, documentar la intervención manual; no simular una garantía de cobro exactamente una vez.

## 2. Canales versionados y compatibilidad

Añadir esquema validado de perfil, selector sencillo y snapshot por trabajo. Extraer reglas Loose Thread a su perfil y mantener adaptador legacy para contenido sin canal. Compartir renderizador, catálogo de voces y servicios; no duplicar el pipeline por canal.

Aceptación: dos perfiles de prueba con distintos idiomas/formatos resuelven configuraciones independientes; editar uno no cambia trabajos ya creados ni el otro canal. Cola histórica, IDs, rutas y referencias Buffer conservan sus valores, incluida música 0.06. La migración ofrece preview y rollback; no genera ni publica. Los JSON históricos siguen siendo legibles; la generación nueva usa native y MPT sólo admite recuperación explícita. Verificar separación de configuraciones con pruebas de CLI y API.

## 3. Director editorial y espera duradera

Implementado: compilación determinista de un brief explícito a EditorialPlan, con recursos/licencias/SHA y faltantes que bloquean. No hay investigación ni guion autónomos.

Pendiente el recorrido completo sin proveedores pagados: elegir canal, guardar investigación con fuentes, presentar candidatos, esperar selección, revisar guion y producir un `EditPlan` validado. La generación automática de guion será una capacidad futura habilitada expresamente. Reutilizar `VisualSection`. Añadir eventos persistidos y suscripción recuperable para UI/director; reservar el worker existente para ejecutar, sin un agente por etapa.

Aceptación: ninguna selección por silencio; cancelar investigación no produce voz; un candidato sin evidencia identifica sus lagunas. Reiniciar mantiene selección, revisiones y cursor; el consumidor recupera los eventos perdidos sin duplicar trabajo. Contratos de investigación, guion y ejecución se prueban con fixtures y una integración local completa. Probar también instrucciones maliciosas en páginas/transcripciones: no amplían herramientas, gasto ni autorizaciones. No se necesita vidIQ para operar; su falta de conexión se declara.

## 4. Montaje semántico, QA y reparación localizada

Implementado: montaje básico por secciones y planes explícitos por escena, tres gráficos reutilizables, render incremental, informes y contactos, CLI/Montaje y A/B UltimateBet76s corregido tras revisión visual. C añade escenas 3D, foto licenciada, biblioteca Commons/Pexels, música con ducking y preparación desde brief explícito. El brief requiere decisiones editoriales. Pendiente: selección mejor de recursos específicos, QA perceptual/semántico y paquete editorial con miniaturas. No se ha reeditado el episodio completo.

Aceptación: fixtures audiovisuales con negro, silencio, clipping, duración errónea y escena ausente producen hallazgos con evidencia; una muestra válida no dispara bloqueos injustificados. Cambiar texto gráfico recompone sólo nodos dependientes y hace cero síntesis. Alineación desconocida se muestra como tal. Antes de paralelizar: locks de caché entre procesos, temporales únicos, recuperación de descargas y límites de recursos probados. Una comparación real autorizada evaluará ritmo y calidad; los tests no sustituyen esa revisión.

## 5. YouTube oficial en lectura

Implementado: [CLI oficial de lectura](integrations/youtube-readonly.md), OAuth Desktop PKCE, identidad, catálogo, consultas Analytics y enumeración Reporting. Consentimiento real pendiente.

Pendiente del [diseño completo](design/youtube.md): ingestión CSV reach a1, CTR, dashboard histórico y retención/purga automática conforme a políticas. El operador debe crear su cliente Desktop y consentir; no incorporar upload.

Aceptación offline: CSV y respuestas versionadas prueban backfill, duplicados, periodos, expiración, revocación, borrado y aislamiento de canales. Con autorización real, demostrar identidad y acceso a un canal; comprobar disponibilidad y unidades de los informes antes de mostrar CTR. Datos ausentes se muestran como pendientes, nunca como cero. La retención sigue las políticas documentadas y se revalida antes de implementar.

## 6. Publicación separada y expansión controlada

Sólo después de una entrega fiable, diseñar un adaptador YouTube con aprobación ligada al bundle, scopes mínimos y reconciliación de resultados ambiguos. No alterar Buffer ni incorporar largos a su calendario sin un contrato específico.

Aceptación: modificar MP4, metadatos, destino o fecha invalida aprobación; reiniciar no publica; timeout de mutación no dispara otra. Las pruebas reales de subida requieren autorización independiente y comprobación del resultado remoto. Paralelismo multicanal sólo tras superar las pruebas de recursos y recuperación anteriores.

## Cierre de compatibilidad MPT

Nuevos shorts locales/Pexels y largos usan generación nativa. CLI largo y estudio
ya seleccionan native; el CLI permite únicamente recuperar MPT con --resume.
Las tareas antiguas no se convierten ni reenvían y el guard bajo lock impide
consumir otra voz sobre un marcador MPT pendiente.

Pendiente operativo: inventariar con el operador las tareas/medios que quiera
recuperar antes de desinstalar MPT. No se borra su instalación automáticamente.
Los tests de shorts usan FFmpeg real y proveedores simulados; una generación
nueva de cada estilo contra APIs reales sigue sin comprobarse. La reedición
UltimateBet reutiliza audio/stock reales y no equivale a esa matriz completa.
