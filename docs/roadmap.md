# Pendientes reales de Kitok

El estado implementado está en [capacidades](capabilities.md) y la evidencia en
[PROJECT_STATUS.md](../PROJECT_STATUS.md). Esta lista contiene trabajo pendiente.
No se activa instalando otra skill y no es un contrato aceptado por las APIs actuales.

## 1. Mejorar calidad antes de aumentar volumen

- Más archivos/fotografías específicos por episodio, con identidad y derechos.
- Tratamiento coherente de color entre stock luminoso y reconstrucciones oscuras.
- Escuchar y revisar de forma continua; los contactos sólo muestrean imágenes.
- Revisar con audición humana la galería y las tres muestras enriquecidas; recursos más específicos para sustituir stock genérico. No extender UltimateBet completo desde un agente durante esta fase.

Aceptación: muestra corregida y revisión audiovisual con problemas concretos
cerrados; el operador podrá lanzar después el episodio completo desde el frontend con montaje documental, reutilizando cachés; esta fase no lo renderiza.

## 2. Director editorial y perfiles reutilizables

- Investigación y guion con fuentes, checkpoints de revisión y espera persistente.
- Perfil de canal versionado con voz, idioma, estilo y snapshot por trabajo.
- Parametrizar escenarios de póker; actualmente Paredes/NioNio están fijados.
- Extender adquisición de recursos específicos y gestionar faltantes en la interfaz.

Aceptación: dos temas/canales distintos producen configuraciones independientes;
un reinicio no duplica voz, recursos ni decisiones. El brief actual es explícito,
no un intérprete semántico de cualquier guion.

## 3. Paquete editorial

Miniaturas editoriales, variantes de título y portada, capítulos, adaptación a
shorts y evaluación de retención necesitan componentes y revisión propios.
Las miniaturas técnicas de previsualización ya existentes no cumplen esa función.
Doblar/traducir tampoco conserva automáticamente la sincronización.

## 4. Cuenta y métricas YouTube

El CLI de lectura ya está implementado. Falta autorización Google real del titular,
comprobar datos de su canal, importar CSV reach/CTR, dashboard y políticas de purga
antes de operar un histórico desatendido. Consultar [la integración actual](integrations/youtube-readonly.md).
Nunca inventar métricas ausentes ni pedir permisos de escritura para simplificar OAuth.

## 5. Entrega y operación ampliadas

Publicación YouTube sigue fuera de la implementación. Cualquier adaptador necesita
aprobación ligada al bundle, scopes mínimos, idempotencia y reconciliación tras
fallos ambiguos. Largos siguen fuera del publicador/calendario Buffer de shorts.
No habilitar paralelismo multicanal sin probar límites de memoria, locks y cachés.

La recuperación MPT se conserva para datos históricos; nuevos vídeos son nativos.
Los diseños anteriores están aislados en el [archivo](archive/README.md), sin
instrucciones de operación vigentes duplicadas.
