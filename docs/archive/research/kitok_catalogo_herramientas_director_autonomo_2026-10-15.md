> ARCHIVO HISTÓRICO — conservado el 19 de octubre de 2026.
> No es un manual vigente ni acredita capacidades actuales.
> Consulta el [índice de documentación actual](../../README.md).

# Kitok — Catálogo de herramientas y arquitectura de director audiovisual autónomo

**Investigación y handoff para Codex Work — 15 octubre 2026.**
**Objetivo:** pasar de vídeo largo basado en stock + overlays repetitivos a montaje editorial semántico con imágenes exactas, animación 2D/2.5D, gráficos, escenas reconstruidas identificadas como tales, y una segunda pasada creativa de Codex que vea y mejore el MP4. Sin rehacer la infraestructura de Kitok ni generar nuevas voces pagadas al corregir escenas.

## 0. Contexto y límites REALES

- Equipo del operador, salida de `nvidia-smi`/`free -h`: **RTX 3050 Laptop, 4.096 MiB de VRAM; RAM total 7,6 GiB, 4,7 GiB available; 2 GiB swap**; Ubuntu bajo WSL. No es una máquina de generación intensiva de vídeo IA. Vigilar picos de RAM de Node/Chromium/PyTorch y evitar correr varios modelos simultáneamente.
- Repositorio `alexgomezz9/Kitok`; ya existe motor Native, Pexels, Fish, FFmpeg, React, pruebas y módulos locales no confirmados en `src/kitok/editing/`, `src/kitok/rendering/native.py`, etc. **Leer SIEMPRE el checkout local**, GitHub puede ir detrás. El usuario informó que UltimateBet ya se generó y que los años/palabras aparecen arbitrariamente en posiciones y estilos repetidos. No asumir que el MP4 es bueno porque pasan tests.
- Narrador Loose Thread: Fish reference `e686ae649ee44f219a108aacba206c1a`; narración y vídeo de UltimateBet ya producidos: **reutilizar**, no repetir Fish ni borrar cachés, estado o outputs. Aún puede haber cinco regresiones de tests del cambio MPT→Native pendientes.
- Los formatos futuros incluyen documentales de estafas/empresas, personajes del terror, biografías históricas, lore de videojuegos y fragmentos verticales. Diseño **multicanal** mediante profiles y recursos por episodio; no hardcodear estética universal ni lógica de una serie.
- `No tokens` tiene dos interpretaciones: *render con código* = sin tokens de modelos externos; *Codex decide creatividad nueva y revisa* = sí consume **cuota/tokens de Codex**. No prometer dirección inteligente gratis por vídeo si requiere modelos. Alternativa: plan editorial generado una vez, validado/caché, reutilización de presets y solo llamadas de IA cuando aporten valor.
- Los enlaces siguientes son un **catálogo de candidatos**, no 42 dependencias obligatorias ni una declaración de haberlos instalado/probado. La evaluación técnica, licencias y benchmarks es obligatoria antes de integración.

## 1. Arquitectura objetivo (diseñar antes de instalar)

```text
GUIÓN + FUENTES + AUDIO FISH YA SINTETIZADO + PERFIL DE CANAL
                   │
                   ├── Segmentación por frase / claim / acto / escena
                   ├── Alineación palabra↔audio (Fish timestamps o modelo local)
                   ├── Índice de assets y evidencia + licencias
                   └── Director automático: EditPlan por escenas (JSON validado)
                                  │
      ┌───────────────────────────┼───────────────────────────────┐
      │                           │                               │
  Stock factual              Motion graphics                 Clips específicos
  Pexels/archivo            FFmpeg/Motion Canvas            Imagen/escenas/local
  fotos y docs              retratos/máscaras               gameplay/capturas
      └───────────────────────────┼───────────────────────────────┘
                                  │
                 Render incremental por escena + cache
                                  │
            QA automático: imagen + audio + evidencias
                                  │
              CODEx DIRECTOR REVISA contacto + MP4
                 (si está disponible la sesión)
                                  │
                    Revisión de escenas malas
                                  │
                          MP4 final + manifiesto
```

