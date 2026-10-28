---
name: kitok-youtube
description: Investiga y produce episodios narrativos en español con ilustraciones stickman dentro de Kitok; conserva reglas del canal, evidencia editorial y estado para continuar entre chats. Úsala al pedir ideas, investigar referencias o arrancar y continuar estos episodios.
---

# Producir YouTube con Kitok

Trabaja en el repositorio real que contiene este archivo. Lee `PROJECT_STATUS.md` y el tramo pertinente de `GUIA.md`; conserva trabajo de otros chats. Una reparación en curso no autoriza modificar sus archivos. No confundas el estado técnico del repositorio con el estado editorial del episodio.

Ejecuta desde la raíz el lector compacto, sin proveedores ni escrituras:

```bash
.venv/bin/python .agents/skills/kitok-youtube/scripts/context.py
# Para continuar un episodio concreto:
.venv/bin/python .agents/skills/kitok-youtube/scripts/context.py --episode content/longform/stickman_video1
```

Lee el [perfil del canal](../../../presets/youtube_historia_stickman_es.json). Consulta sólo la fase necesaria de la [guía editorial](../../../docs/youtube-editorial.md) y las investigaciones allí enlazadas. No vuelvas a pedir preferencias o recursos que ya estén registrados. El perfil no acredita propiedad de un canal ni permisos de publicación.

## Ejercicio guiado vigente y trabajo práctico

El operador pidió el27/10 recorrer el próximo episodio una fase cada vez. Lee
`workflow.guided_exercise` del perfil y `editorial/estado.json`: mientras esté
activo, «siguiente» avanza UNA fase y se detiene. Explica entradas con rutas,
qué hace agente/Kitok, salidas reales y comprobación mínima. No producir guion,
voz, imágenes o vídeo de fases posteriores. Sólo una petición expresa de volver
a automático levanta esta pausa entre fases; no preguntar otra vez lo resuelto.

Prioriza pruebas focales y una muestra real útil. No repetir suites grandes sin
cambio/fallo material. Antes de añadir código, identifica qué operación concreta
no resuelve Kitok y si basta con reutilizar un comando. Durante el ejercicio se
retiran capas redundantes sólo tras ver entradas/salidas y comprobar su uso.

## Organización y reparto de trabajo

Sigue [carpetas de episodios](../../../docs/episode-files.md): entradas y entrega
visibles, índice `LEEME.md`, carpetas comunes; pruebas en `local/pruebas/EPISODIO/`.
Usa `scripts/stickman_delivery.py organize EPISODIO` para inspeccionar y `--apply`
para limpieza autorizada tras revisar el informe. Archiva revisiones cerradas con
`--archive-revisions`; no archivar rutas que consuman entradas vigentes.
Conserva PNG finales, guion, voz original, prompts, manifiestos y licencias.
Retira láminas/crops resueltos; no acumular variantes y muestras en el episodio.
El agente investiga, escribe guion, decide prompts y genera/revisa imágenes;
Kitok procesa voz, tiempos, mezcla, subtítulos y montaje con sus comandos.
Si falla un comando, corregir el defecto reutilizable y reanudar sin repetir
proveedores. Documentar cualquier recuperación manual; no presentarla como
capacidad automática ni repetirla como rutina en cada vídeo.

Jason `trazo_003_jason_voorhees` está en standby por encargo27/10: rehacer sólo en
un encargo futuro con nueva estética y duración útil real >8min. Continuar ahora
Freddy por fases; el audio reparado7:16 no autoriza volver a montar Jason.

## Encargo completo: «siguiente»

Dentro de este canal, «siguiente» encarga el próximo episodio completo hasta entrega
local. Usa `yt-video-workflow` como coordinación y carga sólo la skill de la fase
activa. El perfil fija las decisiones delegadas: elige personaje, promesa y paquete
cuando el operador delegue, sin imponer confirmaciones en cada paso. Consulta sólo
dudas materiales, gasto significativo o bloqueos no recuperables; publicar requiere
encargo separado. Identifica Trazo Maldito por su ID, nunca por la conexión de Loose
Thread. Para leer datos actuales usa el CLI oficial con el directorio del perfil y
comprueba ID remoto; un snapshot o `status` local no acredita acceso vigente.

