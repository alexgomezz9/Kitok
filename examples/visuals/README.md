# Plan visual parcial

Copia [minimal.json](minimal.json) o [documentary.json](documentary.json) al episodio.
Son ejemplos con textos de demostración y nombres de archivo que debes sustituir;
no incluyen fotografías, narración ni documentos históricos. [script.txt](script.txt)
contiene sus anclas de ejemplo.

Desde el estudio importa sólo este JSON en «Fotografías y documentos del caso».
Elige la carpeta del episodio y aporta los archivos en images/ (también se admite
real_images/). Una imagen y una frase bastan; no hacen falta todos los campos del
segundo ejemplo. El formulario también crea este JSON al elegir imagen y frase.

En la configuración CLI existente incluye el contenido bajo visual_plan y
visual_root con la carpeta del episodio relativa al proyecto. Conserva script_file,
id, subject y keywords como en [el ejemplo largo](../longform/native_smoke.json).
Usa music_mode explícito off, auto o manual. Las keywords rellenan automáticamente
los intervalos sin cue. [Contrato y límites](../../docs/editing.md).
