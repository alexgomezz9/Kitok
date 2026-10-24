---
name: kitok-storyboard
description: Convierte un guion definitivo de Kitok en escenas y prompts stickman compatibles con kitok-image-batches, con introducción dinámica, variedad visual y cobertura exacta. No escribe el guion, genera medios ni renderiza.
---

# Del guion a las escenas

Trabaja sobre el episodio indicado y sus reglas de canal. Lee el guion COMPLETO una vez, su configuración y las referencias interiores/personajes con `view_image`; las miniaturas no fijan el estilo interior. Para ahorrar contexto usa el auxiliar desde la raíz de Kitok:

```bash
.venv/bin/python .agents/skills/kitok-storyboard/scripts/storyboard.py context EPISODIO
```

Conserva el método visual existente: mismas referencias interiores y ancla aprobada en todos los lotes, sin sustituirlas por la última escena ni rediseñar personajes. Reutiliza `configuracion.json`: `style_prompt`, `characters`, `references`. Si ya están definidos, no los cambies; sólo completa identidades imprescindibles ausentes una vez por episodio; no impongas personajes ni tono de otro canal. Si no hay perfil, busca el perfil local vigente antes de preguntar. Una referencia de estilo aceptada puede bastar; un personaje reconocible necesita descripción/ancla fiable. Pide sólo referencias imprescindibles ausentes. No exige foto para mapas, objetos o personajes originales bien definidos. No sintetices, generes imágenes, renderices ni consumas investigación vidIQ.

## Decidir primero, compilar después

Identifica promesa, pregunta inicial, acciones, objetos, lugares, fechas/cifras, giros y resolución. Conserva TODOS los hechos, calificadores y palabras. La meta editorial es comprensión, satisfacción y retención para YouTube; no hay promesa de ingresos ni retención medida. Mantén el guion definitivo: no alargues artificialmente para anuncios, no inventes sensacionalismo ni gore. Perfil/brief decide el tono.

Escribe una lista JSON compacta de decisiones en `planificacion_visual/decisiones_storyboard.json`. Cada elemento aporta sólo el final literal del fragmento (`through`: una cita suficientemente larga y única en lo que queda del guion), descripción visual, prompt específico EN INGLÉS, personajes y tipo visual. También admite `narration` exacta en lugar de `through`. El auxiliar calcula narración completa, posiciones, IDs, rutas y prompts finales con estilo/identidades; no calcules estos campos ni repitas el estilo manualmente. Consulta [el contrato y un ejemplo](references/contract.md) al escribir el JSON.

Una escena = una idea visual clara: sujeto, acción, entorno, composición y utilería concreta. No escribas genéricos intercambiables. Alterna acciones/personajes, reacciones, primeros planos/objetos, mapas/lugares, preguntas, fechas, cifras, comparativas y diagramas SEGÚN el significado; no rellenes cuotas ni fuerces protagonista. Evita tres composiciones equivalentes seguidas salvo intención justificada. Los mapas deben respetar geografía verificada; si sólo se conoce un lugar, usa localizador esquemático sin rutas/coordenadas inventadas. Fechas/precios/textos sólo con función narrativa, literales o equivalencias verificadas; conserva moneda, negación y atribución. Documentos siempre ilustrativos. No reveles antes de tiempo lo que el guion reserva.

Ritmo orientativo sobre VOZ REAL: 0–30 s, 1,5–2,5 s por plano; 30–60 s, 2,5–4 s; después 4–6 s. Decide cortes por nueva información, acción, objeto o reacción, nunca por conteo mecánico. Da tiempo a leer mapas/preguntas. Sin voz, deja tiempos pendientes: usa la apertura narrativa para mayor densidad y no la llames «primeros 30 s» verificados. `camera` usa vocabulario Kitok: `slow_push_in`, `slow_pull_out`, `pan_left/right/up/down`, `diagonal_drift`, `subtle_rotation`, `zoom_and_pan`, `focus_push`, `static`. Sólo indica cámara cuando ayuda; no añade imágenes ni otro editor. Reutilizar una imagen para dos planos diferentes requiere decidirlo después en el montaje, no fingir dos dibujos aprobados.

```bash
.venv/bin/python .agents/skills/kitok-storyboard/scripts/storyboard.py build EPISODIO --decisions EPISODIO/planificacion_visual/decisiones_storyboard.json
.venv/bin/python .agents/skills/kitok-storyboard/scripts/storyboard.py check EPISODIO --timing
```

Entrega `planificacion_visual/plan_visual_prevoz.json`: contrato existente consumible directamente por `$kitok-image-batches`. Los tiempos NO están en ese JSON. `check --timing` audita sólo voz/alineación existentes y devuelve mapa `source_id → render_id`, reloj real y avisos de densidad; no certifica sincronía acústica. Si falta voz o hay sólo SRT/segmentos gruesos, queda pendiente el reloj por palabras. Nunca interpoles tiempos ni llames Fish para resolverlo. Un hueco de timestamps no demuestra silencio. Escenas <0,4 s requieren revisar la división semántica; las >máximo se subdividen por palabras reales reutilizando imagen: revisa esos avisos. El planificador existente conserva los spans cortos sin cambiar el objetivo global.

## Revisar y entregar

Antes de generar imágenes, relee las escenas contra el guion: cobertura íntegra, identidad, variedad, claridad en móvil, texto legible, misterio sin spoilers, apertura más densa con pausas útiles. Corrige las decisiones y recompila en una carpeta NUEVA si ya hay salida; no sobrescribas planes/imágenes ni episodios producidos. El auxiliar rechaza huecos, citas ambiguas, hechos narrados sustituidos, personajes desconocidos y salidas distintas existentes. Para probar un episodio real usa copia aislada en `/tmp`, conservando hashes de los originales.

Si aún no existe ancla visual aprobada, indícala como pendiente para que la skill de imágenes prepare y revise su muestra antes de ampliar; no inventes aprobación ni uses referencias de otro personaje.

La skill termina aquí. Informa ruta/escenas, qué referencias se usaron, si el reloj se comprobó o sigue pendiente, y el siguiente paso: `$kitok-image-batches Genera las imágenes pendientes de EPISODIO usando planificacion_visual/plan_visual_prevoz.json`. No copies su manual de cuadrículas. Tras tener imágenes, el recorrido existente `prepare --reuse-images` conserva correspondencia/cortes; `produce` necesita un encargo de montaje. No inventes `direccion_visual.json` con IDs prevoz: ese contrato exige los IDs reales de `prepare`.
