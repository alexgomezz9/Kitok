# Galería histórica del 20/10/2026

Archivo histórico; no son instrucciones ni la selección vigente. Consulta docs/motion.md.

## Muestras revisadas tras el feedback visual

El operador rechazó la primera presentación por parecer tarjetas/subtítulos.
El mosaico enviado era `contact.jpg`, una imagen estática; no se utiliza ahora
como portada del vídeo. Ese hecho no convierte la calidad inicial en aceptada.
La revisión conserva los MP4 anteriores y los retira de la galería vigente.

Las candidatas actuales están bajo `outputs/motion-gallery/`:

- `effect_r2_*`: 19 demostraciones individuales de cuatro segundos.
- `ub_opening_v7`: 31 s; pregunta con titular editorial explícito y cifra grande.
- `ub_development_v7`: 31,5 s; flujo de información con objetos/conexiones animados.
- `ub_revelation_v7`: 29,5 s; dato de reembolso y contexto financiero.
- `generalization_mfa_v3`: 20 s; tipografía y diagrama llave/dispositivo/escudo,
  sin narración nueva.

Las tres UB conservan la mezcla de voz y música de las versiones anteriores, con referencia A/B de audio decodificado idéntico. Se retiraron los
planos de solitario, pantallas de compras y mesas de blackjack señalados en la
revisión; el stock sigue siendo ilustrativo, no imágenes históricas. Las preguntas
breves y etiquetas de estas pruebas fueron decisiones editoriales explícitas;
no se prometen esas mismas decisiones mediante recortes automáticos de frases.
El recorrido Native anterior se conserva como prueba técnica histórica, fuera
de esta selección visual; en esa fase no se renderizó un episodio completo.
La reparación técnica posterior de un intento completo del operador se registra
en [el estado vigente](../PROJECT_STATUS.md); no cambia la selección de muestras
ni acredita aceptación audiovisual del episodio.

Autores consultados mediante GET oficial de Pexels el 20/10 y guardados en
`cache/pexels-credits/`; los créditos de la revisión identifican las sustituciones.
Las búsquedas nuevas conservan autor/perfil; cachés antiguas pueden carecer de
ellos y se declaran desconocidos hasta verificarlos.

El operador confirmó después el error de decodificación tanto en Kitok como en
la descarga Windows. La auditoría completa encontró **seis MP4** que empezaban
como H.264 High/4:2:0 pero cambiaban a High 4:4:4 dentro del archivo al entrar en
una transición. La cabecera inicial y el decoder software de Linux toleraban ese
cambio; las comprobaciones previas no bastaban para validar una entrega portable.

En FFmpeg 6.1.1, `xfade` negocia formatos de trabajo 4:4:4. El renderer ahora
convierte a `yuv420p` después del filtro y fija ese formato al codificar; una versión
nueva de caché invalida las escenas afectadas. Regresión: disolución y barrido
reales, comprobando **todos** los fotogramas y la conservación del AAC.

La galería vigente usa los IDs de arriba con sufijo **`_compat1`**, incluidos los
19 `effect_r2_*_compat1`. Son copias nuevas con H.264 High/4:2:0 uniforme; 5.640
fotogramas de los 23 previews comprobados, decodificación completa y paquetes AAC
idénticos. Las referencias A/B compatibles se copian sin recodificación. Los
originales y metadatos anteriores se conservan con respaldo; cada carpeta nueva
tiene `repair.json` con hashes y procedimiento. No se sintetizó voz ni se renderizó
el episodio para esta reparación. El decoder Windows no está disponible aquí;
la comprobación en el equipo del operador sigue siendo necesaria.

Para reparar otra candidata corta activa, sin sobrescribirla ni usar proveedores:

```bash
.venv/bin/python scripts/repair_motion_delivery.py --item ID_ACTIVO --revision compat1
```

El comando rechaza medios de más de 60 segundos y salidas existentes. Publica la
nueva entrada sólo después de validar todos los fotogramas, duración y AAC;
archivar la entrada anterior es una operación separada con respaldo.
Para ver el movimiento abre el estudio y pulsa «Reproducir muestra»; el contacto
es una imagen de revisión, no una animación.

La música utiliza dos pistas para inicio/cierre, con una frontera de secciones
validada o cambio central estimado declarado. No compone una banda sonora para
cada escena. Las voces nuevas tienen previews del proveedor de textos distintos;
las históricas plain/tags sí comparten texto. No se sintetizó voz en esta fase.
La escucha subjetiva, sincronía audiovisual continua y aprobación editorial
siguen pendientes del operador, aunque se revisen frames y reproducción técnica.
