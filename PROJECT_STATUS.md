# Estado vigente de Kitok

Actualizado: **2026-10-27**. Rama **main**; encargo activo: auditoría y mejoras de
Trazo Maldito (voz, skills/estilo, música, archivos y rendimiento). No publicar.
Manual: [GUIA](GUIA.md), [flujo editorial](docs/youtube-editorial.md),
[audio](docs/audio.md).

## Evidencia vigente

- Voz/Fish y Native/FFmpeg conservan fuentes, hashes y bloqueo por episodio.
  Narración, dirección visual e invocación ImageGen son trabajo del agente;
  mezcla, cámara, tiempos, montaje y QA los ejecuta Kitok sin LLM por plano.
- Biblioteca:24pistas Kevin MacLeod/CC BY4.0, ocho candidatas de horror verificadas
  en caché27/10. Cuatro nuevas descargadas con licencia individual/catálogo/hash.
  53tests de biblioteca pasados; elección no acredita escucha ni retención.
- Perfil del canal: historias9–12min, MP4estrictamente>480s, una entrega subtitulada,
  identidad@trazomalditoes/UC9h_aIbnfQUo0ylPsPNnbrg separada de Loose Thread.
  OAuth read-only verificado26/10; no revalidado hoy ni necesario para este encargo.
- Baseline previo:1154Python/25React, TypeScript/Vite y studio-check pasados.
  Gates nuevos de la auditoría aún en curso; no equiparar historial con código actual.

## Jason: QA técnico pasado, voz pendiente

`content/longform/trazo_003_jason_voorhees/revisiones/voz_limpia_8min` conserva
109PNG,1411palabras y115planos. Recuperación final comprobada27/10:
subtitulado497.733333s/14932frames,−16.03LUFS/−1.75dBTP, audio idéntico al base.
No repetir render/Fish como diagnóstico ni afirmar escucha completa del agente.

El corte anterior401.810930–410.892653s ytempo0.94 conservó fuentes, pero NO
resuelve todas las anomalías. Reconocimiento local independiente detecta inserciones
candidatas repetidas («montantani», variantes) ausentes del guion. La voz requiere
revisión; `final_video_ready=false`. Investigación local y protección previas al
montaje en curso. No se envió audio al ASR remoto; operador eligió alternativa local.

Rendimiento real: mezcla2m34s; animar115planos16m50s; unir8s; QA base3m54s;
segunda codificaciónASS2m41s. NVENC utilizado; escala4K/cámara/filtros son CPU.
Comparación GTA6 no verificable: no se encontraron sus artefactos actuales.

Siguiente: cerrar control local de voz, revisión independiente y pruebas; consolidar
entrega compacta y recuperación de subtítulos. Conservar cachés mientras haya posible
reparación de audio. No atribuir aprobación audiovisual a QA técnico.