**Separación crucial:** Kitok es **runtime de producción determinista** y debería poder ejecutarse sin Codex; Codex es **director/editor opcional** con un protocolo de entrada/salida y presupuestos de reintento, que puede lanzar herramientas, analizar storyboards y corregir el resultado. No meter llamadas Codex en el render de cada clip ni depender de que una conversación permanezca abierta. Para actuación verdaderamente desatendida, configurar un ejecutor/agente persistente autorizado y límites explícitos; no asumir que el CLI tiene una API de uso gratuito e ilimitado.

## 2. Tabla maestra — software a evaluar (40+ referencias)

Etiquetas: **P0** construir/probar ahora; **P1** candidato inmediato; **P2** más adelante/experimental; **E** referencia para estudiar, no integrar sin razón. **CPU** viable sin GPU en una escena individual; **GPU4** ensayo posible, sin garantía; **ALTO** no base viable en 4 GB de VRAM. Estado de licencia indicado solo cuando verificado en fuente original; para el resto se exige revisión por versión/pesos/uso.

### A. Composición, motion graphics y timeline

| Proyecto | Repositorio / web | Aporta a Kitok | Prioridad/hardware | Licencia / decisión |
|---|---|---|---|---|
| FFmpeg / ffprobe | https://github.com/FFmpeg/FFmpeg | xfade, zoompan, overlay, `drawtext`, `subtitles`, loudnorm, h264_nvenc, concatenación y render incremental | **P0 / CPU + NVENC opcional** | Ya está integrado; verificar build, filtros y licencias del binario |
| OpenCV | https://github.com/opencv/opencv | tracking ligero, composición, detección de blur, rostros, motion, análisis de fotogramas | **P0 / CPU** | Usar biblioteca existente si está, revisar build |
| Pillow | https://github.com/python-pillow/Pillow | textos legibles, máscaras, thumbnails de storyboard, capas y fondos | **P0 / CPU** | Más sencillo que montar framework nuevo |
| Motion Canvas | https://github.com/motion-canvas/motion-canvas | animaciones vectoriales en TS con sincronía de narración: líneas, flechas, cifras, timelines, documentación gráfica | **P1 / CPU** | **MIT**; piloto frente a FFmpeg puro |
| Remotion | https://github.com/remotion-dev/remotion | React → vídeo; composición declarativa, tipografía animada, plantillas, preview de alta calidad | **P1 / CPU + Chromium/RAM** | Licencia propia; gratuita para individuos/equipos pequeños elegibles; comprobar si Kitok será herramienta distribuida o servicio de automatización |
| Remotion captions | https://www.remotion.dev/docs/captions | ejemplos y utilidades de subtítulos cinéticos y timing | **P1 / CPU** | Misma licencia aplicable que Remotion |
| Remotion Audiogram template | https://github.com/remotion-dev/template-audiogram | referencia de captions/audio y cómo estructurar componentes | **E / CPU** | No hacer fork completo del producto |
| Manim Community | https://github.com/ManimCommunity/manim | diagramas matemáticos, probabilidad de póker, gráficos técnicos | **P2 / CPU** | MIT; usar solo cuando se necesiten matemáticas |
| SVG + CairoSVG | https://github.com/Kozea/CairoSVG | líneas, mapas, iconos y diagramas renderizados en capas vectoriales | **P1 / CPU** | Ver licencia/deps; SVG nativo también útil |
| Blender Python API | https://github.com/blender/blender | cámaras 3D, objetos, títulos volumétricos y escenas 3D programáticas | **P2 / CPU/GPU pesado** | GPL; excesivo para el núcleo de Kitok |
| OpenTimelineIO | https://github.com/AcademySoftwareFoundation/OpenTimelineIO | exportar/importar EDL/timeline a herramientas externas | **P2 / CPU** | Formato de intercambio; no renderiza vídeo; no confundir con EditPlan |
| Kdenlive/MLT | https://github.com/KDE/kdenlive | referencia de proyecto editable y pipeline timeline | **E / CPU** | No rehacer editor completo para MVP |

