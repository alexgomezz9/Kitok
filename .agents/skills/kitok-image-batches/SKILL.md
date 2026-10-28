---
name: kitok-image-batches
description: Genera, continúa, repara o valida las imágenes de un episodio de Kitok desde sus prompts, usando láminas ordenadas, recortes y manifiestos reanudables. No genera voz ni renderiza vídeo.
---

# Imágenes de episodios Kitok

Localiza el episodio solicitado; lee sus instrucciones, perfil del canal y configuración sin alterar guion, voz, prompts ni otros episodios. Descubre el JSON real: `plan_imagenes.json` terminado, `plan_visual.json` o `planificacion_visual/plan_visual_prevoz.json`. Si hay varios, comprueba cuál corresponde al guion y trabajo vigente. Conserva IDs y `image_file`; usa `scene_prompt` como prompt principal y `visual_description` para revisar. El contrato actual de reutilización se verifica con `kitok.youtube_stickman_es.reuse.source_spans`; no edites el renderer ni sus recibos para simular aprobación.

## Herramienta y referencias

Comprueba la skill oficial `imagegen` y la herramienta integrada disponibles en esta sesión; lee la skill y úsala. Verifica costes/límites si la herramienta o cuenta los exponen; cuando no los expongan, indica que son desconocidos, sin inventar gratuidad, saldo ni tarifa. Una autorización previa vigente permite continuar. No recurras a APIs independientes de pago sin autorización ni ejecutes generación desde el auxiliar Python. En resultado ambiguo, conserva el intento y averigua si hay artefacto antes de repetir; tras tres fallos del mismo bloque, informa de pendientes y detén ese bloque.

Inspecciona las referencias locales con `view_image`. Fija referencias de estilo y un ancla visual del protagonista proporcionada o aceptada, conservando esos mismos archivos y hashes durante los lotes. Si falta ancla, crea primero una muestra con autorización vigente y revísala antes de ampliar. Referencias fijan estilo/identidad, no composiciones. Distingue máscara/rostro, vestuario y personajes secundarios; no fuerces al protagonista en planos de objetos, documentos ilustrativos, mapas, fechas, gráficos u otros personajes. No transfieras el tono entre canales.

## Muestra de enfoque y horror stickman

Antes de lotes completos de un estilo NUEVO, muestra tres enfoques del mismo
momento según kitok-youtube/perfil: línea limpia, tinta/sombras y viñeta con rojo
selectivo, todos con cuerpo de trazo fino, cabeza simple y máscara/ropa constantes.
Una ilustración cartoon genérica no cumple stickman. Prueba acción, reacción y
objeto con el enfoque elegido. Si el operador delega «siguiente automático» o
«no preguntes», elige/revisa y sigue, registrando decisión del agente. Sin esa
delegación ni ancla aceptada, espera elección inicial antes de ampliar. No vuelvas
a pedirla cada episodio si sigue vigente.

Aplica terror contextual: oscuridad legible, amenaza, persecución, armas y sangre
estilizada cuando corresponda al guion. No suavices siempre a ilustración infantil;
no inventes atrocidades ni aumentes violencia ajena al relato. Conserva el detalle
del entorno sin engrosar el cuerpo hasta perder la silueta stickman. La imagen
ancla debe mostrar ese criterio antes de producir cien viñetas.

Comprueba `images.character_continuity` del perfil al revisar cada lote: todos los personajes mantienen silueta stickman y sus anclas, también al cambiar de edad/etapa. Rechaza una deriva a cuerpo cartoon ancho o rostro realista antes de ampliar; conserva las variantes válidas sin regenerar por rutina.

## Referencia visual aportada por el operador27/10

Las cuadrículas de miniaturas de Jason/Michael vistas en el chat fijan una
atmósfera más intensa: máscaras muy reconocibles, cuerpo/brazos/piernas de trazo
stickman fino, sombras negras, contraluz azul de luna o naranja/rojo, niebla y
escenarios con profundidad. Armas con sangre/salpicaduras y consecuencias cuando
lo justifique la narración. Evitar que stickman se convierta en dibujo infantil
o ilustración genérica. No copiar titulares/flechas de miniatura al interior.

La iluminación sigue la escena: infancia tranquila de día antes del conflicto
permanece diurna y sin violencia inventada. Oscuridad, sangre y amenaza se elevan
cuando el relato lo pide, con legibilidad móvil. Para estilo nuevo, preparar
muestras antes de ampliar; el ejercicio guiado vigente se detiene en cada fase.

## Bloque, recorte y revisión

El auxiliar `scripts/batches.py` sólo prepara prompts/manifiestos, recorta con Pillow y guarda PNG revisados. Ejecútalo con el Python/Pillow existente en Kitok, desde su raíz. No llama proveedores. `--help` da los argumentos reales.

```bash
.venv/bin/python RUTA_SKILL/scripts/batches.py pending EPISODIO --plan PLAN_RELATIVO
.venv/bin/python RUTA_SKILL/scripts/batches.py plan EPISODIO --plan PLAN_RELATIVO --start ID --count 9 --columns 3 --batch lote-001 --reference REF_RELATIVA --anchor ANCLA_RELATIVA
```

