# Producción editorial de historias stickman

Entrada reutilizable: skill `kitok-youtube` en `.agents/skills/kitok-youtube/SKILL.md`.
Perfil vigente: [Trazo Maldito](../presets/youtube_historia_stickman_es.json),
`@trazomalditoes`, ID `UC9h_aIbnfQUo0ylPsPNnbrg`. Es el canal de personajes de
terror en español, separado de Loose Thread. La [investigación histórica genérica](research/2026-10-22-historias/README.md)
es contexto fechado, no una selección vigente para este canal. Estado técnico y
comandos: [guía principal](../GUIA.md) y [adaptador stickman](youtube-stickman-es.md).

## Alcance comprobado

La skill dirige al agente y su lector devuelve contexto local; no es un servicio que fabrique vídeos mientras Codex está cerrado. El motor existente monta, mezcla y renderiza. Investigación, escritura, dirección visual y revisión semántica siguen siendo trabajo editorial del agente y del operador. La generación integrada se invoca con la herramienta del agente; Python no dispone de ese endpoint. La skill `kitok-image-batches` ya conserva láminas, recortes nativos, manifiestos y revisiones. No demuestra un tamaño de lote óptimo ni aprobación semántica automática.

Verifica el CLI y el estado del episodio antes de continuar. No sobrescribas reparaciones ni registros privados; un archivo presente no equivale a un recurso revisado.

## Inicio y continuidad sin explicar todo de nuevo

«Siguiente» dentro de este proyecto encarga elegir y producir el próximo episodio
de Trazo Maldito hasta entrega local. El agente elige personaje, ángulo, título,
miniatura y guion según el perfil y las referencias observadas; utiliza las skills
por fase. No impone otra aprobación para cada decisión delegada. Consulta dudas
materiales, gasto significativo o resultados ambiguos sin recuperación segura.
La revisión del agente se registra como tal; no se atribuye aprobación al operador.
No incluye publicar, programar ni cambiar el canal.

Consulta identidad y datos mediante la [conexión oficial de lectura](integrations/youtube-readonly.md)
en `local/youtube-trazo-maldito`, comprobando el ID remoto. No uses la conexión
de Loose Thread. El 26/10 se verificó acceso real y cero vídeos; esa fecha no prueba
acceso futuro y no hay todavía métricas propias con las que ordenar personajes.

La secuencia de trabajo es investigación/paquete → guion fijado → voz y control
independiente local → storyboard → comparación inicial de enfoques si el estilo
es nuevo → lotes 3×3 revisados → muestra de
montaje → render completo/QA → miniatura/metadatos y entrega. El storyboard puede
esbozarse antes de la voz; sus tiempos se revisan con palabras reales. Evita
producir todo el lote antes de detectar un fallo de voz o alineación. Mantén las
referencias de estilo/identidad fijadas, con variación de composición por escena.

