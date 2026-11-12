---
name: kitok-loose-thread
description: Prepara o continúa documentales en inglés de Loose Thread con archivos reales del caso y stock de Kitok.
---

# Loose Thread en Kitok

Lee `PROJECT_STATUS.md` y las secciones de vídeo largo de `GUIA.md`. Usa el narrador
original de Loose Thread y el ID `UCLnP8Kb1USd06TW3D1JLFvg`. Para datos del canal,
consulta el perfil `local/youtube` con el ID explícito en el [CLI de YouTube](../../../docs/integrations/youtube-readonly.md).

1. Investiga el caso con fuentes primarias, escribe en inglés y guarda el guion
   limpio para Fish. Conserva las afirmaciones discutibles, fuentes y licencias en
   las notas editoriales del episodio, junto al guion. Registra candidatos descartados
   cuando falte permiso, contexto o una identificación fiable.
2. Busca fotos, documentos y fragmentos auténticos relevantes. Comprueba el origen,
   lo que se ve y las condiciones de uso. Usa `scripts/media_library.py` para buscar
   y recuperar imágenes con licencia compatible de Commons. Conserva los medios
   elegidos en `images/` o `clips/` del episodio. No conviertas ilustración en prueba.
3. En el [JSON visual parcial](../../../docs/editing.md#json-parcial-sobre-montaje-automático),
   ancla cada recurso a una frase exacta y agrega procedencia, crédito, licencia y
   `usage: "document"` si es evidencia del caso. Usa `occurrence` si se repite la
   frase. Para MP4 añade `duration` y, si procede, `source_start`. Deja los movimientos
   de fotos al motor salvo que haga falta proteger un encuadre. Escribe keywords de
   stock de contexto para cubrir la narración restante.
4. Importa guion y JSON en Vídeo largo y ejecuta «Comprobar». Reutiliza narración y
   alineación aprobadas cuando coincidan guion, voz y velocidad. Ejecuta Native para
   mezcla, stock, montaje, créditos y MP4 según el alcance del encargo. Ante un fallo,
   revisa recibos y reutiliza el audio confirmado antes de llamar otra vez a Fish.
5. Revisa una muestra con el recurso y su entrada/salida, encuadre y audio. Para la
   entrega verifica el MP4 y créditos, registra qué se reprodujo y deja el siguiente
   paso. Guarda guion, fuentes y plan junto al episodio para retomar desde otro chat.
