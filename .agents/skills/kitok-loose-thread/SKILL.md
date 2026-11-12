---
name: kitok-loose-thread
description: Investiga, escribe y monta documentales en inglés de Loose Thread con material real, ilustraciones y stock de Kitok.
---

# Loose Thread en Kitok

Lee el estado vigente y [el método editorial](../../../docs/research/loose-thread.md).
Usa el narrador original y el perfil `local/youtube` con ID `UCLnP8Kb1USd06TW3D1JLFvg`.
Ejecuta desde el checkout WSL. El CLI es la entrada habitual.

1. Usa `reporting-status`, Analytics o `public-search` según la pregunta. Contrasta
   demanda, referencias y disponibilidad de archivo. Propón un ángulo concreto y
   decide con evidencia cuando el encargo lo delegue. El título y la miniatura
   deben prometer algo demostrable en el guion. Si ya hay trabajo compatible, retómalo.
   Para un vídeo publicado, consulta primero los datos propios. Abre el complemento
   `local/editorial/skills/yt-retention/SKILL.md` cuando aporte valor a la revisión.
2. Escribe en inglés, con hechos y fuentes. La apertura cumple pronto la promesa
   del clic. Cada rehook aporta una consecuencia, pregunta o prueba nueva y recibe
   respuesta. Lee el complemento `local/editorial/skills/yt-script/SKILL.md`
   cuando exista y aporte valor al guion en curso.
3. Busca tú los archivos reales de momentos, lugares y protagonistas. Descarga y
   verifica medios utilizables, con origen, fecha, autor y permisos. Prueba el
   archivo oficial y Commons primero, y renderiza documentos para lectura en vídeo.
   Guarda las selecciones en `images/` o `clips/`. Si una imagen decisiva queda
   inaccesible, da un enlace directo, indica la imagen, captura o intervalo exacto
   y la carpeta de destino. Usa otro recurso si la procedencia o el permiso falla.
4. Escribe tú el [JSON parcial](../../../docs/editing.md#json-parcial-sobre-montaje-automático).
   `anchor.phrase` es una cita literal breve y única del propio guion. Fish
   aporta el momento en que se pronuncia. Si se repite, usa `occurrence`.
   En MP4 indica `duration` y, si procede, `source_start`. Deja los huecos a stock
   pertinente. Usa IA para diagramas o reconstrucciones cuando añadan claridad.
   Reserva rótulos para información que el espectador necesite, como nombre,
   fecha o reconstrucción susceptible de confundirse con archivo real.
5. Valida el borrador desde `longform.py`. Reutiliza voz y alineación si encajan.
   Si el encargo pide producir, ejecuta Native y cierra el MP4 verificado.
   Revisa apertura, cortes, voz, mezcla y créditos. Conserva guion, fuentes,
   plan y entrega. Retira temporales que ya cumplieron su función.
