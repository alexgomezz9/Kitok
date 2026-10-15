# Estado vigente de Kitok

Actualizado: 2026-10-15. Rama de implementación: **feat/native-production**, base
**80dc92f** (auditoría subida y CI comprobada). Main no se modifica.

## Ahora

Prioridad: comparación UltimateBet A/B de 76 segundos, reutilizando audio y stock
existentes. Original: outputs/longform/loose_thread_ultimatebet_superuser_001.mp4
(652,6 s, 1080p30). Derivados: outputs/evaluation/ultimatebet_ab/.
No se debe volver a sintetizar ese audio para corregir montaje.

Hay cambios locales previos de migración shorts nativos, caché Fish y edición.
Siguen en estabilización/revisión: no confundirlos con la base auditada.
La interfaz y CLI heredados todavía anuncian MPT; migración completa pendiente
de integración y comprobación. Álvaro queda sólo como dato histórico: las voces
nuevas deben ser Fish.

## Evidencia y límites

- Original UltimateBet y audio/cache local inspeccionados; primera hoja de contacto
  muestra overlays por regex y tiempos estimados. A extraído, B en preparación.
- Hardware comunicado: RTX3050 Laptop 4GB y RAM8GB. Usar FFmpeg/Pillow/ASS,
  renders secuenciales y caché; evitar modelos generativos pesados.
- La base 80dc92f pasó 357 Python, 9 React y 4 E2E; esa cifra NO verifica los
  cambios actuales. Ejecutar make verify sobre el siguiente checkpoint.
- APIs existentes autorizadas cuando sean necesarias. Reutilizar antes de gastar;
  sin publicación ni merge a main.

## Continuar

Leer .codex-work/PLAN.md si está disponible. Terminar B y comparar imagen/audio,
cerrar revisión de caché Fish y pruebas de migración, actualizar GUIA y este estado,
hacer commits/push verificados y comprobar CI. No borrar cola/estado/caché/media.
Operación diaria: [GUIA.md](GUIA.md). Protocolo: [docs/development.md](docs/development.md).
