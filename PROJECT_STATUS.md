# Estado vigente de Kitok

Actualizado: 2026-10-19. Rama **feat/documentary-director**, base f9549b7.
Main intacto; sin publicación ni merge. Manual: [GUIA.md](GUIA.md).

## Disponible y comprobado

- Shorts/largos nuevos: Fish + FFmpeg nativos y Pexels cuando corresponde.
  MPT sólo diagnóstico/recuperación histórica; Álvaro/Edge no se usa para voz nueva.
- Estudio local: Short, Vídeo largo, Montaje y guía única; sin Google Drive.
- Montaje: gráficos, fotografía animada y reconstrucción 3D secuencial/cacheada.
  Escenarios de póker aún restringidos a Paredes/NioNio; sin editor de timeline.
- Compilador: brief explícito → selección de recursos por entidad/función → plan.
  Comprueba licencia, hash, cobertura y repetición; un faltante bloquea el plan.
  No investiga ni interpreta un guion arbitrario. CLI sin voz, red ni publicación.
- Biblioteca Commons + registro offline Pexels. Procedencia/derechos conservados;
  stock sólo ilustrativo. Un recurso de menor resolución exige revisión expresa.
- Música: 4 pistas CC BY 4.0, selector por trabajo/canal, crossfade, ducking y SFX.
  CLI independiente, no activado en formularios ni en el audio de comparación.
- YouTube: OAuth Desktop PKCE y CLI oficial sólo lectura preparados. Conexión real
  pendiente de cliente/consentimiento Google. VidIQ reconoce LooseThread y pide
  verificación. Sin créditos de investigación gastados. CTR/CSV aún no importado.

## Evidencia del 18 y revalidación del 19 de octubre

- C final: outputs/evaluation/ultimatebet_cinema/B_improved.mp4; 76 s, 1920×1080, 30 fps,
  17 escenas. A es el B anterior. Original de 652,6 s y todas las versiones conservados.
- Flujo real brief→plan→render; voz/mix idénticos a A, decode completo correcto,
  sin negros, -16,13LUFS/-1,8dBTP. Último ensamblado 14,49 s, 17 planos reutilizados,
  NVENC y cero proveedores; QA aparte. Reconstrucciones 3D se renderizaron antes.
- Revisión visual independiente corrigió UTF8, cartas ambiguas, origen de apuesta,
  rótulos y tiempo de revelación. Final coincide byte a byte con el archivo revisado.
  Chromium real reprodujo A/B a 62,8 s; créditos HTTP 200, sin errores de página.
- Foto Hamilton: Gene Bromberg, CC BY-SA 2.0; cambios/licencia en CREDITS.md y vídeo.
  Algunas fuentes se reescalan: salida 1080p no implica fuentes 1080p.
- Mezcla musical separada 18 s: -16,24LUFS/-1,8dBTP; 15 tests/revisión correctos.
- Gate final: **649 Python, 13 React, build y 5 E2E** correctos, reejecutados el 19/10; studio-check correcto.
  136 tests afectados repetidos por revisor independiente, sin P1/P2 pendientes.
- Promoción exclusiva conserva archivos concurrentes. SHA aprobado bloquea cambios
  antes/durante render. Probes Chromium normal y congelado cierran procesos propios
  con TERM repetido; no garantizan limpieza ante SIGKILL externo/caída del sistema.

## Git, límites y siguiente paso

Checkpoints coherentes subidos durante el trabajo. Motor 3D ef5c164: CI 39138920635
correcta, comprobada el 19/10. El checkpoint del compilador se verifica y sube al
cerrar esta unidad; su resultado remoto se registrará tras el push.
PR1 histórica sigue en borrador sin merge; esta rama tampoco se fusiona a main.

La mejora es real, pero sigue habiendo stock genérico, contraste stock/3D y un
diagrama plano. Sin audición subjetiva ni reproducción audiovisual continua.
No se ha mejorado el episodio completo ni creado un director general multicanal.
Content ID permanece desconocido. No prometer monetización, CTR o retención.

Siguiente trabajo: reunir recursos específicos adicionales y unificar aspecto de
stock/3D antes de ampliar al episodio entero. Google requiere intervención de
cuenta; ese requisito no impide trabajar en edición. Mantener GUIA/estado/Git al día.