### B. Animar fotografías, personas y objetos (2D/2.5D)

| Proyecto | Repositorio / web | Uso propuesto | Prioridad/hardware | Nota importante |
|---|---|---|---|---|
| rembg | https://github.com/danielgatis/rembg | extraer sujeto/objeto en PNG, capas para parallax | **P0 / CPU ONNX** | MIT; probar calidad del recorte y casos difíciles |
| Depth Anything V2 **Small** | https://github.com/DepthAnything/Depth-Anything-V2 | mapa de profundidad para movimiento 2.5D | **P1 / CPU o GPU4** | **Small Apache-2.0; Base/Large/Giant CC BY-NC 4.0**; usar SOLO Small en producción comercial |
| Segment Anything 2 Tiny | https://github.com/facebookresearch/segment-anything-2 | máscara guiada de objetos y seguimiento de máscaras en vídeos | **P2 / GPU4 sin garantía** | PyTorch/CUDA y carga significativa; no prioridad ante rembg |
| MediaPipe | https://github.com/google-ai-edge/mediapipe | puntos de cara/manos/postura para seguir sujetos y anclar elementos | **P1 / CPU** | Ideal seguimiento ligero; revisar distribución/licencia versión |
| RIFE interpolation | https://github.com/hzwer/ECCV2022-RIFE | interpolar fotogramas para movimiento, cámara lenta | **P2 / GPU4 experimental** | La interpolación no añade semántica; consumo adicional |
| Real-ESRGAN | https://github.com/xinntao/Real-ESRGAN | mejorar assets pequeños / ilustraciones si el resultado lo requiere | **P2 / GPU4, CPU lento** | Revisar pesos y licencia; no dar falsa nitidez |
| OpenToonz | https://github.com/opentoonz/opentoonz | animación tradicional / sprites | **E / GUI** | Más útil como referencia de rigging que como motor de producción automática |

### C. Palabras, voz, alineación, subtítulos y sincronía

| Proyecto | Repositorio / web | Aporta | Prioridad/hardware | Nota |
|---|---|---|---|---|
| Timestamps Fish (existente) | https://docs.fish.audio/ | palabra ↔ tiempo junto a síntesis, cuando esté habilitado y sea fiable | **P0 / proveedor existente** | Usar audio/timestamps cacheados. Evitar otra llamada de pago solo para alinear si se puede forzar localmente |
| whisper.cpp | https://github.com/ggml-org/whisper.cpp | transcripción local y fallback por voz; tiny/base/small | **P1 / CPU** | README: model `small` ~852 MB memoria del modelo; buena opción 8GB RAM |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper | transcripción local cuantizada/int8, timestamps | **P1 / CPU o GPU4** | README reporta `small` int8 en CPU ~1,48 GB RAM en benchmark; sin batch grande |
| WhisperX | https://github.com/m-bain/whisperX | alineación por palabra y diarización | **P2 / CPU o GPU4 ajustando modelos** | Pesado: preferir solo alineación o uso selectivo y descargar modelos secuencialmente |
| pysubs2 | https://github.com/tkarabela/pysubs2 | estilos ASS, posiciones, fechas, textos, captions selectivos | **P0 / CPU** | MIT; evitar texto repetitivo basado en regex solamente |
| Rhubarb Lip Sync | https://github.com/DanielSWolf/rhubarb-lip-sync | mapa de fonemas a bocas para sprites 2D | **P1 / CPU** | MIT; ideal personaje dibujado recurrente, no rostro real |
| auto-editor | https://github.com/WyattBlue/auto-editor | detectar/cortar silencios y movimiento en clips | **P2 / CPU** | Base del repositorio Unlicense; no útil para narración documental limpia salvo casos específicos |
| pyannote.audio | https://github.com/pyannote/pyannote-audio | diarización si importamos entrevistas/podcasts | **P2 / CPU/GPU pesado** | Innecesario para narrador único |

### D. Recursos audiovisuales RELEVANTES al texto: fuentes e índices