Al iniciar o continuar lee `editorial/estado.json`. Al cerrar cada fase registra
decisión, procedencia, hashes de entradas/salidas y siguiente acción. No cambies el
guion fijado después de generar voz/imágenes sin una revisión nueva. Primero revisa
voz/alineación y una muestra visual/audiovisual antes de ampliar. Los scripts hacen
IDs, cobertura, recortes, tiempos y render; el agente decide historia y revisa
significado. No recrees esas operaciones escribiendo otro generador.

## Elegir o investigar

Busca personajes de terror y ángulos propios según el perfil: historia ficticia y
creación detrás de cámaras son capas distintas. Fija película/continuidad y fuentes
antes de mezclar versiones. No copies ni traduzcas tal cual un vídeo de referencia.
La prioridad es narrar la vida/evolución del personaje, desde su infancia cuando
las obras la cuentan; no sustituirla por curiosidades de producción ni inventar
un crecimiento ausente. Se cubrirán los personajes principales con el tiempo:
las referencias ayudan a narrar y visualizar, no obligan a perseguir tendencias.
Investiga YouTube público sin gastar vidIQ y contrasta español e inglés. Distingue
idioma hablado de títulos traducidos, largos de shorts y vistas absolutas de
rendimiento relativo al canal. Conserva consultas, fecha, enlaces, muestras y límites;
no prometas éxito ni llames desocupado a un mercado por una búsqueda vacía.

Compara pocas opciones con evidencia a favor/en contra y un ángulo propio; si la
selección está delegada, elige y registra el motivo antes del guion definitivo.
Obtén tú las referencias públicas. Abre e inspecciona miniaturas; intenta reproducir
secuencias relevantes y anota los intervalos realmente vistos, audio escuchado y
limitaciones. Un título/transcript no demuestra montaje ni sonido. Guarda análisis
propios, no copias de guiones ajenos. Sin métricas propias, declara esa limitación.

## Voz narrativa y dirección Fish

En Trazo Maldito se cuenta la historia desde dentro: «Jason volvió al lago», no
«en la segunda película Jason vuelve». Títulos/continuidad/fuentes quedan en notas;
no ocultes contradicciones entre versiones inventando puentes. No hagas reseña,
resumen de entregas ni explicación del rodaje salvo encargo expreso. Lee las reglas
actuales del perfil antes de escribir. Terror admite amenaza, persecución, sangre
estilizada y consecuencias cuando lo exige la historia; no infantilices el relato
ni añadas atrocidades que el canon no cuenta.

Aplica `narrative_rules.natural_prose` del perfil: acciones y causas concretas, sintaxis variada; evita encadenar «No era X. No era Y. Era Z». Esta preferencia se aplica al redactar y releer con `yt-script`; no implementar comprobaciones regex, linters ni filtros posteriores para imponerla. Conservar negaciones necesarias para los hechos. Para figuras y crecimiento sigue `images.character_continuity` en protagonistas y secundarios.

En TODA síntesis nueva de este flujo, usa Kitok con `collapse_whitespace_v1`:
parte de `guion_final.txt`, convierte saltos/tabulaciones/espacios repetidos en un
único espacio y conserva palabras y etiquetas `[]`. El guion fuente permanece
legible con párrafos; no envíes el archivo de lectura limpia como sustituto.
Comprueba política y hash del texto enviado en `voice_request.json`. No cambies
recibos antiguos ni regeneres voces existentes por esta regla. Mantén el control
local de audio: el resultado bueno de Freddy no garantiza ausencia de fallos.

Para interpretación Fish consulta [voz y fidelidad](../../../docs/fish-voice.md).
Comprueba el modelo efectivo: S2 usa corchetes como `[break]`,
`[long-break]`, `[whispering]`, `[emphasis]`, `[scared]` o `[sad]`; no asumir `[pausa]`
ni una duración exacta. Dosifica instrucciones y prueba una muestra cuando se
autorice voz nueva. Mantén guion hablado, instrucciones TTS y transcript esperados
separados mediante el contrato realmente soportado; no metas etiquetas a mano en
`guion_final.txt` si van a contaminar alineación/subtítulos. Nunca resintetices un
episodio existente sólo para añadirlas. El ASR independiente reconoce SIN recibir
el guion; después compara, señala discrepancias y bloquea antes de renderizar.
Usa `voice.transcript_verification=local_asr_autocut` en episodios nuevos: Kitok
recorta inserciones con anclas y silencios en una copia y vuelve a reconocerla
antes de permitir el montaje. Omisiones/reemplazos y residuos ambiguos bloquean;
no los borres para conseguir un informe verde. No demuestra fidelidad una
alineación forzada, ni convierte cada diferencia ASR en un corte seguro.
No encubras anomalías de voz con música.

