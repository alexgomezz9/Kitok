# Desarrollo, agentes y mantenimiento

Las reglas permanentes están en [AGENTS.md](../AGENTS.md). El estado de cada
entrega está en [PROJECT_STATUS.md](../PROJECT_STATUS.md). El manual operativo
está en [GUIA.md](../GUIA.md), también servido en el frontend.

## Ciclo de trabajo

1. Leer el estado y el diff; acotar objetivo observable, archivos, invariantes y
   pruebas. Abrir sólo el código relevante. Usar plan-work para cambios sustanciales.
2. Resolver una unidad coherente. Si se delega, asignar propiedad de archivos y
   recordar que el árbol es compartido. El coordinador recoge y corrige hallazgos.
3. Verificar primero el módulo afectado. En límites de pagos, concurrencia,
   publicación y seguridad, pedir revisión independiente acotada y releer fixes.
4. Actualizar las fuentes de documentación afectadas y eliminar sus afirmaciones
   obsoletas. Archivar sólo lo histórico útil, con aviso claro; no dejar dos guías
   con instrucciones alternativas para el mismo flujo.
5. Ejecutar el gate pertinente, revisar índice y secretos, crear commit con el
   código y sus tests/documentación esenciales y subir la rama autorizada.
   Comparar SHA remoto y comprobar CI; indicar expresamente si sigue pendiente.
6. Actualizar estado y siguiente paso al cerrar. Antes de integrar main, verificar
   autorización expresa y ascendencia remota. No forzar ni borrar cambios ajenos.
   Usar `git switch --no-overwrite-ignore`: una rama antigua puede versionar datos
   que hoy son privados. Comparar esas rutas antes del cambio y conservarlas;
   un estado Git limpio no demuestra que los archivos ignorados estén protegidos.

## Fuentes de verdad y orden

| Cambio | Documentos que revisar |
| --- | --- |
| Comando, ruta o paso de usuario | GUIA.md, ejemplos y enlaces afectados |
| Capacidad o límite de automatización | docs/capabilities.md y PROJECT_STATUS.md |
| Flujo de montaje o esquema de brief | docs/editing.md y examples/editorial/ |
| Conexión o métrica YouTube | docs/integrations/youtube-readonly.md |
| Regla de ingeniería/organización | AGENTS.md y este protocolo |
| Trabajo aún no implementado | docs/roadmap.md; nunca presentarlo como disponible |

La raíz tiene una lista pequeña de entradas/configuración permitidas. Los ejemplos
van en examples/, herramientas en scripts/, código en src/kitok/ y documentación
temática en docs/. No reorganizar cola, estado, medios o cachés privados sin
comprobar su uso. No añadir informes temporales ni otro prompt de continuidad en raíz.

## Agentes y skills: qué hay realmente

Se han usado agentes de implementación y revisiones independientes durante el
desarrollo; no son servicios de producción ni tareas que estén ejecutándose en
segundo plano. Kitok no tiene un enjambre de agentes, cron editorial o LLM por frame.
Los agentes pueden leer el contrato del repo y preparar briefs; el programa ejecuta
los pasos deterministas descritos en [capacidades](capabilities.md).

Las skills ya disponibles plan-work, verify-before-completion y git-checkpoint
cubren planificación, evidencia y Git. No se han instalado nuevas skills, MCPs o
hooks globales para este ordenamiento. Un workflow especializado puede añadirse
cuando una necesidad repetida lo justifique; no duplicar estas instrucciones.
AGENTS.md aporta guía persistente y las skills aportan procedimientos reutilizables;
ninguno sustituye la verificación ni instala por sí solo un orquestador.
[Guía oficial AGENTS.md](https://developers.openai.com/codex/guides/agents-md),
[prácticas de instrucciones](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra).

## Gate reproducible

```bash
make docs-check
make studio-check
make verify
# Con Chromium instalado:
make verify-browser
```

verify añade higiene de fuentes/índice, documentos, pytest, React, build y whitespace;
verify-browser añade los recorridos aislados con medios temporales. Los tests
bloquean proveedores externos y no acreditan una síntesis Fish o publicación real.
No usar la cola del operador para pruebas automáticas. CI ejecuta el mismo gate
sin secretos ni permisos de escritura: [workflow](../.github/workflows/verify.yml).
