# Prompt para Codex

Tengo una primera versión funcional de un proyecto llamado Kitok.

NO lo reescribas desde cero.

Contexto:
- Kitok se ejecuta en WSL/Linux.
- MoneyPrinterTurbo Portable 1.3.7 se ejecuta en Windows.
- Se comunican exclusivamente por HTTP.
- MPT no debe ser modificado.
- v1 solo genera, valida y copia los vídeos a READY_DIR.
- NO quiero publicación social automática todavía.

Haz esto en orden:

1. Lee README.md y todo `src/kitok/`.
2. Ejecuta `pytest -q`.
3. Ejecuta `python main.py --dry-run`.
4. Inspecciona la API REAL de mi MoneyPrinterTurbo 1.3.7 usando su `/docs` u OpenAPI.
5. Confirma:
   - POST real de creación;
   - GET real de task;
   - TaskVideoRequest exacto;
   - valores exactos de los campos del preset;
   - estados reales;
   - formato real de `videos`;
   - cómo se descargan artefactos con/sin x-api-key.
6. Compara el OpenAPI real con `presets/mpt_default.json`.
7. Si algo no coincide, aplica cambios MÍNIMOS. No inventes campos.
8. Comprueba WSL -> Windows:
   - primero localhost:8080;
   - si falla, detecta host Windows;
   - no abras el puerto a Internet.
9. No lances la cola completa.
10. Haz SOLO un end-to-end con `voz_grabada_001`.
11. Verifica:
   - task_id guardado;
   - polling;
   - recuperación;
   - MP4 descargado;
   - ffprobe;
   - output en generated/ready;
   - sidecar;
   - publish_plan.
12. Revisa robustez:
   - no duplicar POST tras timeout;
   - state atómico;
   - paths WSL;
   - UTF-8;
   - 429/5xx;
   - MPT apagado;
   - timeout sin perder task_id.
13. No añadas Docker, Redis, DB, frontend ni async si no es necesario.
14. No añadas publicación TikTok/Instagram/YouTube aún.

ANTES de tocar archivos, dime:
- tests actuales;
- endpoints encontrados;
- incompatibilidades;
- archivos exactos que cambiarías.

Después implementa, corre tests/dry-run y, solo si la API está arriba, ejecuta el único test end-to-end.
