# Kitok: contrato para agentes

## Continuidad, Git y documentación

- Lee primero PROJECT_STATUS.md (estado vigente y siguiente paso), después GUIA.md y sólo el código necesario para el encargo. El estado orienta; verifica de nuevo los hechos que vayas a cambiar o afirmar.
- Mantén PROJECT_STATUS.md breve: rama/base, capacidades comprobadas, comandos/pruebas con fecha, trabajo en curso, límites y siguiente paso. No uses este archivo como diario ni copies logs completos.
- En cada unidad terminada actualiza estado, guía y referencias afectadas en el mismo checkpoint. Reescribe afirmaciones obsoletas de documentos vigentes; conserva historia útil en docs/archive/ con fecha y aviso.
- Dentro de Kitok el operador autoriza commits coherentes y push de ramas de trabajo después de verificar cada unidad. Hazlo durante el trabajo, no sólo al final. Comprueba el SHA remoto y el resultado de CI; informa si no se pudieron comprobar.
- Antes de commit/push revisa el índice y las rutas: no incluir .env, estado privado, contenido editorial local, medios, cachés, logs ni cambios ajenos sin revisar.
- No hagas commits vacíos, pushes de estados conocidos rotos ni force-push. Integrar main, desplegar o publicar vídeos requiere intención expresa del operador; la autorización de una de esas acciones no autoriza las otras. Mantén las aprobaciones específicas de gasto significativo.
- Al cerrar o interrumpir trabajo, deja el siguiente paso exacto y los bloqueos reales en PROJECT_STATUS.md y .codex-work/PROJECT_STATE.md. Otros chats no deben asumir que los cambios sin commit están completos.
- No instales skills ni hooks duplicados. El coordinador encarga revisión, recibe feedback, corrige y pide relectura; las comprobaciones deterministas preceden a nuevos agentes.

## Orden y documentación siempre vigentes

- Raíz: sólo README.md, AGENTS.md, GUIA.md, PROJECT_STATUS.md, lanzadores y configuración necesarios. Ejemplos en examples/, herramientas en scripts/, lógica en src/kitok/ y manuales temáticos en docs/. No crear otro prompt/diario/mapa duplicado en raíz.
- Cada cambio de comportamiento revisa sus fuentes: comandos/rutas → GUIA; capacidades/automatización → docs/capabilities.md; montaje → docs/editing.md y ejemplos; cuenta/métricas → guía de integración. Corrige o retira afirmaciones obsoletas en ese mismo checkpoint, incluidos instaladores y ayuda CLI.
- Una fuente principal por tema. La documentación vigente enlaza historia sólo mediante docs/archive/README.md; todo documento archivado lleva aviso de que no es una instrucción actual. No borres datos operativos para limpiar documentación.
- Antes de cerrar, ejecuta make docs-check. Verifica enlaces y ejemplos, pero revisa además la exactitud semántica contra código y runtime; ningún hook garantiza documentación correcta automáticamente.
- Mantén explícita la frontera entre Kitok, agente/editor y operador. No conviertas un piloto o una propuesta en una capacidad general, ni un agente de desarrollo en un servicio autónomo de producción.

## Autonomía técnica y editorial autorizada

- El operador encarga investigar, probar, descartar y terminar mejoras útiles sin pedir aprobación para cada paso local. Elige según calidad audiovisual demostrada, coste, mantenimiento y el equipo de 4 GB VRAM / 8 GB RAM. Conserva los experimentos útiles y sus límites; no instales listas enteras de herramientas.
- Prioriza una muestra real revisada antes de ampliar un episodio. Contrasta con referencias vistas, no sólo con sus títulos. Corrige encuadres, legibilidad, acción y sincronización; una suite verde no demuestra calidad narrativa.
- El agente decide el brief editorial y los hechos con fuentes; los componentes deterministas seleccionan recursos, compilan, mezclan y renderizan. Evita llamadas LLM por plano, fotograma o reintento de operaciones ya resueltas.
- Antes de otra síntesis busca audio Fish y alineación existentes. Las APIs ya configuradas están autorizadas cuando hacen falta; no repitas solicitudes ambiguas ni contrates nuevos servicios de pago. Los créditos de investigación vidIQ y el gasto significativo requieren aprobación específica.
- Comprueba identidad, contexto y licencia antes de usar recursos. Stock y reconstrucciones se declaran ilustrativos; no se presentan como imágenes del caso. Conserva autor, URL, licencia, cambios y obligaciones ShareAlike. Content ID desconocido no significa libre de reclamaciones.
- YouTube se conecta por lectura oficial con consentimiento del titular. No amplíes scopes para evitar un paso de autenticación; no publiques, modifiques el canal ni fusiones a main con esta autorización general.

## Antes de empezar

- Lee GUIA.md: es el manual de operación y la fuente de la página «Cómo usarlo».
- Inspecciona git status y los archivos afectados. Conserva el trabajo previo y los datos del operador.
- Verifica el comportamiento con código, comandos y resultados actuales. Marca lo no verificado.
- Para cambios sustanciales usa plan-work; antes de afirmar que funcionan usa verify-before-completion. Revisa independientemente los límites importantes.

## Mapa y fuentes de verdad

