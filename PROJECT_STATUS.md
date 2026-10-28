# Estado vigente de Kitok

Actualizado: **2026-10-28**. Rama **main**, tres checkpoints locales previos sobre
origin/main al comenzar esta unidad. Organización de episodios y Freddy guiado.
Sin publicación, merge ni push en este encargo. Manual: [GUIA](GUIA.md),
[carpetas](docs/episode-files.md), [voz](docs/fish-voice.md),
[flujo editorial](docs/youtube-editorial.md).

## Capacidades y evidencia

- Nuevas peticiones Fish compilan `guion_final.txt` con espacios únicos y `[]`
  conservados; hash/política quedan en voice_request. Peticiones previas conservan
  strip-only para reutilizar caché. `guion_lectura_limpia.txt` sirve
  al storyboard, no a TTS. `[]` se transmiten; el texto limpio excluye etiquetas.
  Muestras reales con etiquetas probadas en Freddy; no repetir Jason.
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

## Freddy — producción nocturna autorizada entre fases

Operador27/10revocó la pausa: continuar con registro antes/después en
`content/longform/trazo_004_freddy_krueger/editorial/produccion.md`.
Guion1984palabras,3[break]; estilo B elegido por agente entre3muestras, no
aprobación humana. Storyboard124escenas/1984palabras con cobertura completa,
reloj pendiente. PNG en producción desde el plan fijo; progreso exacto en editorial/estado.json.
El helper de recorte crea un contacto de los PNG reales sin escalarlos, evitando
montajes manuales de hojas para cada lote; nueve pruebas existentes pasadas.
Miniatura nativa1672×941/final1280×720 vista grande y160×90.
Muestra Fish: con énfasis falla el nombre; sin él85/85pero5s actividad sin palabras
ASR/Fish. Kitok recorta4.699s, segundo ASR85/85y controlenergía correcto.
Nueva ampliación `untranscribed_activity`:42tests y revisión independiente
sin hallazgos, muestra real reanudada sin otro Fish. No escucha humana.
Voz larga solicitada UNA vez; audio/SRT/alineación guardados. Proceso externo143
durante ASRlocal; retomado prepare SIN--generate-voice, no otra síntesis.
Voz larga base:13cortes automáticos,13diferencias restantes, montaje bloqueado.
16/16INSERT en párrafos; A/Bcorto84palabras amboslimpios. Nueva revisión
`revisiones/voz_texto_continuo`: MISMOguion/voz/modelo, política nueva espacios
únicos, una solicitud distinta autorizada, proceso desacoplado y exitcode duradero.
Terminó:5discrepancias ASR y0huecos de actividad; ventanas locales recuperan frase
omitida por ASR y grafías. Refinamiento automático acotado en desarrollo, sin
aceptar voz aún. GTA adjunto coincide con texto guardado; también contiene
saltos/etiquetas, así que su presencia sola no prueba causa del defecto.
Siguiente: verificar esa revisión, completar124PNG; montar sólo con audio válido.
No borrar ni volver a escuchar cientos de veces el MP3 crudo de la base. Jason pausa.

## Verificación y límites

Unidad organización:21tests workspace/delivery y14pipeline/word_pipeline pasados;
revisión independiente cerró tres riesgos de limpieza tras corrección/regresiones.
docs-check, higiene y validación de2skills pasados;7dry-runs posteriores vacíos,
5archivos ZIP verificados por CRC/SHA y rutas actuales.419fuentes conservadas.
Se añadió además exclusión con el lease global Native para el mantenimiento de
los proyectos históricos normalizados: regresión y revisión independiente pasadas;
3dry-runs actuales con ese bloqueo, sin candidatos.
Voz anterior:42tests empalmes/integración,40motor y43Native/MPT pasados durante el
encargo anterior. Baseline histórico make verify1194Python/25React no es un gate
completo del código nuevo. No repetir suite global sin motivo. No se ha validado
publicación ni OAuth en esta tarea local; tampoco calidad audiovisual nueva de Freddy.
