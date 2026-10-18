# Desarrollo y revisión coordinada

Contrato vigente del proyecto: [AGENTS.md](../AGENTS.md). Esta página concreta el
ciclo de trabajo; no instala otro sistema global de agentes.

## Inventario histórico comprobado el 15 de octubre de 2026

Se inspeccionaron nombres y valores permitidos de configuración, instrucciones,
roles, skills y hooks. No se abrieron credenciales ni se copiaron configuraciones
privadas al repositorio.

- Configuración global: modelo gpt-6.1-sol con razonamiento high. Cinco roles:
  architect, explorer, reviewer, adversarial y evaluator; configurados para lectura.
- Skills existentes: takehome-discovery, plan-work, execute-plan, git-checkpoint,
  release-gate y verify-before-completion. Cubren planificación, ejecución,
  checkpoints, verificación y revisión.
- SessionStart invoca session_context.py e inyecta el estado privado de
  .codex-work/ en inicio, reanudación, limpieza y compactación.
- PreToolUse aplica git_guard.py al matcher Bash. Una prueba inocua con texto de
  una operación destructiva fue bloqueada: hay un falso positivo por coincidencia
  textual. No se modificó ni eludió el hook. Su configuración no demuestra que
  intercepte todas las herramientas disponibles en cada cliente.
- .codex/ y .agents/ existen como directorios del entorno sin configuración de
  proyecto visible. No se deduce que falten capacidades por esa ausencia.
- Hay metadatos de 17 plugins en caché, entre ellos GitHub y vidIQ, y nombres de
  MCP HappyRobot configurados. Caché/configuración no acredita instalación activa,
  permisos ni autenticación. No se conectaron esos servicios en aquella auditoría. El estado vigente de GitHub/vidIQ/YouTube se registra en PROJECT_STATUS.md.
- Las herramientas de subagentes sí se usaron en esta sesión para auditorías y
  revisión independientes. No había un gate ejecutable local/CI que agrupara
  higiene, Python, React y navegador.

