# Documentación vigente de Kitok

Empieza por la página que corresponda a tu tarea. Cada tema tiene una fuente
principal; los documentos no duplican instrucciones completas.

| Necesitas | Fuente vigente |
| --- | --- |
| Crear shorts/largos, revisar y descargar | [Guía diaria](../GUIA.md) |
| Saber qué está terminado y qué sigue | [Estado actual](../PROJECT_STATUS.md) |
| Entender qué se automatiza y qué requiere agente/persona | [Capacidades y próximos vídeos](capabilities.md) |
| Preparar brief/plan y reeditar sin nueva voz | [Montaje por escenas](editing.md) |
| Conectar YouTube sólo para lectura | [Conexión oficial](integrations/youtube-readonly.md) |
| Mantener código, Git, pruebas y documentación | [Desarrollo](development.md) y [AGENTS.md](../AGENTS.md) |
| Saber qué falta de la autonomía solicitada | [Límites y siguientes fases](roadmap.md) |
| Revisar el caso de ejemplo que ya se produjo | [UltimateBet actual](episodes/ultimatebet-superuser-production.md) |
| Entender herramientas elegidas y formatos viables | [Decisiones de investigación](research/README.md) |

## Cómo se mantiene

- La guía diaria vive en GUIA.md; el frontend lee ese mismo archivo.
- Las capacidades son contratos observados, no promesas de la arquitectura futura.
- PROJECT_STATUS.md conserva evidencia fechada y siguiente paso, sin convertirse
  en diario. Cuando cambie el producto, se actualiza junto al código y la guía.
- Las propuestas sólo aparecen como pendientes en roadmap.md. Los diseños
  sustituidos, auditorías y estudios fechados están en el [archivo histórico](archive/README.md),
  fuera de los manuales de operación actuales.
- `make docs-check` verifica enlaces locales, entradas permitidas en raíz y
  contratos de las plantillas públicas. No puede demostrar que una frase de
  documentación siga siendo cierta: eso exige revisar código y comportamiento.

## Organización de la raíz

Se conservan README.md, AGENTS.md, GUIA.md y PROJECT_STATUS.md como entradas.
main.py y longform.py son lanzadores finos; la lógica está en src/kitok/.
Makefile, pyproject.toml y requirements.txt sirven para instalación/ejecución;
requirements.txt delega en pyproject.toml para no duplicar versiones.

.env y content_queue.json permanecen locales en su ruta activa. Los medios,
contenido, estado y cachés son datos del operador; no se mueven por estética.
Las plantillas públicas viven en examples/ y las herramientas en scripts/.