Duración del canal: planificar historias útiles para 9–12 minutos y comprobar
que el MP4 final supere estrictamente 480 segundos. No confundir estimaciones
con duración real ni rellenar con pausas. YouTube admite anuncios intermedios
en vídeos monetizados de ocho minutos o más; la duración no acredita elegibilidad
del canal ni garantiza anuncios. Fuente: [YouTube](https://support.google.com/youtube/answer/6175006?hl=es).

Dentro del proyecto Kitok, pedir «Usa $kitok-youtube para investigar el próximo episodio» o «Continúa el episodio X». Las skills locales se descubren desde `.agents/skills` del repositorio; una skill de WSL no aparece automáticamente en una carpeta Windows sin relación. [Documentación oficial](https://learn.chatgpt.com/docs/build-skills). El lector compacto se ejecuta desde la raíz:

```bash
.venv/bin/python .agents/skills/kitok-youtube/scripts/context.py
.venv/bin/python .agents/skills/kitok-youtube/scripts/context.py --episode content/longform/stickman_video1 --scene escena_063 --scene escena_064
```

Devuelve perfil, recursos presentes, recuentos, estado editorial si existe y sólo los prompts solicitados. No lee credenciales, genera medios, modifica recibos ni asume aprobaciones. Señala estados originales `not_generated` que ya tienen archivo: esa contradicción exige reconciliación, no otra generación automática.

Cada episodio conserva `editorial/estado.json` dentro de su carpeta local ignorada por Git. El agente lo guarda al terminar una fase, con este contrato pequeño:

```json
{
  "version": 1,
  "phase": "research",
  "updated": "2026-10-22",
  "decisions": [],
  "approvals": [],
  "artifacts": [],
  "unresolved": [],
  "next_action": "Comparar las dos historias propuestas antes de fijar el guion"
}
```

Cada aprobación identifica qué aprobó quién y con qué mensaje/artefacto; no se infiere de un archivo o del silencio. Artefactos: rutas relativas y, para guion/plan/medios, hashes cuando corresponda. No se copia la conversación completa. Las fases útiles son investigación, packaging, guion, escenas, imágenes, narración, montaje, QA y entrega; las existentes no se repiten si sus entradas siguen vigentes.

## Investigación y memoria del canal

Conservar un breve paquete por selección: consultas de YouTube y fecha; vídeos EN/ES con URL, idioma hablado comprobado o pendiente, duración, fecha y visitas; comparación con el propio canal cuando sea posible; fuentes históricas y dudas. Una búsqueda vacía no demuestra baja saturación. Shorts, podcasts largos, doblajes y vídeos de 8–12 minutos compiten de distinta manera. YouTube puede traducir títulos ingleses: comprobar idioma en el vídeo/transcripción antes de contarlos como español.

Una referencia útil aporta una lección concreta: qué promete título/miniatura, qué hace el primer minuto, cómo introduce conflicto, resuelve preguntas y distribuye información visual. Guardar análisis propio y timestamps si se observaron. No copiar guiones ni convertir recursos de terceros en recursos propios. Un título visto no permite afirmar cómo narra el vídeo. Las lecciones pasan al perfil o guía sólo cuando sean útiles y estén respaldadas; las métricas permanecen como snapshots fechados.

Priorizar oportunidad narrativa, competencia observada, credibilidad de fuentes y
viabilidad visual. Visitas y multiplicadores orientan; no pronostican ingresos o
éxito. Antes de escribir entero se fija la promesa y un concepto de título/miniatura
que el vídeo pueda cumplir; el agente decide cuando esté delegado. Identifica qué
película/continuidad se cuenta y distingue ficción de historia de producción.
El objetivo es cubrir los personajes famosos y narrar su evolución con stickman:
origen, infancia cuando exista, crecimiento y transformaciones. No rellenar años
sin relato en las obras ni reemplazar esta historia por anécdotas de rodaje.
No elegir un tema sólo por ser el mayor número de una tabla.

## Relato inmersivo y estilo del canal

La voz narra la historia del personaje desde dentro, sin «en las películas»,
«en esta entrega», comentarios al espectador ni resumen de saga. Registrar canon,
títulos y fuentes en notas; resolver contradicciones sin inventar puentes. Las
instrucciones Fish van separadas del texto hablado y de los subtítulos según
el contrato soportado; ver [voz](fish-voice.md).

Stickman significa cabeza simple y cuerpo/extremidades de trazo fino visibles,
con máscara/vestuario como identidad. Una ilustración cartoon genérica no basta.
Terror contextual permite sombras, amenazas, armas y sangre estilizada; no borrar
las consecuencias de una escena violenta ni inventarlas sólo para impresionar.
Antes de un estilo nuevo se comparan tres enfoques del mismo momento: línea limpia,
tinta/sombras y viñeta con rojo selectivo. Después se verifica acción/reacción/objeto
con el elegido y se fijan referencias. Con estilo aceptado se reutiliza.

Sin delegación se espera la elección inicial; con «siguiente automático» o «no
preguntes», el agente elige, registra su revisión y sigue. No atribuir al operador
una aprobación que no dio. La música se prepara con perfil horror antes del montaje,
con baja presencia bajo la voz y escucha de muestra; ver [audio](audio.md).

## Guiones con historia y hooks

Empezar donde existe una decisión, un riesgo o una contradicción comprensible sin conocer al personaje. Dar pronto el objetivo y qué se puede perder. Retrasar antecedentes hasta que aclaren lo que está ocurriendo. Cada bloque debe cambiar la situación, añadir una dificultad o resolver una pregunta; evitar una lista de fechas disfrazada de narración.

Escribir primero una escaleta causal y verificar las afirmaciones que sostienen sus giros. Los reenganches abren preguntas reales; no prometer una revelación inexistente cada treinta segundos. Elegir el final y comprobar que responde al principio. Leer el guion en voz alta y ajustar a la duración de narración prevista. Si un caso sólo sostiene seis minutos, no rellenar hasta doce. Distinguir hecho documentado, inferencia y reconstrucción; no inventar diálogos o estados mentales para mejorar el drama.

## Imágenes: rapidez con correspondencia narrativa

Antes de generar, comparar por escena el fragmento narrado, sujeto/acción, lugar, época y objetos de su descripción. Ejemplo observado el 22/10: la narración de `escena_064` describe a un principiante golpeando sin éxito, mientras su prompt describe a un adulto experto enseñando. No corregido aquí: la revisión semántica debe empezar antes de ImageGen. No basta con que el dibujo cumpla un prompt equivocado.

El usuario informó que una tanda externa de 39 recortes se produjo con temas generales y asignación posterior. Es evidencia de una vía rápida, no de fidelidad ni de un número determinado de solicitudes. No deducir su procedencia únicamente de las dimensiones de los PNG.

Para las nuevas láminas, cada trabajo persiste ANTES de generar: IDs de escenas, fragmentos narrados, prompts exactos, referencias, orden y cajas de paneles. Cada panel compone por separado en 16:9. Una escena clave o compleja puede producirse individualmente. No se mostrarán cuadrículas en el vídeo ni se asociarán recortes después por parecido general.

Después: conservar lámina original; recortar separadores/cabeceras sin amputar dibujo; validar geometría; escalar sólo cuando aporte una salida utilizable; guardar PNG individual y metadatos del tamaño nativo, crop, escalado y hash. Generar contacto de revisión. Evaluar caras, objetos, acción, época y coherencia, tanto estático como con los movimientos reales de Kitok. Un fallo aislado se repara por panel; no se regenera un lote aceptado. Registrar solicitudes ambiguas y reconciliarlas antes de repetir.

La herramienta integrada aquí no expone `n` ni lista de prompts independientes. La skill de lotes usa láminas recortables con asignación previa y validación local; todavía no se ha demostrado qué tamaño gana en una comparación de rendimiento. Comparar tiempo total por escena aceptada, incluyendo revisión y repeticiones, y calidad bajo zoom/paneo. La ruta de ChatGPT web relatada por el usuario tampoco tiene medición comparable en este equipo. No prometer cero tokens ni confundir cuota de suscripción con precio de API. Seleccionar la superficie y agrupación por resultados, sin contratar otra API como requisito.

## Entrega y aprendizaje

Conservar una imagen distinta por escena editorial y separar IDs de los tiempos. Reutilizar voz/alineación y mantener límites de duración, integridad y hashes. Utilizar el motor actual y los procedimientos vigentes para importar, aprobar estilo, renderizar y revisar. No editar recibos para forzar que el sistema continúe.

La carpeta `entrega/` separa los seis archivos de uso del trabajo interno mediante
`scripts/stickman_delivery.py`; consultar [guía](../GUIA.md#estilo-y-entrega-de-trazo-maldito).
No borrar cachés mientras queden reparaciones que puedan necesitarlas.

Una muestra de 45–60 segundos valida aspectos concretos, después hay que comprobar el MP4 completo: sincronización, pronunciación, legibilidad, continuidad, mezcla y ausencia de errores semánticos. Tras publicar manualmente, si el usuario aporta métricas autorizadas, contrastar promesa, clics y retención sin atribuir causalidad a una miniatura por un solo resultado. Este flujo no publica ni cambia el canal por su cuenta.