| Proyecto/servicio | Repositorio / web | Aporta | Prioridad | Advertencia |
|---|---|---|---|---|
| Pexels API | https://www.pexels.com/api/ | stock genérico cuando es semánticamente correcto | **P0: YA ESTÁ** | No buscar «hacker», «casino» para absolutamente toda escena |
| Wikimedia Commons API | https://commons.wikimedia.org/wiki/Commons:API | fotos históricas, retratos, objetos, localizaciones | **P1** | licencia y atribución por asset; no todo es dominio público |
| Openverse API | https://api.openverse.org/v1/ | descubrimiento de fotos/audio CC | **P1** | licencia por archivo; verificar enlace fuente |
| Internet Archive | https://archive.org/developers/ | archivos, documentos y medios históricos | **P1** | disponibilidad/uso por asset no automático |
| NASA Image & Video Library | https://images.nasa.gov/ | misiones espaciales, satélites, archivo oficial | **P2** | revisar uso, insignias y restricciones particulares |
| yt-dlp | https://github.com/yt-dlp/yt-dlp | ingesta técnica de vídeos desde URLs admitidas | **P2** | disponibilidad técnica ≠ permiso de reutilización; identificar procedencia |
| PySceneDetect | https://github.com/Breakthrough/PySceneDetect | cortar películas/gameplay/videos fuente por planos, crear índice | **P1** | no extraer automáticamente un archivo ajeno como si fuera evidencia propia |
| OpenCLIP | https://github.com/mlfoundations/open_clip | ranking texto↔frames para buscar planos relevantes dentro de un catálogo | **P1 / CPU o GPU4** | elegir modelo pequeño y procesar en lotes. Coincidencia no es prueba factual |
| pypdfium2 | https://github.com/pypdfium2-team/pypdfium2 | render de páginas reales de informes, contratos y expedientes | **P1 / CPU** | licencia Apache/BSD del wrapper; revisar condiciones de dependencias |
| PyMuPDF | https://github.com/pymupdf/PyMuPDF | búsqueda de párrafos y coordenadas, realce documental | **P2 / CPU** | Revisar cuidadosamente AGPL/licencia comercial para la integración; opción alternativa: pypdfium2 + otras herramientas |
| Playwright | https://github.com/microsoft/playwright | capturas verificables de páginas oficiales o sitios archivados | **P1 / CPU/RAM** | ya usado en tests de Kitok; Chromium consume RAM; capturas cacheadas |

### E. Personajes que hablan e imagen→vídeo

| Proyecto | Repositorio / web | Qué hace | Prioridad/hardware | Realismo para TU equipo |
|---|---|---|---|---|
| MuseTalk 1.5 | https://github.com/TMElyralab/MuseTalk | lipsync facial sobre imagen/vídeo + audio | **P2 / GPU4** | **Referencia oficial:** RTX 3050 **Ti** Laptop de 4GB, fp16, unos **5 min para 8 s de vídeo**. Tu 3050 es distinta; probar 3–5 s sin integración global |
| SadTalker | https://github.com/OpenTalker/SadTalker | retrato+audio → cabeza que habla | **P2 / GPU4 o CPU lento** | calidad facial/compatibilidad y licencia de los checkpoints por validar; no montar avatares recurrentes antes de demo |
| LivePortrait | https://github.com/KlingAIResearch/LivePortrait | transferir movimiento de vídeo conductor a retrato | **P2 / GPU4 experimental** | NO es TTS→labios. Atención a pesos/uso comercial de InsightFace en pipeline base |
| ComfyUI | https://github.com/Comfy-Org/ComfyUI | flujo local/remote de imagen y vídeo generativos por API | **P2 / GPU4 modo lowvram en imagen pequeña** | GPL-3.0; no acoplar al runtime obligatorio. WSL/RAM limitan |
| Wan 2.2 | https://github.com/Wan-Video/Wan2.2 | text-to-video / image-to-video pesado | **P2 / ALTO** | No usar como ruta estándar con 4GB VRAM |
| LTX-2 | https://github.com/Lightricks/LTX-2 | text-to-video / audio-video y variantes | **P2 / ALTO** | el entrenamiento oficial requiere mínimo 32GB VRAM; eso no es cifra de inferencia, pero la GPU 4GB no es una opción sensata para motor diario |
| Blender Python | https://docs.blender.org/api/current/ | opcional objetos/cámaras/escenas 3D | **P2 / RAM/CPU** | para una animación específica, no un sustituto barato de IA de vídeo |

