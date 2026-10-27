# Estado vigente de Kitok

Actualizado: **2026-10-27**. Rama **main**, tres checkpoints locales previos sobre
origin/main al comenzar esta unidad. Organización de episodios y Freddy guiado.
Sin publicación, merge ni push en este encargo. Manual: [GUIA](GUIA.md),
[carpetas](docs/episode-files.md), [voz](docs/fish-voice.md),
[flujo editorial](docs/youtube-editorial.md).

## Capacidades y evidencia

- Stickman envía `guion_final.txt.strip()` a Fish. `guion_lectura_limpia.txt` sirve
  al storyboard, no a TTS. `[]` se transmiten; el texto limpio excluye etiquetas.
  Sintaxis documentada; muestra real con etiquetas aún pendiente, no repetir Jason.
- `local_asr_autocut` en init nuevo: voz cruda → ASR local → cortes anclados en
  copia PCM → nueva ASR → sólo después reloj/mezcla/montaje. Reemplazos, omisiones
  y ambigüedades bloquean; no prometemos reparar cualquier fallo sin revisión.
- Pruebas reales anteriores: Jason/Loose Thread × directo/timestamps sobre64
  palabras, S2.1-free. Habla extra presente en respuesta cruda; no sólo montaje.
  No equivaler web Drama3 y API S2.1. Muestra Drama3 API: HTTP402, sin retry.
- Loose Thread largo, shorts y stickman generan con Native/Fish/FFmpeg. MPT sólo
  recuperación histórica explícita; no se desinstaló servicio alguno.
- `scripts/stickman_delivery.py organize`: índice/carpetas comunes, limpieza
  explícita de cachés y láminas resueltas, archivo de revisiones cerradas con
  fuentes/hashes y restauración. init/montaje generan/actualizan índice; no borran
  al guardar ni archivan trabajos automáticamente. Contrato en docs/episode-files.md.

## Jason — STANDBY por encargo del operador

`content/longform/trazo_003_jason_voorhees/LEEME.md` es el índice actual.
`voz_reparada.wav`:435.728708s (7:16), PCM48k mono; original Fish MP3 intacto.
24cortes automáticos +1corte editorial ambiguo +2frases/19palabras recuperadas.
Segunda ASR completa anterior:0inserciones,14diferencias; no escucha del agente
ni coincidencia acústica perfecta demostrada. NO hay vídeo nuevo con esta voz.
`entrega/voz_limpia_8min__video.mp4` conserva errores: referencia visual anterior,
no final corregido. Diagnósticos en `local/pruebas/trazo_003_jason_voorhees/`.
No seguir reparándolo/renderizarlo ahora. Rehacer en futuro encargo con estética
stickman más terrorífica y duración útil real >480s, sin ralentizar para cumplir.

## Organización aplicada

Siete episodios comparten carpetas e índice; los tres Native históricos tienen
`configuracion.json`, `guion_final.txt`, `titulo.txt`. Sus rutas script_file obsoletas
se corrigieron; las tres definiciones cargan sin proveedores. Originales en archivo.
Se comprobaron419fuentes por SHA256 sin pérdidas/cambios de contenido.
Revisiones cerradas de Jason/Myers/Antigüedad archivadas fuera del árbol diario;
vídeos únicos conservados visibles, PNG definitivos intactos, láminas resueltas
retiradas. Pruebas de voz y configs de ensayo fuera de episodios. Intermedios de
pruebas cerradas, mezclas regenerables y temporales Kitok retirados; recursos ASR,
stock, música, credenciales y galerías útiles conservados. Manifiestos y recuentos:
`local/cleanup/2026-10-27-organizacion/summary.json` y reportes asociados.
Limpieza anterior de Jason/tmp: `local/cleanup/2026-10-27-jason/`, no repetirla.

## Freddy — fase2 terminada, PARADA

`content/longform/trazo_004_freddy_krueger/editorial/investigacion_y_escaleta.md`:
seis fuentes, continuidad clásica,10bloques y presupuesto aproximado1950palabras.
Guion/voz/imágenes/vídeo todavía no generados. Perfil guided_exercise activo.
Próximo «siguiente»: escribir/revisar guion, explicar inputs/outputs y parar antes
de voz/imágenes. Automático sólo por petición expresa del operador.

## Verificación y límites

Unidad organización:20tests workspace/delivery y14pipeline/word_pipeline pasados;
revisión independiente cerró tres riesgos de limpieza tras corrección/regresiones.
docs-check, higiene y validación de2skills pasados;7dry-runs posteriores vacíos,
5archivos ZIP verificados por CRC/SHA y rutas actuales.419fuentes conservadas.
Voz anterior:42tests empalmes/integración,40motor y43Native/MPT pasados durante el
encargo anterior. Baseline histórico make verify1194Python/25React no es un gate
completo del código nuevo. No repetir suite global sin motivo. No se ha validado
publicación ni OAuth en esta tarea local; tampoco calidad audiovisual nueva de Freddy.
