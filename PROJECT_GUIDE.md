# Mapa de Kitok

- Uso diario: [GUIA.md](GUIA.md).
- Auditoría y prioridades: [docs/audit/2026-10-15.md](docs/audit/2026-10-15.md).
- Desarrollo y revisión: [docs/development.md](docs/development.md).
- Arquitectura propuesta: [docs/design/multichannel-production.md](docs/design/multichannel-production.md).
- YouTube oficial: [docs/integrations/youtube-readonly.md](docs/integrations/youtube-readonly.md).
- Siguientes fases: [docs/roadmap.md](docs/roadmap.md).

El mapa anterior está preservado en
[docs/archive/project-guide-2026-09.md](docs/archive/project-guide-2026-09.md).

Entradas actuales: main.py (shorts), longform.py (largos), python -m kitok.api
(API/estudio), dashboard.py (Streamlit legado). El motor nativo largo sigue siendo
experimental; shorts Pexels/locales y nuevos largos no necesitan MPT. Su API sólo
se usa al pedir diagnóstico o recuperación histórica explícita.
Montaje por escenas: [docs/editing.md](docs/editing.md). Estado breve:
[PROJECT_STATUS.md](PROJECT_STATUS.md).

Herramientas locales: scripts/direct_edit.py compila briefs sin proveedores;
scripts/media_library.py consulta/importa recursos con procedencia;
scripts/audio_library.py selecciona y mezcla música licenciada. La interfaz
diaria mantiene los recorridos sencillos de GUIA.md.
