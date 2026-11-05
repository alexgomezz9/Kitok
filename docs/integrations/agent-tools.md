# Herramientas de agentes: navegador y HyperFrames

Instalación comprobada05/11/2026. Entorno objetivo: **Ubuntu WSL y Codex dentro de VS Code Remote WSL**.

## QA de frontend

- MCP `playwright` habilitado en `/home/prueba/.codex/config.toml`, transporte stdio local. No abre un servidor de depuración público ni conecta el perfil personal de Chrome.
- Runtime compartido: `@playwright/cli`0.1.23 y `@playwright/mcp`0.0.84; ambos usan Playwright1.65.0-alpha-2026-10-30 y Chromium headless1252.
- Para trabajo repetido con salidas acotadas, preferir la skill `playwright` y su wrapper; para exploración interactiva, usar el MCP. Elegir una interfaz por prueba. No hay una medición propia de ahorro de tokens.
- CLI: `bash /home/prueba/.codex/skills/playwright/scripts/playwright_cli.sh -s=qa-nombre open http://127.0.0.1:PUERTO`.
- MCP: abrir un chat nuevo de Codex en VS Code WSL y comprobar que aparece `playwright`. El catálogo está limitado a17herramientas de navegación/formularios/clics/capturas/consola/red, sin cargar el ejecutor de código inseguro.
- La configuración Windows y esta instalación WSL son independientes. En la app Windows ya existe control de navegador; no se duplicó allí este MCP.
- Verificado con página sintética local: inicialización MCP, tools/list, navegación, clic real, resultado visible, captura y0errores de consola. CLI también pasó el mismo recorrido. No constituye QA completo de Curbops ni Kitok.
- Nueva versión: `browser_click` usa `target` (no `ref`); las capturas piden `scale: css`. Leer siempre el esquema actual y los snapshots devueltos. Algunos snapshots se guardan en archivo.

Comprobar sin datos del operador:

```bash
python3 /home/prueba/.codex/maintenance/browser_smoke.py
python3 /home/prueba/.codex/maintenance/browser_mcp_smoke.py
```

## Vídeo opcional con HyperFrames

- CLI local fijado0.9.16, revisión upstream45705fa25c4aa7ba2cef3e8a66842ea08c261b9a. Skills `hyperframes` y `hyperframes-cli` instaladas **sólo en Kitok**, con referencias y licencia Apache2.0.
- Wrapper: `bash /home/prueba/.codex/maintenance/hyperframes/hyperframes.sh COMANDO`. Usa Node24local; no descarga latest en cada invocación.
- Telemetría desactivada y comprobada (`HYPERFRAMES_NO_TELEMETRY=1`, `DO_NOT_TRACK=1`). No hay cuenta cloud conectada ni generación de pago autorizada por instalarlo. `init` no instala más skills automáticamente.
- Uso: overlays, rótulos, gráficos y composiciones HTML cuando se encarguen. **Native/FFmpeg sigue siendo el recorrido de producción de Kitok**. No migrar episodios ni regenerar Fish/imágenes existentes.
- El navegador de render HyperFrames usa su Chrome headless152fijado por el proveedor, separado del navegador de QA. En este WSL la prueba usó software WebGL/CPU; no se ha acreditado aceleración GPU ni rendimiento de episodios largos.
- Prueba real: `local/pruebas/hyperframes-smoke-20261105`,640×360,12fps,2,000s,MP4no vacío; checkok sin errores de runtime/layout/contraste; warnings de composición/hold por ser un smoke corto, no demo artística. Snapshot y fotograma decodificado vistos.
- Proveedores existentes, voz, imágenes y música de Kitok conservan sus contratos. Las companion skills no instaladas no deben instalarse ni invocarse automáticamente.

Ejemplos desde una carpeta de prueba:

```bash
bash /home/prueba/.codex/maintenance/hyperframes/hyperframes.sh init MI_PRUEBA --non-interactive --skip-skills --skip-transcribe
bash /home/prueba/.codex/maintenance/hyperframes/hyperframes.sh check --json
bash /home/prueba/.codex/maintenance/hyperframes/hyperframes.sh snapshot --at 1 --json
# Render sólo cuando se encargue; para este equipo,1worker:
bash /home/prueba/.codex/maintenance/hyperframes/hyperframes.sh render --workers 1 --low-memory-mode --quality draft --output prueba.mp4
```

## Actualización y recuperación

Abrir un chat nuevo para descubrir las skills y el MCP. No cambiar permisos/hook trust hashes. Paquetes fijados y lockfiles en `~/.codex/maintenance/browser` y `hyperframes`.
Antes de modificar se guardaron los manifiestos/config/wrapper no secretos del navegador en `~/.codex/archive/tools-20261105/`. Config.toml no se copió porque puede contener credenciales.
Para retirar el servidor añadido: `codex mcp remove playwright` desde WSL con Node disponible. Para recuperar el navegador anterior, restaurar sus manifiestos/config/wrapper, ejecutar npmci y reinstalar la revisión de Chromium que declare ese Playwright. El instalador oficial de Chromium retiró su caché antigua automáticamente; el backup de manifiestos permite reconstruirla.
El doctor ya detectaba drift en `skills/yt-script/SKILL.md` antes de este encargo; se conserva sin sobrescribir ni aprobar su hash.

Fuentes: [Playwright MCP](https://github.com/microsoft/playwright-mcp), [Playwright CLI](https://github.com/microsoft/playwright-cli), [HyperFrames](https://github.com/heygen-com/hyperframes), [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).
