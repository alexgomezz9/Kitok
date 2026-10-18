# Estado vigente de Kitok

Actualizado: 2026-10-18. Rama **feat/documentary-director**, base f9549b7.
Main intacto; sin publicación de vídeos ni merge. Manual: [GUIA.md](GUIA.md).

## Capacidades comprobadas

- Nuevos shorts y largos: Fish/Pexels/FFmpeg nativos. MPT sólo diagnóstico y
  recuperación histórica explícita. Álvaro/Edge no se usa para nuevas voces.
- Estudio local con Short, Vídeo largo y Montaje; almacenamiento sin Google Drive.
- Planes por escena: recursos, gráficos, fotografía animada y reconstrucción 3D
  local con cartas/fichas/cámaras; render secuencial y caché, sin nueva síntesis.
  Los escenarios de póker actuales son Paredes/NioNio. No hay editor de timeline.
- Catálogo Commons con derechos/procedencia por imagen; música local CC BY4.0
  con selección por canal/trabajo, crossfade y ducking. No integrado en formularios.
- CLI YouTube oficial sólo lectura preparado; OAuth real pendiente de cliente
  Desktop/consentimiento. VidIQ reconoce LooseThread pero pide verificación.
  No se gastaron créditos de investigación vidIQ. CTR/CSV aún no importado.

## Evidencia del incremento

- UltimateBet C3:76s,1920×1080,30fps,17escenas, voz/mix idénticos a B anterior;
  decode completo, sin negros, -16,13LUFS/-1,8dBTP. Original652,6s/A/B conservados.
- Revisión visual independiente corrigió mojibake, cartas ambiguas, origen de la
  apuesta y tiempo de revelación. C3 y una salida desde brief revisadas por muestras.
- Fotografía real de Hamilton: Gene Bromberg, CC BY-SA2.0; atribución y cambios
  conservados. Algunas fuentes stock se reescalan; salida1080p no implica fuente1080p.
- Mezcla musical separada18s: -16,24LUFS/-1,8dBTP;15 tests y revisión pasan.
- Promoción exclusiva conserva vídeos/recibos concurrentes. Hash aprobado opcional
  bloquea entradas cambiadas.50 pruebas editoriales/3D y probes de cierre Chromium
  normal y forzado correctos; no garantizan limpieza ante SIGKILL externo/caída SO.
- Gate previo642Python/13React/build/5E2E pasó. Gate sobre últimos guards en curso.
- Checkpoints YouTube0ad6d7b, Commons2acbd67, audio3a86bcd y contrato0097395 subidos;
  CI comprobada correcta hasta audio39137490878. Main y PR1 sin merge.

## Límites y trabajo en curso

C mejora el lenguaje visual, pero sigue usando mucho stock genérico y un diagrama
plano; no se ha mejorado el episodio completo. Sin audición subjetiva ni reproducción
continua. Antes de ampliarlo conviene obtener más recursos específicos y unificar
el tratamiento de stock/3D. Content ID de recursos musicales/desconocidos no probado.

En curso: fijar la salida C en Montaje, cerrar compilación desde brief con catálogo
Pexels ilustrativo, gate final, documentación y checkpoints. No dar por terminados
los archivos sin commit. Próximo chat: verificar este estado y .codex-work/PROJECT_STATE.md.
