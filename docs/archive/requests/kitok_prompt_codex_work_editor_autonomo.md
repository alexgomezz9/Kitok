> ARCHIVO HISTÓRICO — conservado el 19 de octubre de 2026.
> No es un manual vigente ni acredita capacidades actuales.
> Consulta el [índice de documentación actual](../../README.md).

> Referencia del encargo recibido el 2026-10-15. Las instrucciones vigentes son
> AGENTS.md y GUIA.md; el avance comprobado está en PROJECT_STATUS.md.
> Esta propuesta incluye capacidades que aún no están implementadas.

# Encargo para Codex Work — Kitok director audiovisual autónomo

Lee primero `docs/research/kitok_catalogo_herramientas_director_autonomo_2026-10-15.md` (catálogo de herramientas que acompaña este documento), `AGENTS.md`, `GUIA.md`, el motor Native local y los cambios no confirmados. Si hay discrepancias con GitHub, prevalece el checkout local y consulta al usuario antes de sobrescribir trabajo. No des por implementados módulos que solo estén documentados.

**Misión:** que Kitok produzca documentales largos con una edición realmente deliberada; Codex debe asumir el rol de editor creativo opcional, inspeccionar el vídeo final y corregir escenas. No quiero veinte efectos más que aparezcan al azar: quiero mejores decisiones de montaje. El sistema debe seguir funcionando sin Codex para trabajos rutinarios.

**Hardware exacto:** NVIDIA RTX 3050 Laptop **4GB VRAM**, **7,6GiB RAM**, 2GiB swap, WSL. Prioriza CPU/FFmpeg y modelos ligeros, procesos secuenciales y caché. No instales ni cargues Wan/LTX/ComfyUI como dependencias obligatorias. Si haces una prueba con MuseTalk, el repositorio oficial informa de un ensayo de 4GB con RTX 3050 Ti a unos cinco minutos por ocho segundos de vídeo; nuestra GPU no es exactamente esa. Test de 3–5 s y solo si aporta algo, con licencia compatible.

**Prioridad inmediata: UltimateBet ya generado.** Inspecciona el MP4 real de `outputs/longform/`, el guion `content/longform/3/ultimatebet_superuser.json`, los logs, audio, caches y código local (`src/kitok/editing`, `rendering/native`, FFmpeg y timeline). Ya se ha observado que aparecen palabras/fechas de modo repetitivo y descontextualizado. **No regeneres ni pagues otra vez Fish.** Corregir solamente montaje visual.

**Haz trabajo ejecutable, sin quedarte en investigación:**

1. Renderiza un **A/B de 60–90 segundos del mismo fragmento de UltimateBet**, conservando exactamente la voz existente. A = actual; B = nuevo montage. Introduce recursos específicos y precisos de esa parte del guion, animación ligera por capas 2.5D, un gráfico/documento/objeto explicativo, cortes dinámicos naturales, y datos/palabras solo donde tengan propósito semántico y sincronía. Evita stock irrelevante y falsas capturas de documentos/sistemas.
2. Crea un `EditPlan` por escena: intención, claim verificado, ID de fuente/recurso, inicio/fin, recurso visual, composición, animación, overlays alineados, fallback, provenance y canal. Asegura que el efecto se vincula a lo narrado, no a regex arbitraria o un patrón cada N segundos. Presets distintos por canal: Loose Thread ≠ terror/lore ≠ historia.
3. Evalúa **FFmpeg/Pillow/OpenCV** contra **Motion Canvas** y, solo si compensa, **Remotion**, con dos escenas de demostración y benchmark de tiempo/uso de RAM. Reutiliza el renderer Native; no metas tres frameworks paralelos. Revisa licencias antes de usar código y modelos.
4. Implementa mejoras reutilizables: imágenes y personajes recortados (`rembg`), parallax restringido por calidad, documentos y realces sobre PDFs reales (`pypdfium2`), títulos con jerarquía/posiciones variables y safe areas, comparaciones, mapas/diagramas y métricas animadas contextuales. Algunos de estos son opcionales si no sirven al episodio.
5. Mejora selección visual: consulta activos exactos del episodio, sus procedencias y al menos una alternativa de archivo/imágenes; puntúa visual↔frase con herramientas locales pequeñas si ayuda. Pexels es fallback, no la totalidad del vídeo. Mantén URLs, autoría/condiciones de activos. No metas material no verificado como prueba documental.
6. Añade QA obligatorio: contact sheets con timestamps, frames de cortes, verificación de safe areas, legibilidad, imágenes duplicadas, overlays en zonas incorrectas, texto sin sincronía, audio LUFS/true peak, cortes negros o planos inconsistentes. Si Codex dispone de capacidad de visualizar el MP4, que también lo vea. Señala límites del análisis automático; haz revisión manual donde corresponda. **Corregir y volver a renderizar solo escenas fallidas**, con caché.
7. Corrige cinco tests generales heredados del cambio MPT→Native sin degradar su cobertura, si siguen fallando. Ejecuta `make verify` y `make verify-browser` cuando sea viable. Usa Reviewer/Evaluator ya configurados y no dupliques herramientas por moda.
8. Entrega **vídeos MP4 A y B reproducibles**, comparación de frames/filmstrip, medidas del pipeline y una decisión editorial documentada; no basta con fotos o tests. Después, si la mejora es clara, prepara un episodio corto de prueba para el preset `Character Documentary` (sujeto icónico+documento+movimiento por capas), con recurso real aportado.

**Autonomía:** Puedes investigar, clonar repos de forma temporal y estudiar código, implementar integraciones y hacer iteraciones con modelos locales. No clones decenas de proyectos ni descargues muchos GB sin necesidad. Mantén entornos separados para experimentos CUDA y no alteres las dependencias Python del runtime a ciegas. Limita coste de agentes/modelos, informa si no puede continuar. No gastar proveedores de pago, publicar, borrar archivos de producción, sobrescribir trabajos locales o fusionar `main` sin aprobación. Trabaja en una rama segura y produce commits/PR cuando el código esté probado.

**Criterio de éxito:** a simple vista, B debe sentirse sustancialmente mejor editado que A; recursos correctos según historia, títulos no arbitrarios, transiciones y movimientos variados con moderación, sin penalizar la narración. Tiene que ser **usable en Kitok**, no una demo separada que haya que ejecutar a mano cada vez.
