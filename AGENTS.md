# Kitok: contrato para agentes

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
- src/kitok/longform_studio.py: borradores/trabajos largos separados; comparte el ejecutor de shorts.
- longform.py: configuración/CLI de largos. Los JSON del estudio son compatibles con este CLI.
- src/kitok/rendering/, media/, providers/, stock/: motor largo nativo y adquisición de stock.
- control_panel.py y publisher.py: revisión, confirmación, idempotencia y reconciliación de publicación; buffer_client.py y cloudinary_host.py: transporte externo.
- content_queue.json y state/state.json: datos activos de shorts, no fixtures.
- content/longform/studio/ y state/longform/: borradores y trabajos largos del operador.
- presets/generation_profiles.json: catálogo de voces/estilos. .env: configuración privada, nunca mostrar ni versionar.
- PROJECT_GUIDE.md y README.md: referencias técnicas con partes históricas; contrasta con el código.

## Invariantes del producto

- Mantén la interfaz sencilla: escribir → comprobar sin generar → generar/revisar → descargar o programar.
- Guardar borradores y hacer previews no debe generar voz, contactar proveedores ni publicar.
- No generes guiones automáticamente ni añadas opciones que el usuario no necesita para la decisión.
- Generación y publicación son acciones separadas. Una fecha local no prueba que haya un post en Buffer.
- Buffer requiere revisión y confirmación explícitas. Conserva los IDs remotos y los resultados ambiguos; no reintentes automáticamente mutaciones de publicación ni borres estado para forzarlas.
- Los largos están fuera de la cola/calendario/publicador de shorts. No los introduzcas sin adaptar validación y contrato de publicación.
- En largos, la interfaz elige native de forma explícita y lo identifica como experimental. El CLI conserva mpt por defecto. No cambies silenciosamente estos valores.
- La migración MPT sigue parcial: shorts Pexels y largos MPT aún lo necesitan. No borres MPT ni afirmes independencia total sin migrar y verificar estos recorridos.
- No reinicies trabajos de pago al arrancar. En largos, fallos/interrupciones requieren revisión; Fish puede haber consumido saldo.
- Mantén el bloqueo de generación por ID durante todo el trabajo. CLI y estudio usan longform-ID en state/jobs/. No uses sólo un botón deshabilitado como protección contra duplicados.
- HTTP no acepta rutas arbitrarias para guiones, configuración o descarga. Usa IDs validados y directorios controlados.
- Guarda el estado de forma atómica; no sobrescribas salidas terminadas como efecto de una navegación, preview o reintento.
- Los servidores se mantienen en 127.0.0.1. No publiques ni despliegues esta aplicación local sin intención explícita del operador.

## Verificación y entrega

Desde la raíz:

```bash
make studio-check
.venv/bin/python -m pytest -q
npm --prefix frontend test
npm --prefix frontend run build
git diff --check
```

- Ejecuta primero las pruebas del módulo afectado. Usa tmp_path/data_root y proveedores simulados para no tocar contenido ni consumir servicios reales.
- Los tests bloquean red externa. Las pruebas de UI/transporte no demuestran una generación real de Fish/Pexels/MPT ni una publicación real en Buffer.
- Las pruebas de navegador deben usar un workspace temporal y mocks para operaciones externas; no abras una cola real con acciones automáticas.
- Cuando cambien comandos, modos, archivos, límites o pasos de usuario, actualiza GUIA.md en el mismo cambio. El frontend la lee directamente.
- Mantén la documentación técnica alineada cuando afecte a su contenido. No elimines secciones históricas ni datos de trabajo sin revisar su uso.
- Si existe .codex-work/, mantén allí PLAN.md, PROJECT_STATE.md, DECISIONS.md y QA_MATRIX.md como estado privado. No lo incluyas en entregables.
- Haz commits locales coherentes y verificados; separa cambios previos del operador. No hagas push, PR, publicación ni despliegue sin intención explícita.
- En la entrega indica comandos de arranque, pruebas realizadas y límites no verificados.
