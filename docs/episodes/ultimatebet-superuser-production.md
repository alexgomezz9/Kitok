# UltimateBet: muestra actual y reutilización

Estado verificado en [PROJECT_STATUS.md](../../PROJECT_STATUS.md). Este documento
registra el piloto terminado; no es una orden de regenerar el episodio ni su voz.

## Resultado vigente

- Carpeta local: `outputs/evaluation/ultimatebet_cinema/`.
- `A_current.mp4`: montaje B anterior, usado como referencia.
- `B_improved.mp4`: muestra C final de76s,17escenas,1920×1080p30.
- `plan.json`: plan compilado con hashes; `brief.json`: decisiones editoriales;
  `director_plan_pinned.json`: salida del compilador; `manual_plan.json`: plan previo.
- `B_improved.qa.json`, `B_improved.contact.jpg` y `CREDITS.md`: QA, revisión y derechos.
- El estudio muestra esa carpeta en Montaje → UltimateBet — C.

La voz/mix se reutilizan; el audio decodificado es idéntico a A. El último
ensamblado con17planos cacheados tardó14,49s, sin incluir QA ni el render3D previo.
No extrapolar esa medida a un episodio nuevo. El original de652,6s, sus audios,
las comparaciones anteriores y los experimentos siguen conservados localmente.

## Revisión realizada

Se corrigieron texto UTF8, cartas ambiguas, el origen equivocado de una apuesta,
superposición de rótulos y duración de la revelación. Las cartas pasan de ocultas
a visibles para NioNio con cue explícito. Foto de Hamilton: Gene Bromberg,
CC BY-SA2.0, con recorte/movimiento/sombreado y créditos/ShareAlike conservados.
Las manos3D son reconstrucciones ilustrativas, no manos reales ni capturas del software.

Se revisaron contactos y fotogramas completos mediante revisión independiente.
No consta audición subjetiva o reproducción audiovisual continua. Siguen presentes
stock genérico, contraste entre stock luminoso y3D oscuro y un diagrama plano.
Algunas fuentes se reescalan; salida1080p no acredita material nativo1080p.

## Para otros vídeos

Reutiliza los motores, validación, caché, catálogo, música y compilador siguiendo
[capacidades y responsabilidades](../capabilities.md). Cambia guion, hechos, audio,
tiempos y recursos. Las escenas table/records no son genéricas: Paredes/NioNio
están fijados en el código y el compilador bloquea otro reparto.

Falta ampliar el episodio completo. Antes conviene resolver más recursos específicos
y coherencia visual. El encargo y las versiones de documentación anteriores están
aislados en el [archivo histórico](../archive/README.md); no se usan como manual.
