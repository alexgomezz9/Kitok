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
- Vídeo largo: motor nativo experimental por defecto en CLI y estudio.
- Montaje: compara A/B y renderiza planes por escena con audio/recursos locales;
  gráficos reutilizables, caché por plano y QA sobre el MP4 real.
- Guardado local: outputs/ready y outputs/longform. No requiere Google Drive.
- Generar o asignar una fecha local no publica. Buffer requiere confirmación.
- El director autónomo, los perfiles multicanal y YouTube directo están diseñados,
  pendientes de implementación. MPT sólo queda para recuperar tareas antiguas;
  los vídeos nuevos no requieren su instalación.
- El desarrollo y la verificación se hacen desde un checkout completo. El wheel
  Python aislado todavía no incluye la interfaz ni el CLI raíz de largos.

## Verificar

    make verify

Ejecuta higiene del repositorio, pruebas Python, pruebas React y build TypeScript.
Para los recorridos reales de navegador con renderizadores de pago simulados:

    frontend/node_modules/.bin/playwright install chromium
    make verify-browser

La instalación del navegador necesita red. Los tests no necesitan claves de
proveedores; los escenarios de navegador usan datos temporales.

## Documentación

| Documento | Contenido |
|---|---|
| [GUIA.md](GUIA.md) | Operación diaria y comandos |
| [Montaje por escenas](docs/editing.md) | Planes reutilizables y comparación sin nueva voz |
| [Auditoría](docs/audit/2026-10-15.md) | Capacidades comprobadas, riesgos y límites |
| [Desarrollo](docs/development.md) | Ciclo de coordinación, revisión y CI |
| [Multicanal y director](docs/design/multichannel-production.md) | Propuesta de arquitectura y contratos |
| [YouTube oficial](docs/design/youtube.md) | OAuth, métricas y almacenamiento histórico propuestos |
| [Roadmap](docs/roadmap.md) | Fases y aceptación verificable |
| [Mapa rápido](PROJECT_GUIDE.md) | Entradas y referencias |
| [Archivo histórico](docs/archive/) | Documentación anterior, no instrucciones vigentes |

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
