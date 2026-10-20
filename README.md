# Kitok

Estudio local para generar y revisar shorts y vídeos largos, con publicación de
shorts opcional mediante Cloudinary + Buffer. Python y FFmpeg mantienen las reglas
de ejecución; React/FastAPI ofrecen el recorrido guiado.

## Empezar

Requisitos: Python 3.11+, Node 22.12+ o 24 y FFmpeg/ffprobe.

    make studio-setup
    make studio

Abre http://127.0.0.1:8000. Escribe → comprueba sin generar → guarda → genera y
revisa. Las claves se configuran en .env; nunca se guardan en el frontend.

**Manual completo:** [GUIA.md](GUIA.md). Estado de desarrollo y siguiente paso:
[PROJECT_STATUS.md](PROJECT_STATUS.md).

## Estado real

- Shorts con fondos locales: Fish + FFmpeg.
- Shorts con Pexels: Fish + Pexels + FFmpeg nativos.
- Vídeo largo: motor nativo experimental; Básico o Documental enriquecido desde el formulario, sin preparar un plan manual.
- Montaje: compara A/B y renderiza planes por escena con audio/recursos locales;
  galería de19composiciones, tres muestras UltimateBet, otro tema, fotografía y QA.
  Three.js/póker se conserva opcional histórico.
- Compilador de briefs: selección local por entidad/función, derechos y hashes;
  biblioteca de20músicas con crossfade/ducking,6SFX y11voces catalogadas. No interpreta guiones arbitrarios.
- Guardado local: outputs/ready y outputs/longform. No requiere Google Drive.
- Generar o asignar una fecha local no publica. Buffer requiere confirmación.
- YouTube: CLI oficial de lectura preparado, consentimiento de Google pendiente.
  El director general y los perfiles multicanal siguen pendientes.
  MPT sólo queda para recuperar tareas antiguas;
  los vídeos nuevos no requieren su instalación.
- El desarrollo y la verificación se hacen desde un checkout completo. El wheel
  Python aislado todavía no distribuye la interfaz, presets y recursos del estudio.

## Verificar

    make verify

Ejecuta higiene del repositorio, pruebas Python, pruebas React y build TypeScript.
Para los recorridos reales de navegador con renderizadores de pago simulados:

    frontend/node_modules/.bin/playwright install chromium
    make verify-browser

La instalación del navegador necesita red. Los tests no necesitan claves de
proveedores; los escenarios de navegador usan datos temporales.

## Documentación vigente

- [Índice de manuales](docs/README.md): encuentra la fuente adecuada sin duplicados.
- [Qué hace Kitok y cómo reutilizarlo](docs/capabilities.md): automatización real,
  trabajo de agentes/operador y adaptación a nuevos vídeos/canales.
- [Guía diaria](GUIA.md): frontend, terminal, pasos y resolución de problemas.
- [Estado comprobado](PROJECT_STATUS.md): evidencia, límites y siguiente paso.
- [Desarrollo](docs/development.md): Git, revisiones y mantenimiento constante.

Los documentos sustituidos sólo se conservan en el [archivo histórico](docs/archive/README.md),
fuera de las instrucciones operativas. `make docs-check` comprueba enlaces,
estructura y contratos de ejemplos; también forma parte de `make verify` y CI.

## Estructura

- src/kitok/: servicios, estado, medios, proveedores y API.
- frontend/: estudio React.
- scripts/: arranque, verificación y herramientas de diagnóstico.
- examples/: ejemplos sintéticos públicos.
- content/, state/, outputs/, cache/, local/: trabajo local excluido de Git.
- content_queue.json: cola activa local; el estudio la crea vacía si falta.

Los pilotos antiguos, importaciones y backups sueltos se preservan bajo local/.
El manifiesto local de organización contiene sus rutas y hashes. La limpieza no
reescribe historia Git ni altera rutas de vídeos ya guardadas.

Consulta [AGENTS.md](AGENTS.md) antes de modificar el proyecto.
