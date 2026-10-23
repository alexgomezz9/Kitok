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

## Elegir o investigar

Busca historias curiosas que funcionen con stickman y tengan una buena promesa; personajes, objetivos y conflictos son recursos, no una plantilla obligatoria. No copies ni traduzcas tal cual un vídeo de referencia. Ondol fue rechazado. Investiga YouTube público sin vidIQ y contrasta español e inglés. Distingue idioma hablado de títulos traducidos, largos de shorts y vistas absolutas de rendimiento relativo al canal. Conserva consultas, fecha, enlaces, muestras y límites; no prometas éxito ni llames desocupado a un mercado por una búsqueda vacía.

Propón pocas opciones ordenadas, con evidencia a favor/en contra y un ángulo propio. Antes del guion definitivo acuerda tema, promesa y paquete de título/miniatura cuando siga pendiente. Obtén tú las referencias públicas; pide sólo el enlace o material preciso que no puedas consultar. Guarda análisis propios, no copias de guiones ajenos. Diferencia haber visto una miniatura, leído el guion, visto el montaje y escuchado el audio.

## Escribir y visualizar

Verifica las afirmaciones importantes con fuentes históricas sólidas. Abre con acción, riesgo o pregunta concreta y cumple esa promesa; evita una introducción biográfica larga. La estructura y los giros deben surgir de los hechos. No inventes pensamientos, diálogos ni escenas documentales; declara reconstrucciones. El esquema de trabajo y los puntos de revisión están en la guía.

Comprueba guion → descripción de escena → prompt antes de generar. Conserva identidad editorial estable, palabras de origen y PNG propio por escena. Define antes de la solicitud qué escena corresponde a cada panel. No generes temas genéricos para asignarlos después. Cada recorte necesita revisión narrativa; hashes y dimensiones no entienden la imagen.

## Producir y continuar

Reutiliza voz, alineación e imágenes existentes. Usa el CLI y motor actuales de Kitok, consultando su ayuda real; esta skill no implementa un servicio ImageGen en Python. El agente invoca la herramienta y Kitok conserva/importa archivos. Consulta la guía para requisitos de láminas, recibos y medición. No certifiques un lote a partir de unas muestras ni repitas solicitudes de resultado incierto.

Persiste el estado editorial local en `content/longform/<episodio>/editorial/estado.json` con fase, decisiones/aprobaciones reales y su procedencia, artefactos, dudas y siguiente acción exacta. No modifiques los recibos técnicos para simular aprobación. Usa las autorizaciones vigentes; generar recursos nuevos, cambiar un tema aprobado o publicar no se deduce de guardar este estado.

Al entregar registra qué se generó, revisó y escuchó realmente. Una muestra técnica no acredita un episodio completo. Deja un siguiente paso breve y concreto; no obligues al usuario a reconstruir el contexto o copiar mensajes entre chats.