Las capacidades nativas permiten roles y trabajo delegado; las skills reutilizan
instrucciones bajo demanda. Los roles heredan límites del entorno: una instrucción
de «sólo lectura» no sustituye el sandbox. No se añaden skills con nombres
duplicados ni hooks globales.
[Subagentes](https://developers.openai.com/codex/subagents/),
[skills](https://developers.openai.com/codex/skills/),
[hooks](https://developers.openai.com/codex/hooks/).

## Comparación y decisión

| Referencia Superpowers | Lo que ya existe | Mejora adoptada aquí |
|---|---|---|
| subagent-driven-development | Coordinador, roles y release-gate | Encargos delimitados y devolución directa de hallazgos al coordinador |
| executing-plans | plan-work, execute-plan y estado privado | Cerrar cada unidad con evidencia y actualizar pendientes |
| requesting-code-review | reviewer, architect y release-gate | Review por requisitos y corrección; contexto acotado e independiente |
| verification-before-completion | Skill homónima y contrato de evidencia | Un comando reproducible que falla al primer error |
| systematic-debugging | Tests y revisión, sin otra skill específica | Reproducir, aislar causa, corregir y verificar regresión antes de ampliar cambios |

Fuentes de comparación:
[desarrollo delegado](https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md),
[ejecución](https://github.com/obra/superpowers/blob/main/skills/executing-plans/SKILL.md),
[revisión](https://github.com/obra/superpowers/blob/main/skills/requesting-code-review/SKILL.md),
[verificación](https://github.com/obra/superpowers/blob/main/skills/verification-before-completion/SKILL.md),
[depuración](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md).
Se adoptan prácticas en este protocolo, sin instalar Superpowers ni copiar sus
skills. La carencia concreta se resuelve con el gate del repositorio.

## Protocolo del coordinador

1. Leer guía, estado y diff. Especificar objetivo observable, requisitos, archivos
   propios, datos que preservar, acciones externas autorizadas y comprobación.
   Para cambios sustanciales, comparar el diseño mínimo y fallos principales.
2. Implementar una unidad pequeña. En encargos paralelos, asignar propiedad
   exclusiva y recordar que otros trabajan en el mismo árbol.
3. Ejecutar primero la prueba pertinente. Ante fallo: guardar reproducción,
   formular causa contrastable y cambiar una hipótesis cada vez. Un fallo de test
   puede ser contrato obsoleto; contrastarlo antes de cambiar producción.
4. Enviar a revisión el diff y requisitos, comandos ejecutables y límites; evitar
   justificaciones privadas que sesguen al revisor. Revisar tanto cumplimiento como
   corrección. Un cambio pequeño suele necesitar una revisión; estado persistente,
   pagos, concurrencia, seguridad o entrega importante requieren perspectivas
   independientes de corrección, adversarial y evaluación.
5. El revisor devuelve ubicación, escenario reproducible, impacto, prioridad
   P0–P3 y evidencia faltante. El coordinador deduplica y decide. Corrige P0/P1,
   añade regresión cuando aporta valor y pide relectura del límite afectado.
   Desacuerdos se resuelven con código/pruebas; los riesgos aceptados quedan escritos.
6. Ejecutar el gate final sobre el resultado corregido, no sobre un commit anterior.
   Actualizar estado privado y documentación pública de operación. Crear commits
   coherentes. El coordinador gestiona este ciclo sin pedir al operador que copie
   mensajes entre agentes.

Si falta evidencia, declarar «no verificado». Agotar tiempo no convierte una
revisión o integración en aprobada. No crear agentes para tareas que un comando
determinista resuelve mejor. Este protocolo coordina desarrollo. El compilador editorial prepara planes desde
un brief explícito; no sustituye la investigación ni la revisión audiovisual.

## Gate ejecutable

    make verify
    make verify-browser

verify comprueba rutas, modos y contenido del índice Git y del árbol de trabajo, además de firmas conocidas de credenciales
sin imprimir valores, ejecuta pytest, Vitest, build TypeScript/Vite y diff --check.
verify-browser añade Playwright contra HTTP local, archivos temporales y proveedores
simulados. Instalar Chromium previamente como indica README. Cada paso tiene límite
de diez minutos y un fallo interrumpe los siguientes. Los tests Python bloquean
conexiones de socket; el gate retira credenciales exportadas de proveedores de su
entorno, pero no es un sandbox contra código malicioso ni un detector exhaustivo de
secretos. No ejecutar pruebas de procedencia desconocida con .env real.

[CI](../.github/workflows/verify.yml) ejecuta verify-browser en push/PR y manualmente,
con Python 3.12, Node 24, FFmpeg y Chromium, sin secretos de proveedores ni permisos
de escritura. No publica ni despliega. Las versiones de actions se contrastaron con
sus repositorios oficiales:
[checkout](https://github.com/actions/checkout),
[setup-python](https://github.com/actions/setup-python),
[setup-node](https://github.com/actions/setup-node).
La ejecución remota debe comprobarse tras el push; definir YAML no prueba CI verde.

Antes de entregar una reorganización, repetir el gate desde un clone sin .env,
cola, estado ni medios privados. Un clone que reutiliza dependencias instaladas
prueba integridad de fuentes, no una instalación nueva desde Internet. El wheel
aislado sigue incompleto para el estudio y el CLI de largos; usar checkout completo.

Una suite verde demuestra sus escenarios con mocks. No demuestra saldo,
conectividad Fish/Pexels/MPT, publicación Buffer, acceso vidIQ ni OAuth YouTube.
Esos ensayos requieren autorización y evidencia propias.

## Continuidad de cada checkpoint

PROJECT_STATUS.md es la entrada breve para el siguiente chat: capacidades
comprobadas, límites y siguiente paso. GUIA.md describe operación, incluyendo el
frontend que la lee. AGENTS.md obliga a actualizar ambos y los documentos afectados
en cada unidad terminada; elimina afirmaciones antiguas de las páginas vigentes,
y conserva propuestas/encargos fechados bajo docs/archive/ o docs/research/.

El operador autoriza commits y pushes de ramas de trabajo verificadas. El
coordinador revisa el índice, ejecuta el gate pertinente, crea un commit coherente,
sube la rama y coteja SHA/CI. No hay un hook que haga push de cualquier cambio
parcial: las pruebas y la inspección preceden al checkpoint. Main, publicación
de vídeos y gastos significativos mantienen su aprobación específica. No añadas
otras skills o hooks que dupliquen el protocolo actual.

Durante el piloto editorial, la revisión produjo correcciones comprobables:
enlaces internos que redirigían salidas, promoción interrumpida de QA/contact,
muestreo de más de 80 planos y caché del reproductor tras completar un render. Las
regresiones persistentes están en test_editorial_studio/test_editorial_plan y
Workbench.test; el E2E de Montaje renderiza FFmpeg real con medios temporales.