## Aprobar el estilo antes de ampliar

Para un estilo nuevo muestra tres enfoques del MISMO momento narrativo, todos
stickman (limpio contrastado, tinta/sombras, viñeta con rojo selectivo); después
comprueba acción/reacción/objeto con el elegido. Cuerpos de trazo fino y cabezas
simples reconocibles, máscara/vestuario coherentes; cartoon de cuerpo ancho o una
ilustración sencilla no bastan. Sangre estilizada/armas/sombras cuando correspondan,
sin uniformar todos los planos ni perder claridad móvil. Fija ancla y referencias
tras la elección antes de los lotes. Con estilo ya aceptado, reutilízalo.

Si no hay delegación, espera la elección visual inicial antes de producir el lote
completo. «Siguiente automático», «no preguntes» o delegación equivalente autorizan
al agente a elegir/revisar y seguir; registra elección del agente, nunca aprobación
humana inventada. No reabras decisiones resueltas ni rediseñes episodios terminados.

## Escribir y visualizar

Verifica las afirmaciones importantes con fuentes históricas sólidas. Abre con acción, riesgo o pregunta concreta y cumple esa promesa; evita una introducción biográfica larga. La estructura y los giros deben surgir de los hechos. No inventes pensamientos, diálogos ni escenas documentales; declara reconstrucciones. El esquema de trabajo y los puntos de revisión están en la guía.

Comprueba guion → descripción de escena → prompt antes de generar. Conserva identidad editorial estable, palabras de origen y PNG propio por escena. Define antes de la solicitud qué escena corresponde a cada panel. No generes temas genéricos para asignarlos después. Cada recorte necesita revisión narrativa; hashes y dimensiones no entienden la imagen.

## Montaje con una entrada y entrega compacta

Con guion/voz/ASR, storyboard, imágenes y configuración fijados, invoca el recorrido
Kitok `prepare --reuse-images` y `produce --reuse-images --subtitles`. No rehagas
mezcla, cámara, timestamps, concatenación, ASS o QA con scripts ad hoc. Un defecto
reproducible se corrige en Kitok y se reanuda con recibos; no repetir proveedores
para resolver un fallo local. Consulta progreso por etapas y recibo final sin
volcar planes/logs enteros ni hacer llamadas de modelo por plano.

Sigue `workflow.efficient_close`: espera procesos locales con consultas compactas; prepara notas durante las fases y cierra una vez QA y bundle estén listos. Reserva auditorías adicionales, reproducción completa en navegador y revisiones independientes para cambios/fallos o encargos que lo justifiquen; conserva los controles automáticos de cada entrega.

Fija música `horror` para episodios nuevos según el perfil antes de mezclar. Al
terminar, prepara metadatos finales y usa `scripts/stickman_delivery.py bundle`:
operador recibe `entrega/`, no miles de archivos internos. Los originales y
licencias permanecen fuera; `clean-cache` primero simula y sólo se aplica tras
resolver reparaciones, con hashes/locks y sin borrar fuentes. No afirmes que esta
organización constituye una limpieza automática ni que un QA técnico pasó el ASR.

## Producir y continuar

Reutiliza voz, alineación e imágenes existentes. Usa el CLI y motor actuales de Kitok, consultando su ayuda real; esta skill no implementa un servicio ImageGen en Python. El agente invoca la herramienta y Kitok conserva/importa archivos. Consulta la guía para requisitos de láminas, recibos y medición. No certifiques un lote a partir de unas muestras ni repitas solicitudes de resultado incierto.

Persiste el estado editorial local en `content/longform/<episodio>/editorial/estado.json` con fase, decisiones/aprobaciones reales y su procedencia, artefactos, dudas y siguiente acción exacta. No modifiques los recibos técnicos para simular aprobación. Usa las autorizaciones vigentes; generar recursos nuevos, cambiar un tema aprobado o publicar no se deduce de guardar este estado.

Al entregar registra qué se generó, revisó y escuchó realmente. Una muestra técnica no acredita un episodio completo. Deja un siguiente paso breve y concreto; no obligues al usuario a reconstruir el contexto o copiar mensajes entre chats.