Elige nueve escenas consecutivas pendientes en el orden del JSON y numéralas 1–9. `plan` conserva esa asignación y genera `prompt.txt` con ÚNICAMENTE esos nueve prompts más estilo/referencias; no envíes el guion completo, otras escenas, una cuadrícula anterior ni todo el historial. Invoca la herramienta con ese texto y las referencias fijadas explícitamente, evitando incluir imágenes de conversación adicionales. Cuadrícula exacta 123 / 456 / 789, nueve casillas iguales, cada una 16:9, sin bordes ni texto de numeración. Cada casilla es independiente y exclusiva de su prompt. El texto intencional de una escena prevalece sobre prohibiciones genéricas de texto. No reescribas el archivo original.

Genera y guarda dos lotes primero cuando se esté validando un estilo/método nuevo; inspecciona sus resultados y continúa si son adecuados. Copia cada lámina al lote antes de la siguiente llamada; es temporal hasta validar y aceptar los PNG finales. Para el último bloque, usa las escenas restantes y casillas vacías declaradas; nunca inventes escenas para rellenar. El manifiesto preserva las posiciones.

```bash
.venv/bin/python RUTA_SKILL/scripts/batches.py crop EPISODIO --batch lote-001 --atlas SALIDA_REAL --inset 8 --source-kind builtin_imagegen
```

El comando crop guarda automáticamente contacto_recortes.png con los recortes reales, sin escalarlos, para revisar el lote sin montar la hoja a mano. Inspecciona TODOS los recortes: correspondencia con `visual_description`, acción, personajes/objetos, anatomía simple, identidad, composición y ausencia de bordes/contaminación de otra casilla. El recorte uniforme es sólo el punto de partida: si las divisiones no están en tercios exactos, ajusta con Pillow y conserva las cajas reales; regenera un lote si el orden no es inequívoco. No reasignes escenas por parecido. Revisa los avisos de resolución y duplicados exactos/perceptuales: pueden ser legítimos, pero exigen juicio. No prometas 1080p nativo: registra tamaño real. Conserva los recortes nativos. Las imágenes aportadas se validan con `ImageBatch.inspect(..., require_delivery_size=False)`: conservar tamaño nativo y hashes, sin ampliaciones previas. Native escala y encuadra al tamaño final del vídeo. Las fuentes pequeñas llevan aviso de calidad; no recuperan detalle al ampliar. El mínimo 1280×720 se conserva para nuevas entregas individuales y miniaturas.

```bash
.venv/bin/python RUTA_SKILL/scripts/batches.py accept EPISODIO --batch lote-001 --ids ID1 ID2 --reviewer Codex --note 'Revisión visual real de correspondencia, estilo y recorte'
```

Acepta sólo IDs vistos y adecuados. Los demás quedan pendientes. El auxiliar publica por las rutas `image_file` originales, sin sobrescribir archivos distintos. Para reparar existentes, conserva primero copia y hash en el lote y solicita sólo la sustitución autorizada; no borres originales. Para fallos, usa un NUEVO lote 2×2 (`--count 4 --columns 2`) o individual (`--count 1 --columns 1`) que cubra sólo escenas afectadas consecutivas; si están dispersas, haz lotes individuales. No repitas todo el episodio. `pending` distingue archivos existentes de revisiones documentadas; su existencia no acredita calidad. Los hashes fijados impiden reanudar con prompts/referencias/crops cambiados. No trabajes simultáneamente sobre un mismo lote.

## Entrega

En `imagenes/`, entrega sólo PNG con IDs originales, según `image_file`. Láminas, cajas de recorte, hashes, estado y revisiones quedan en `planificacion_visual/lotes_imagenes/<batch>/manifest.json`, fuera de la carpeta consumida por Kitok. No marques como revisados archivos sólo porque decodifiquen. No modifiques recibos `.stickman`; para imágenes aportadas usa el recorrido existente `--reuse-images`. Cuando haya voz/alineación reales, `prepare --reuse-images` valida sin renderizar; sólo ejecuta `produce` si el encargo lo autoriza. Aprovecha `kitok-audiovisual-qa` al revisar montaje si está disponible y dentro del encargo; esta skill termina en las imágenes.

Antes de dar las imágenes por listas para montaje, valida TODOS los PNG finales con `ImageBatch.inspect`, también los existentes que no has generado en este turno. Validar sólo `source_spans` no comprueba su resolución. Si hay una revisión de entrega ya preparada (por ejemplo `revisiones/montaje_720p`), verifica sus archivos y hashes y comunica esa ruta exacta; no vuelvas a señalar los recortes nativos de la carpeta original como entrada lista. Mantén límites de seguridad y decodificación, y no atribuyas detalle nuevo al escalado.

Informa de cantidad realmente generada, aceptada, conservada y pendiente, tamaño nativo y ruta. Las skills se invocan en Codex con `$kitok-image-batches`; ese nombre no es un comando del renderer.


## Cierre de auxiliares

Tras aceptar y validar todos los PNG de los lotes resueltos, usa
`scripts/stickman_delivery.py organize EPISODIO` y revisa/aplica su limpieza.
Conserva PNG definitivos, prompts, cajas, revisiones, manifiestos y hashes;
las láminas, contactos y crops redundantes no son una segunda entrega permanente.
Un lote pendiente conserva sus fuentes. Si un recorte antiguo fue sustituido,
registra `cleanup_superseded_by` con el lote de reparación aceptado, nunca sólo
por coincidencia de ID. No volver a generar por la ausencia deliberada del atlas:
`pending` comprueba la aceptación contra el PNG final. Para otra reparación, lote
nuevo. Pruebas/muestras de diagnóstico en `local/pruebas/EPISODIO/`, con limpieza
al cerrarlas; no manipular recibos de voz o render para simular aprobación.