- frontend/: React + TypeScript + Vite. La interfaz diaria ofrece Short y Vídeo largo; el resto queda en opciones avanzadas.
- src/kitok/api/: transporte FastAPI local; schemas.py define las peticiones. Reutiliza servicios Python, no implementes reglas de negocio en React.
- src/kitok/application.py: borradores y trabajos de shorts; un único ejecutor.
- src/kitok/pipeline.py y generation.py: generación de shorts, validación y READY.
- src/kitok/editing/: planes por escena, gráficos y QA; editorial_studio.py sirve comparaciones locales con audio aprobado, sin proveedores.
- src/kitok/longform_studio.py: borradores/trabajos largos separados; comparte el ejecutor de shorts.
- longform.py: entrada CLI de largos; la lógica compartida vive en src/kitok/longform/cli.py. Los JSON del estudio son compatibles con este CLI.
- src/kitok/rendering/, media/, providers/, stock/: motor largo nativo y adquisición de stock.
- control_panel.py y publisher.py: revisión, confirmación, idempotencia y reconciliación de publicación; buffer_client.py y cloudinary_host.py: transporte externo.
- content_queue.json y state/state.json: datos activos de shorts, no fixtures.
- content/longform/studio/ y state/longform/: borradores y trabajos largos del operador.
- presets/generation_profiles.json: catálogo de voces/estilos. .env: configuración privada, nunca mostrar ni versionar.
- README.md y docs/README.md: entradas vigentes; docs/capabilities.md: reutilización y reparto Kitok/agente/operador. docs/archive/: historia, no contratos actuales.
- docs/development.md: protocolo del coordinador, revisión y gates. docs/roadmap.md: trabajo pendiente; diseños sustituidos sólo en docs/archive/.

## Invariantes del producto

- Mantén la interfaz sencilla: escribir → comprobar sin generar → generar/revisar → descargar o programar.
- Guardar borradores y hacer previews no debe generar voz, contactar proveedores ni publicar.
- La interfaz básica usa el guion aportado. Los agentes pueden preparar borradores investigados en encargos editoriales autorizados; no inventes hechos ni actives voz o publicación al guardar. No añadas opciones que el usuario no necesita para la decisión.
- El uso diario guarda los vídeos localmente (outputs/ready y outputs/longform); no requiere Google Drive. No reactives copias a una unidad externa por defecto. Conserva las rutas históricas.
- Generación y publicación son acciones separadas. Una fecha local no prueba que haya un post en Buffer.
- Buffer requiere revisión y confirmación explícitas. Conserva los IDs remotos y los resultados ambiguos; no reintentes automáticamente mutaciones de publicación ni borres estado para forzarlas.
- Los largos están fuera de la cola/calendario/publicador de shorts. No los introduzcas sin adaptar validación y contrato de publicación.
- Nuevos largos: native predeterminado en CLI y estudio, todavía experimental. MPT sólo se conserva para --renderer mpt --resume TASK_ID histórico; nunca envíes una tarea nueva ni conviertas una histórica silenciosamente.
- Shorts Pexels/locales, CLI y estudio usan generación nativa; conserva IDs y registros MPT históricos sin enviarlos automáticamente de nuevo. La integración completa y los límites verificados están en PROJECT_STATUS.md; no afirmes independencia total sin comprobar CLI/UI y recorridos reales.
- No reinicies trabajos de pago al arrancar. En largos, fallos/interrupciones requieren revisión; Fish puede haber consumido saldo.
- Mantén el bloqueo de generación por ID durante todo el trabajo. CLI y estudio usan longform-ID en state/jobs/. No uses sólo un botón deshabilitado como protección contra duplicados.
- HTTP no acepta rutas arbitrarias para guiones, configuración o descarga. Usa IDs validados y directorios controlados.
- Guarda el estado de forma atómica; no sobrescribas salidas terminadas como efecto de una navegación, preview o reintento.
- Los servidores se mantienen en 127.0.0.1. No publiques ni despliegues esta aplicación local sin intención explícita del operador.

## Verificación y entrega

Desde la raíz:

```bash
make docs-check
make studio-check
make verify
# Si afecta flujos de UI/API, con Chromium instalado:
make verify-browser
```

- El coordinador gestiona encargos, hallazgos, correcciones y relectura directamente; el operador no debe copiar mensajes entre agentes. Sigue docs/development.md.
- Para cambios pequeños minimiza agentes/contexto. En límites críticos usa revisión independiente de corrección, adversarial y evaluación; resuelve P0/P1 y verifica el resultado corregido.
- Ejecuta primero las pruebas del módulo afectado. Usa tmp_path/data_root y proveedores simulados para no tocar contenido ni consumir servicios reales.
- Los tests bloquean red externa. Las pruebas de UI/transporte no demuestran una generación real de Fish/Pexels/MPT ni una publicación real en Buffer.
- Las pruebas de navegador deben usar un workspace temporal y mocks para operaciones externas; no abras una cola real con acciones automáticas.
- Cuando cambien comandos, modos, archivos, límites o pasos de usuario, actualiza GUIA.md en el mismo cambio. El frontend la lee directamente.
- Mantén la documentación técnica alineada cuando afecte a su contenido. No elimines secciones históricas ni datos de trabajo sin revisar su uso.
- Si existe .codex-work/, mantén allí PLAN.md, PROJECT_STATE.md, DECISIONS.md y QA_MATRIX.md como estado privado. No lo incluyas en entregables.
- Haz commits locales coherentes y verificados; separa cambios previos del operador. No hagas push, PR, publicación ni despliegue sin intención explícita.
- En la entrega indica comandos de arranque, pruebas realizadas y límites no verificados.
