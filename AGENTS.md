# Kitok

- Empieza por `PROJECT_STATUS.md`, el tramo pertinente de `GUIA.md` y el diff. Para Loose Thread usa `kitok-loose-thread`. Para Trazo Maldito usa `kitok-youtube`. Mantén las entradas, manuales y estado vigentes, y archiva las notas históricas en sus carpetas.
- La interfaz es React/Vite y el transporte es FastAPI. Reutiliza los servicios Python: `application.py` para shorts, `longform_studio.py` y `longform.py` para largos, `editing/` para dirección y `rendering/` para el motor. `docs/development.md` enlaza los manuales y las comprobaciones.

## Producción

- El agente investiga, escribe y decide la posición de los recursos auténticos. Kitok valida, sincroniza, mezcla y renderiza. Revisa contexto y licencia, conserva fuente y créditos, y distingue archivo real de stock ilustrativo.
- Reserva episodios con los comandos de la guía del canal en content/longform/<canal>/<NNN_tema>. Deja la subida en su subcarpeta entrega/. Lee el índice de documentación al retomar y actualiza la nota pertinente con fuente cuando una decisión se vaya a reutilizar.
- Para Loose Thread opera por CLI. El agente busca, descarga y verifica los recursos disponibles y redacta el JSON. Cuando falte un archivo decisivo, indica el enlace, el fragmento y la carpeta exactos. Usa ilustración o IA cuando aporte claridad. Anota la procedencia y retira temporales al cerrar.
- Comprobar, guardar y previsualizar borradores son operaciones locales. Reutiliza voz, alineación y stock confirmados. Las síntesis inciertas se investigan antes de repetir. Mantén el bloqueo por ID, la identidad de los datos y las salidas previas en reintentos y recuperaciones.
- Native es el flujo de producción. MoneyPrinterTurbo se usa sólo para reanudar una tarea histórica conocida. El publicador Buffer cubre shorts, con preview, confirmación y reconciliación. Para YouTube comprueba el ID del canal y los permisos; publicar o modificar contenido requiere un encargo concreto.
- La UI y la API son locales, en `127.0.0.1`. Valida IDs y rutas en el servidor. Protege `.env`, la cola, `state/`, episodios, cachés y tokens. Los tests usan un workspace temporal y proveedores simulados.

## Entrega

- Revisa código y casos de fallo, ejecuta las pruebas focales y `make docs-check`. Usa `make verify` para cambios transversales y `make verify-browser` si cambias recorridos de UI. En medios, comprueba una muestra reproducible y registra qué se vio y qué se escuchó.
- Integra el trabajo local verificado en main. Haz commits coherentes tras comprobar el índice, el diff y las pruebas. Conserva el trabajo ajeno y usa `git switch --no-overwrite-ignore` cuando cambies de rama. Antes de subir una rama, integrar main, desplegar o publicar, comprueba la autorización del encargo.
- Actualiza la guía y las referencias afectadas. Deja el siguiente paso en `PROJECT_STATUS.md` y, si existe, en el estado privado de `.codex-work/`.
