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

## Escribir y visualizar

Verifica las afirmaciones importantes con fuentes históricas sólidas. Abre con acción, riesgo o pregunta concreta y cumple esa promesa; evita una introducción biográfica larga. La estructura y los giros deben surgir de los hechos. No inventes pensamientos, diálogos ni escenas documentales; declara reconstrucciones. El esquema de trabajo y los puntos de revisión están en la guía.

Comprueba guion → descripción de escena → prompt antes de generar. Conserva identidad editorial estable, palabras de origen y PNG propio por escena. Define antes de la solicitud qué escena corresponde a cada panel. No generes temas genéricos para asignarlos después. Cada recorte necesita revisión narrativa; hashes y dimensiones no entienden la imagen.

## Producir y continuar

Reutiliza voz, alineación e imágenes existentes. Usa el CLI y motor actuales de Kitok, consultando su ayuda real; esta skill no implementa un servicio ImageGen en Python. El agente invoca la herramienta y Kitok conserva/importa archivos. Consulta la guía para requisitos de láminas, recibos y medición. No certifiques un lote a partir de unas muestras ni repitas solicitudes de resultado incierto.

Persiste el estado editorial local en `content/longform/<episodio>/editorial/estado.json` con fase, decisiones/aprobaciones reales y su procedencia, artefactos, dudas y siguiente acción exacta. No modifiques los recibos técnicos para simular aprobación. Usa las autorizaciones vigentes; generar recursos nuevos, cambiar un tema aprobado o publicar no se deduce de guardar este estado.

Al entregar registra qué se generó, revisó y escuchó realmente. Una muestra técnica no acredita un episodio completo. Deja un siguiente paso breve y concreto; no obligues al usuario a reconstruir el contexto o copiar mensajes entre chats.