### F. Referencias para crear Shorts a partir de largos (NO prioridad hasta mejorar long form)

| Proyecto | Repositorio | Qué extraer |
|---|---|---|
| OpenShorts | https://github.com/mutonby/openshorts | ideas de transcripción, selección, auto-reframe y flujo UX; estudiar licencia por subdirectorios |
| Chopify | https://github.com/mehbul/chopify | lógica de scoring, subtitles, corte ligero |
| ClipsAI | https://github.com/ClipsAI/clipsai | análisis de transcripción y segmentación/reencuadre |
| ClipMint | https://github.com/kleZ799/clipmint | referencia alternativa de UI y flujo |

## 3. Qué SÍ es viable en tu GPU y RAM

**Sin nueva API, ejecución local recomendable:** cortes, parallax por capas, PNG transparentes con rembg en CPU, zoom/posición variable, chroma/matte, animación de documentos, cifras asociadas al guion, timelines, mapas 2D, máscaras SVG, captions ASS, composición en FFmpeg, gráficos ligeros, thumbnails/contact sheets, detección de escena, etiquetado/índice ligero con OpenCLIP o modelos pequeños en CPU y exportación 1080p (si el encoder instalado lo permite).

**Demostración GPU4 opcional:** Depth Anything Small en imágenes aisladas; MuseTalk 1.5 en una prueba de 3–5 segundos; Real-ESRGAN a una imagen pequeña. Ejecutar **uno cada vez**, monitorizar `nvidia-smi` y memoria, no mantener cargados simultáneamente con el render FFmpeg/Chromium.

**Mal encaje como rutina:** Wan/LTX generando cientos de planos, SAM2 video en 1080p continuo, 3D complejo, varios modelos PyTorch a la vez, lip-sync realista por minutos. Si se necesitan unas pocas secuencias premium: remoto bajo presupuesto explícito o assets prerenderizados. No equiparar vídeo IA generativo con motion graphics programados.

## 4. El fallo editorial del motor actual y cómo corregirlo

**Síntoma:** palabras, números y años saltan de forma aleatoria y siempre con el mismo efecto. Un detector de regex/tokens no entiende si el número es importante. El motor de efectos debe decidir **qué contar visualmente**, no qué palabras subrayar.

Contrato interno sugerido:

```json
{
  "schema_version": 1,
  "episode_id": "ultimatebet_superuser",
  "scene_id": "s_regulator",
  "start_sec": 83.2,
  "end_sec": 91.0,
  "spoken_claim": "The regulator identified accounts used in the cheating scheme.",
  "visual_purpose": "show_primary_evidence",
  "asset_refs": ["official-regulator-document-verified"],
  "visual_kind": "source_document_highlight",
  "animations": [
    {"kind": "camera_push", "intensity": 0.14},
    {"kind": "fact_label", "text": "23 accounts", "show_when": "phrase_alignment", "fact_id": "regulator_account_count"}
  ],
  "claim_provenance": "fact-map/regulator_report.md",
  "fallback": "no_text_editorial_still",
  "review_status": "pending"
}
```

**Todos los tiempos y nombres de assets arriba son ILUSTRATIVOS, no timestamps ni documentos que ya existan.** El planner debe resolver IDs reales antes del render y rechazar datos sin fuente.

