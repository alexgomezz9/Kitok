# Estado vigente de Kitok

Actualizado: **2026-10-22**. Rama **main**, integrada por fast-forward desde
`feature/stickman-word-alignment`, base `53c739e`. Checkpoints de alineación
`be3cf81`, planificación `01c11ae` y reutilización `e46fbb1` verificados localmente.
CI remoto consultado: en curso; la comprobación del checkpoint de planificación
seguía instalando FFmpeg. No se presenta ese estado como CI aprobado.
Manual: [GUIA.md](GUIA.md); [stickman ES](docs/youtube-stickman-es.md);
[montaje](docs/editing.md); [movimiento](docs/motion.md); [audio](docs/audio.md).

## Capacidades comprobadas

- Stickman ES conserva guion y voz, convierte timestamps Fish completos aunque
  el guion contenga párrafos y planifica cortes sobre palabras reales. Valida
  transcript, orden, solapes, duración y hashes; admite palabras instantáneas
  sin inventar tiempos. Segmentos multipalabra mantienen la alternativa SRT.
- Reutiliza imágenes por fragmentos originales, conservando nombres y prompts.
  `--revision alineada --reuse-images` crea copias aisladas con manifiesto de
  hashes. La autorización de montaje no se presenta como revisión visual ni
  sustituye recibos o aprobaciones anteriores. Sin recursos existentes se conserva
  el flujo Codex: dirección, muestra, aprobación e imágenes, sin backend ImageGen.
- Kitok mantiene el único motor Native/FFmpeg/ASS/Pillow para cámaras,
  transiciones, mezcla licenciada/SFX y render. Shorts y documental conservados;
  MPT sólo recupera IDs históricos. No hay publicación automática.

## Verificación y límites

- `make verify`: **1075 Python**, **25 React**, TypeScript/Vite e higiene correctos.
  Tras los últimos ajustes, **181 pruebas stickman** correctas. `make docs-check`
  y `make studio-check` correctos. Revisiones independientes de corrección y
  adversarial: sin P0/P1; hallazgos de tolerancia, rechazo y BOM corregidos.
- Prueba aislada de recuperación por interfaz pública: Native **6 s / 180 frames**,
  QA técnico correcto, cero proveedores; conserva imágenes y deja miniaturas
  ausentes pendientes. No demuestra calidad audiovisual del episodio real.
- Preparación real repetida de `stickman_video1/revisiones/alineada/`: **136**
  asociaciones exactas texto/imagen, voz **585,03825 s**, montaje **585,06667 s**
  a 30 fps y máximo por escena **7,46667 s** (límite 8 s). Los **230 archivos
  originales** conservan hashes, incluidos recursos, SRT y recibos aprobados.
- No se han generado voz/imágenes ni renderizado el episodio completo durante
  esta reparación. Hay siete pistas documentales/investigation verificadas en
  caché. El resultado final, sincronía acústica, derechos y valoración visual
  completa requieren revisión humana. Sin SRT ni alineación real no hay ASR local.
- Backend del operador intacto; datos editoriales ignorados y cambios concurrentes
  de investigación preservados sin incluirlos. No se publica ni despliega.

Siguiente para el operador, desde la raíz del proyecto:

```bash
.venv/bin/python -m kitok.youtube_stickman_es produce content/longform/stickman_video1 --revision alineada --reuse-images
```

El MP4 se guardará en la revisión; no se regeneran voz ni ilustraciones.
UltimateBet completo sigue bajo control del operador desde el estudio tras revisar
sus muestras. [Historia](docs/archive/README.md).
