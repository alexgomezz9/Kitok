# Decisiones corregidas tras inspeccionar Kitok en WSL

22/10/2026. Plan pendiente de validación del usuario; no se implementa generación en esta revisión.
Este documento sustituye las recomendaciones anteriores de tema, acceso y orden de ejecución.

## Acceso y estado real

- Repositorio operativo: `/home/prueba/projects/Kitok`, Ubuntu/WSL, abierto en VS Code como `Kitok [WSL: Ubuntu]`.
- Rama observada: `feature/stickman-word-alignment`; HEAD `53c739edeaeab4be8ee5270100c01bdf7d6e225d`.
- Hay una reparación concurrente en audio, planificador y pruebas, registrada en `.codex-work/PLAN.md`. No se ha sobrescrito, certificado ni atribuido a esta revisión.
- Los documentos de la copia Windows anterior no estaban en WSL. Esta revisión guarda expresamente estas decisiones en el repositorio operativo, sin trasladar las recomendaciones retiradas.

## Comprobación sin proveedores

Episodio: `content/longform/stickman_video1`.
Hay 136 PNG con 136 hashes distintos y ninguna imagen editorial ausente: 86 de 1672×941, 48 de 1280×720 y 2 de 1920×1080.
El guion tiene 1.677 tokens y coincide con los 1.677 segmentos Fish; hay 25 segmentos válidos de duración cero. El recibo local informa 585,03825 segundos. El SRT existente tiene 122 bloques.
Las 136 escenas editoriales cubren consecutivamente las palabras del guion.

Se ejecutó exclusivamente el conversor del HEAD original contra los archivos reales, con conexiones de red deshabilitadas. Se reprodujo el rechazo; su excepción interna es `Malformed SRT: expected numbered cues and timestamps`. La serialización conserva saltos de párrafo que el parser interpreta como separadores de bloques. No se ha probado ni declarado terminada la reparación concurrente. No se modificaron audio, SRT, alineación ni imágenes; cero llamadas a Fish o ImageGen.

## Diseño acordado como requisito

Una escena editorial conserva un identificador estable, por ejemplo `escena_021`, una descripción específica, sus palabras y su propio PNG. Los tiempos de reproducción y movimientos de cámara son campos independientes. Modificar la duración no cambia su identidad ni obliga a regenerar su recurso.

Una lámina es sólo un intermedio: paneles distintos con composición 16:9 → recortes independientes → archivos por escena. No se monta la cuadrícula ni se sustituye el episodio por fondos genéricos repetidos. Si el motor divide una escena editorial en planos técnicos, conserva la asociación explícita con la escena original y no cuenta esos planos como nuevas ilustraciones.

El manifiesto de cada derivado conserva escena, solicitud, original, dimensiones nativas, coordenadas de recorte, escalado, hash, intento y estado de aceptación. El escalado no se presenta como detalle nativo. Se comprueban caras, objetos y contornos con los movimientos reales a 1080p.

## Capacidad confirmada y experimento pendiente

La herramienta integrada de esta sesión admite un prompt, referencias y transparencia; no expone `n`, lista de prompts, tamaño ni calidad. No hay una interfaz confirmada aquí para obtener varios archivos independientes en una única petición. Sí se puede solicitar una lámina y programar recorte, nombres, dimensiones, hashes, hoja de contacto e importación. Todavía no se ha generado ni medido una lámina en esta revisión.

La generación integrada se invoca desde el agente mediante su herramienta; no debe inventarse un endpoint de Kitok que la llame desde Python. El generador de lotes persistirá trabajos y recibirá resultados a través de un puente del agente. Reclamación de trabajo, recuperación y posprocesado serán automáticos; no se prometerá ejecución desatendida fuera de Codex sin un proveedor programático real.

Primera prueba propuesta, pendiente de autorización: dos solicitudes integradas, una lámina de dos escenas y otra de cuatro, con escenas del episodio y referencias existentes. Sirve para comprobar viabilidad y calidad, no para afirmar un ahorro estadístico. Conservar tiempos y resultados; contrastar con ilustraciones individuales existentes reconociendo que no tienen una medición comparable de generación. Si hace falta medir rendimiento individual, pedir un presupuesto adicional acotado antes de hacerlo. Sin API de pago ni nueva voz.

## Tres tareas técnicas, en orden

1. Revisar e integrar la reparación existente: conversión fiel de palabras Fish, cortes factibles sobre tiempos reales e identidad editorial estable; importar las 136 asociaciones sin renombrar originales. Verificar cobertura, duración máxima, hashes y reanudación. Producir una muestra técnica de 45–60 segundos con recursos existentes cuando el alcance quede validado; no dar por probado el episodio completo con esa muestra.
2. Automatizar pendientes e importación: manifiesto por escena, lotes de 1/2/4 según resultados medidos, puente de generación, recorte y validación, hojas de contacto, fallos parciales y reanudación. Un resultado remoto incierto exige reconciliación, nunca repetir automáticamente una solicitud potencialmente consumida.
3. Una entrada de producción reutilizable: perfil del canal y estado del episodio, investigación verificable, aprobación de enfoque/título/miniatura antes del guion final, producción, montaje con motor existente y QA. Una skill principal con guías por fase; aprendizaje editorial con análisis propios, enlaces y fechas. No crear una red de agentes ni reemplazar el motor.

## Dirección editorial y límites

Ondol queda descartado por instrucción directa. Se buscan historias narrativas ilustradas con stickman: protagonistas, objetivo, conflicto, giro y desenlace; hechos y contexto verificables. No se ha elegido un sustituto ni demostrado baja saturación española. Comparar resultados públicos de YouTube en español e inglés, fecha, formato, visitas relativas al canal, títulos y miniaturas; conservar incertidumbre cuando los datos no permitan afirmar una oportunidad. No usar vidIQ ni gastar créditos.

`ana` queda fuera del alcance. Fish se trata según lo indicado por el usuario como gratuito actualmente; no hace falta investigar precios ni generar voz para resolver este episodio. No se automatizará la interfaz de ChatGPT web ni se prometerá equivalencia de cuota o velocidad entre superficies.

No faltan archivos del usuario para iniciar la reparación. El usuario pidió validar el plan antes de implementar; falta esa validación para ampliar la implementación y permiso separado para las dos generaciones experimentales. La inspección y este registro sí están autorizados.
