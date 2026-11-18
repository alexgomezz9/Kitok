---
name: kitok-loose-thread
description: Investiga, escribe y monta documentales en inglés de Loose Thread con material real, ilustraciones y stock de Kitok.
---

# Loose Thread en Kitok

Lee el estado vigente y [el método editorial](../../../docs/research/loose-thread.md).
Usa el narrador original y el perfil `local/youtube` con ID `UCLnP8Kb1USd06TW3D1JLFvg`.
Ejecuta desde la carpeta del repositorio en Ubuntu WSL. El CLI es la entrada habitual.

1. Usa `reporting-status`, Analytics o `public-search` según la pregunta. Contrasta
   demanda, referencias y disponibilidad de archivo. Propón un ángulo concreto y
   decide con evidencia cuando el encargo lo delegue. El título y la miniatura
   deben prometer algo demostrable en el guion. Si ya hay trabajo compatible, retómalo.
   Para empaquetar, abre `local/editorial/skills/yt-package/SKILL.md` y
   `local/editorial/skills/yt-thumbnail/SKILL.md`. Compara dos premisas visuales,
   incluida una con texto. Usa una flecha si el detalle necesita señalización.
   Para un vídeo publicado, consulta primero los datos propios. Abre el complemento
   `local/editorial/skills/yt-retention/SKILL.md` cuando aporte valor a la revisión.
2. Escribe en inglés, con hechos y fuentes. Escribe en el guion las cifras y
   siglas como se han de pronunciar cuando eso ayude a Fish y sus subtítulos.
   La apertura cumple pronto la promesa del clic. Cada rehook aporta una consecuencia, pregunta o prueba nueva y recibe
   respuesta. Lee el complemento `local/editorial/skills/yt-script/SKILL.md`
   y sus referencias de retención antes de escribir. Desarrolla historia para
   9–12 minutos. Como estimación inicial, 1620–2160 palabras a unas 180 palabras
   por minuto. La voz y la pista de vídeo deben superar 480 segundos reales.
   Para estudiar ritmo o sonido,
   sigue el [flujo de referencias](../../../docs/research/reference-media.md).
3. Busca tú los archivos reales de momentos, lugares y protagonistas. Descarga y
   verifica medios utilizables, con origen, fecha, autor y permisos. Prueba el
   archivo oficial y Commons primero. Concentra la búsqueda en la apertura, la
   presentación de personas y lugares, y los giros que ganen una prueba visual.
   Guarda las selecciones en `images/` o `clips/`. Si una imagen decisiva queda
   inaccesible, da un enlace directo, indica la imagen, captura o intervalo exacto
   y la carpeta de destino. Usa otro recurso si la procedencia o el permiso falla.
4. Escribe tú el [JSON parcial](../../../docs/editing.md#json-parcial-sobre-montaje-automático).
   `anchor.phrase` es una cita literal breve y única del propio guion. Fish
   aporta el momento en que se pronuncia. Si se repite, usa `occurrence`.
   En MP4 indica `duration` y, si procede, `source_start`. Deja los huecos a stock
   pertinente. Puedes elegir una foto de Pexels como `usage: "illustration"` si
   un detalle se entiende mejor en un plano fijo. Mantén legibles los documentos,
   mueve el encuadre cuando guíe la mirada y corta al cambiar el sentido de la
   narración. Usa IA para diagramas o reconstrucciones que aporten claridad.
   Reserva rótulos para información necesaria, como nombre, fecha o reconstrucción.
   Si sólo orienta, pon la fecha sobre el lugar. Usa la línea temporal cuando
   relacione etapas y un inserto propio cuando la evidencia lo pida. Fija los
   efectos deliberados en el JSON y conserva el ritmo entre ellos.
5. Reserva el episodio con `.venv/bin/python longform.py new loose_thread TEMA`.
   El comando devuelve `content/longform/loose_thread/<NNN_tema>`.
   Si el encargo pide producir, prepara título, descripción con capítulos y
   créditos, etiquetas, ajustes de Studio y miniatura final. Ejecuta el CLI
   `longform.py CONFIG --deliver --dry-run` y luego `--deliver`.
   Usa `--deliver-only` para un MP4 confirmado y reutiliza voz y alineación.
   Mientras un montaje esté en revisión, usa `--keep-native-workspace` para
   conservar los planos y la mezcla. Si el operador señala un minuto, localiza
   el plano en el plan resuelto y usa [`--preview-scenes`](../../../docs/editing.md#preparar-un-montaje)
   para enseñar la variante de ese tramo. Conserva la duración si el ajuste es
   sólo visual para poder reutilizar la voz y los planos vecinos.
   Si dejas un servicio systemd produciendo fuera del chat, regístralo con
   `scripts/loose_thread_jobs.py observe EPISODIO --unit UNIDAD` y comprueba
   `local/loose_thread_jobs/ESTADO.md`. El observador actualiza fases, fallo y
   entrega automáticamente. Al retomar, usa `scripts/loose_thread_jobs.py status`
   y lee el journal antes de decidir un reintento. El temporizador se detiene
   cuando todos terminan o fallan; tras reanudar manualmente, repite `observe`
   con el mismo episodio y unidad. No marca revisión audiovisual ni publicación
   como completadas.
   Valida el comienzo, las pruebas visuales decisivas y los avisos técnicos.
   Kitok elige y monta el stock de relleno. Entrega la carpeta `entrega/`
   para que el operador suba y programe en Studio. Consulta los planos elegidos
   en `clips_revision/INDICE.md`, junto a la entrega. Conserva guion, fuentes,
   voz y recibos. Retira temporales que ya cumplieron su función.
