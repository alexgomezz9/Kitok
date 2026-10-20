# Estado vigente de Kitok

Actualizado: 2026-10-20. Fase **Documental enriquecido** en rama
**feature/documentary-motion**, base main bfd43c5. No integrar main ni renderizar
UltimateBet completo en esta fase. Entrega anterior integrada por autorización.

## Fase en curso: audio e investigación

- Catálogo ampliado a20 músicas Incompetech CC BY4.0, archivos locales, hashes,
  páginas/licencias y recibos verificados. 9 voces catalogadas y13 muestras de
  escucha históricas/proveedor; ninguna síntesis nueva. DefaultLooseThread intacto.
- CLI audio selección automática/manual, crossfade/ducking/SFX temporizados;
  preferencias locales de voces y consulta Fish GET. Evidencia: 27tests afectados
  correctos20/10; demo20s -16.00LUFS/-1.99dBTP. Audición humana pendiente.
- [Investigación](docs/motion-research.md): conservarFFmpeg/ASS/Pillow; alternativas
  revisadas, sin instalar otro motor. Three.js queda opcional histórico.
- Compositor/galería/frontend están en implementación y revisión; todavía no
  se consideran entregados. Próximo checkpoint: muestras y controles integrados.
- CI anterior bfd43c5 comprobado20/10: main39291059237 y feature39291054745 success.

Código y guías: **18e6031**, SHA local/remoto comprobado. Manual: [GUIA.md](GUIA.md).

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
- Gate de reorganización del 19/10: **654 Python, 13 React, build y 5 E2E** correctos; studio-check correcto.
  136 tests afectados repetidos por revisor independiente, sin P1/P2 pendientes.
- Promoción exclusiva conserva archivos concurrentes. SHA aprobado bloquea cambios
  antes/durante render. Probes Chromium normal y congelado cierran procesos propios
  con TERM repetido; no garantizan limpieza ante SIGKILL externo/caída del sistema.

## Git, límites y siguiente paso

Integración fast-forward conservando el historial local y remoto; sin force-push.
CI de 5c591f3, f4c46aa y eef9d88 correcta, comprobada el 19/10. CI de 18e6031
en main (39290708250) y en la rama de trabajo (39290651451) en ejecución al consultar;
no se atribuye éxito remoto todavía. No se ha publicado ningún vídeo.

Raíz con 11 archivos públicos necesarios y datos privados locales. Lógica larga en
el paquete, herramientas en scripts/ y ejemplos en examples/. Manuales actuales en
docs/README.md; inventario de automatización en docs/capabilities.md. Historia aislada.
docs-check verifica enlaces, estructura y contratos de ejemplos dentro de verify/CI;
no verifica verdad editorial. Revisión independiente sin hallazgos pendientes.
También make test pasa: 654 pruebas desde el ejecutable pytest.

Incidencia local al pasar por main antigua: Git retiró content_queue.json, entonces
versionado. Restaurado desde 7ff1e8b^:content_queue.json (30 entradas), con copia y
recibo en local/backups/. Sin hash previo no puede acreditarse que no hubiera
cambios locales posteriores. Estado de publicación conservado; no reintentar envíos.
El contrato exige ahora switch --no-overwrite-ignore para evitar esa sobrescritura.

La mejora es real, pero sigue habiendo stock genérico, contraste stock/3D y un
diagrama plano. Sin audición subjetiva ni reproducción audiovisual continua.
No se ha mejorado el episodio completo ni creado un director general multicanal.
Content ID permanece desconocido. No prometer monetización, CTR o retención.

Siguiente trabajo editorial: reunir recursos específicos adicionales y unificar aspecto de
stock/3D antes de ampliar al episodio entero. Google requiere intervención de
cuenta; ese requisito no impide trabajar en edición. Mantener GUIA/estado/Git al día.