Reglas del director:
- seleccionar entre **asset real/cita**, visual editorial simbólico, diagrama, personaje recortado, stock contextual o vacío intencional;
- tener **variedad funcional** de planos, sin cuota obligatoria de efectos;
- palabras/números/fechas se insertan solo cuando están alineados a narración y cumplen un propósito;
- no repetir ubicación, tipo de transición y asset de manera mecánica;
- texto de pantalla nunca tapa a personaje/objeto principal, se verifica en safe areas y tamaño reducido;
- animación de 2.5D solo si máscara limpia y espacio detrás del sujeto; si no, imagen con zoom ligero sin forzar;
- música y ambiente sostienen montaje, no silencios abruptos ni efectos demasiado fuertes;
- para vídeos sobre personajes, priorizar **assets exactos del personaje** de recursos provistos y capturas legítimas, en lugar de stock genérico «miedo».

## 5. QA autónomo que permite actuar a Codex

**No basta con que Codex imprima un log de FFmpeg**. Contrato para ver y corregir resultados:

1. Kitok renderiza MP4 preview de escena o episodio y exporta `edit_plan.json`, `shot_manifest.json`, `render_manifest.json`, `facts.json`, `source_manifest.json`.
2. Produce `contact_sheet.jpg` con 2–4 frames por plano, timestamps sobreimpresos, `cuts.csv`, `audio_quality.json`, `qa_flags.json`, versión vertical a móvil cuando proceda.
3. Heurísticas automáticas: duración, fps, negro/freeze, artefactos de texto en bordes, boxes/safe areas, duplicados/perceptual hash, transiciones repetidas, uniformidad de clips, legibilidad, discontinuidades de audio y balance LUFS/true peak, ocurrencia de número/fecha sin alineación/claim.
4. **Codex Work / Codex CLI con acceso local** abre MP4, frames y manifiestos; prioriza las peores escenas; describe acciones concretas; modifica `edit_plan` o recurso, regenera solo esas escenas y concatena reutilizando el audio original.
5. Bucle limitado (por ejemplo, máximo 2 iteraciones por escena o 3 rondas en una muestra), logs claros y límites de consumo de Codex; no bucle infinito ni asumir que un score es calidad humana.
6. Revisión manual al principio de las primeras entregas, y presets versionados por canal. No publicar ni gastar en proveedores caros automáticamente.

**Codex director como opción externa:** `kitok render --plan path; kitok qa --episode id; codex exec ...` puede orquestarse solo si el entorno y sus límites reales lo permiten; no asumir sintaxis/API del Codex instalada sin inspección previa. Kitok debe poder funcionar sin esa etapa.

## 6. Plan de implementación con entregables medibles

### P0: reparar lo que se ve mal, sin más dependencias (1 demo real)

- Inspeccionar código local modificado y MP4 UltimateBet producido. Conservar archivos y claves.
- Elegir **60–90 s exactos** del MP4, extraer audio original y crear referencia A.
- Rehacer B con 4–6 decisiones visuales intencionales: 1 recurso preciso, 1 gráfico útil, 1 imagen con capas (parallax), 1 dato verificado y un tramo en el que no aparezca texto. No introducir textos solo por palabras en script.
- Generar filmstrip A/B, inspeccionar frames 1-s, 5-s, último frame y toda transición. Mirar y escuchar versión renderizada real.
- Reparar tests heredados que fallan por nuevos defaults sin romper cobertura; no bloquear prototipo de long-form en infraestructura ajena.
- Si mejora, convertir escena en módulos de edición reutilizables con tests y presets.

### P1: catálogo mínimo que dé salto de calidad

- `asset_index`, `source_manifest`, ranking OpenCLIP ligero; Wikimedia Commons/Openverse; búsqueda exacta y por escena.
- Biblioteca 8–12 módulos: cut, slow camera, subject cutout/parallax, document highlight, timeline meaningful, contextual metric, quote card attributed, compare split screen, map, card/hand diagram, logo/product, understated chapter card.
- Probar Motion Canvas vs FFmpeg puro para dos módulos. Integrar el ganador; NO añadir tres motores de render equivalentes.
- API de QA/contact sheet y re-render de escena con caché. Estilo distinto por canal; nada «neon hacker» predeterminado.

### P2: nichos visualmente exigentes

