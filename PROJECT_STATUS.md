# Estado vigente de Kitok

Actualizado: **2026-10-26**. Rama **main**. Último código subido antes de este
checkpoint: `2bae2f5`, SHA remoto confirmado y [CI verde](https://github.com/alexgomezz9/Kitok/actions/runs/40389960019).
Encargo activo: terminar Jason completo, entrega única subtitulada y **>8 min**.

Manual: [GUIA](GUIA.md), [flujo editorial](docs/youtube-editorial.md),
[stickman](docs/youtube-stickman-es.md), [audio](docs/audio.md).

## Capacidades y evidencia

- Storyboard compila decisiones editoriales en escenas/prompts con cobertura
  exacta, personajes/referencias/cámara; lotes 3×3 con manifiestos y revisión.
- Kitok Native/FFmpeg/ASS monta, mezcla y exporta subtítulos con palabras reales:
  MAYÚSCULAS, grupos cortos y palabra activa amarilla/110 %. No publica.
- Fish nuevo requiere opción expresa; resultados inciertos se conservan sin retry.
  No hay ASR ni realineación acústica automática. QA técnico no acredita escucha.
- Imágenes aportadas conservan tamaño nativo con avisos; escalar no crea detalle.
- Mezcla `sample-clock-v4-decoder-tail`: conserva duración declarada del MP3 y
  margen AAC. 53 tests audio y muestra real33,5s/1005frames pasados, ambos QA
  passed, −16,1LUFS/−2,29dBTP; fotogramas vistos y reproducción completa silenciada.
- Reparación ahora admite `--tempo`0.9–1.1 sin cambiar tono, después de cortes
  revisados. Transforma timestamps de palabras y verifica originales/hashes.
  72 tests cortes/reuso/subtítulos pasados; revisión independiente sin hallazgos.
- Baseline anterior: 1154Python/25React, TypeScript/Vite y studio-check correctos;
  frontend tuvo timeouts intermitentes asociados hipotéticamente al reloj local.
  `docs-check` e higiene correctos en este checkpoint.

## Trazo Maldito

`@trazomalditoes`, ID `UC9h_aIbnfQUo0ylPsPNnbrg`, separado de Loose Thread.
OAuth oficial read-only comprobado26/10 en `local/youtube-trazo-maldito`:
cero vídeos, Analytics diario/tráfico `no_data`, Reporting disponible.
Tokens y snapshot privados ignorados; esta fecha no prueba acceso futuro.

«Siguiente» delega investigación/guion/dirección y coordinación por skills hasta
entrega local; Kitok hace operaciones deterministas. Perfil: historias/evolución
de todos los personajes famosos, infancia sólo cuando está contada en las obras.
Planificar9–12min y verificar MP4final estrictamente>480s; no relleno ni promesa de
monetización. Sólo una entrega subtitulada; limpio es intermedio del motor.

## Jason — render completo en curso

Base conservada: `content/longform/trazo_003_jason_voorhees`.
Guion1411palabras,109PNG finales revisados/validados, miniatura1280×720 vista en
móvil. Voz original476,891s contiene un añadido401,711–410,993s que el operador
identifica como habla tipo latín ajena al relato. Causa modelo/voz no aislada.
No atribuirlo a montaje; no repetir Fish ni generar nuevas imágenes.

Copia activa: `revisiones/voz_limpia_8min` dentro del episodio. Corte revisado
401,810930–410,892653s con100ms de margen, tempo0.94. Conserva1411palabras,
109ilustraciones y119hashes originales. Voz497,711s, plan115planos/497,733s,
máximo7,4s: `prepare --reuse-images` listo. Render completo con GPU y subtítulos
iniciado; MP4 final y QA aún pendientes. Progreso: `/tmp/kitok-jason-full-progress.log`.

Siguiente: esperar exit/QA finales, verificar duración>480s, inspeccionar resultado
y entregar únicamente `revisiones/voz_limpia_8min/video_subtitulado.mp4`, miniatura,
metadatos y créditos. No lanzar otro trabajo del mismo episodio. Escucha completa
no realizada por el agente; no confundir aprobación técnica con audiovisual humana.

Michael Myers anterior: ambos recibos QA leídos26/10 indican passed, sin nueva
reproducción/escucha en este encargo. Ruta conservada
`content/longform/stickman_2_michael_myers/revisiones/montaje_720p_sin_ruidos`;
no usar la copia diagnóstica anterior `sin_ruidos`.
[Historia técnica](docs/archive/README.md).