- Estudio de personajes/lore con imágenes, sprites, capturas y tags temporales exactos.
- `video_asset_index` con PySceneDetect para ingesta de vídeo fuente; seleccionar escena por sentido narrativo, resolver coincidencias ambiguas sin inventar.
- Lip sync simple con Rhubarb (sprites), luego prueba MuseTalk 3–5 s `fp16` sobre material de demostración.
- Generación de video IA solamente por servicios aislados opcionales con presupuesto, no como motor básico.

## 7. Integración repositorios sin destruir Kitok

- **No** `git clone` 40 repos en la raíz de Kitok. Crear un catálogo de evaluación + prototipos aislados en directorio temporal no versionado o `local/vendor-eval/`. No copiar archivos fuente ni pesos de modelos al repositorio público sin revisar procedencia/licencia/atribución.
- No instalar globalmente paquetes PyTorch/CUDA ni sobrescribir `.venv` de Kitok por pruebas grandes; entornos aislados por motor (venv/uv/Docker cuando valga la pena) y un adaptador estable `run(scene_plan) -> clip_path`.
- Anotar por candidato: *valor añadido*, *prueba funcional*, *ram/vram pico*, *tiempo por 10 s*, *calidad en sample*, *licencia de código*, *licencia de pesos*, *dependencias transitivas*, *coste de mantenimiento*, *decisión ACEPTAR/DESCARTAR*.
- Descargas de modelos checkpoint solo después de estimar tamaño y necesidad; reutilización/caché de activos, checksum y ruta local. No acceder a internet para cada render.
- No tocar secretos, estados de MPT, cachés pagadas, vídeos anteriores o la rama main sin aprobación. Proveedores de pago y publicaciones requieren permiso explícito.
- Ser autónomo para INVESTIGAR y IMPLEMENTAR tras un smoke test: la autonomía no es instalar lo máximo; es identificar limitaciones, experimentar y escoger la mínima pila que produzca buena edición.

## 8. Criterios de aceptación del siguiente trabajo con Codex

**Entrega útil:** MP4 A/B real de 60–90 segundos, filmstrip, manifiesto, informe de QA, comandos reproducibles, scripts/tests, diferencias visuales justificadas, pruebas en el equipo del usuario y resultados de `make verify` tras corregir regresiones relevantes. Revisar cuando hay escenas incorrectas; no declarar éxito solo porque existe un MP4. Mantener los renders largos en 10–14 min cuando la historia lo amerite, sin padding.

**No hacer:** roadmap de 50 páginas sin demo; textos y fechas al azar; clonación masiva de repos; reusar stock genérico cuando hay un asset verdadero; gastar Fish otra vez; generar rostros/videos IA sistemáticamente en 4 GB; repetir el mismo zoom/transición; confundir efectos con comprensión narrativa.

## 9. Fuentes primarias para verificaciones técnicas y licencias

- Motion Canvas MIT y animación con voz: https://github.com/motion-canvas/motion-canvas y https://github.com/motion-canvas/motion-canvas/blob/main/LICENSE
- Remotion licencias: https://www.remotion.dev/docs/license/pricing y https://github.com/remotion-dev/remotion/blob/main/LICENSE.md
- Depth Anything V2 Small vs versiones NC: https://github.com/DepthAnything/Depth-Anything-V2#license
- Rhubarb MIT: https://github.com/DanielSWolf/rhubarb-lip-sync/blob/master/LICENSE.md
- MuseTalk 4GB benchmark: https://github.com/TMElyralab/MuseTalk#gradio-demo
- Whisper CPP uso RAM: https://github.com/ggml-org/whisper.cpp#memory-usage
- Faster Whisper benchmarks: https://github.com/SYSTRAN/faster-whisper#benchmark
- ComfyUI --lowvram y GPL: https://github.com/Comfy-Org/ComfyUI
- PySceneDetect: https://github.com/Breakthrough/PySceneDetect
- OpenTimelineIO: https://github.com/AcademySoftwareFoundation/OpenTimelineIO
- PDFium licencias: https://github.com/pypdfium2-team/pypdfium2#licensing
- Repositorios de referencia no equivalen a pruebas reales en Kitok; Codex debe verificar tags, licencias, versiones y hardware actual al ejecutar.
