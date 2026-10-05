# Datos para reconocer los sellos

Hay capturas de diagnóstico de cámara; todavía no forman un conjunto validado de entrenamiento. La fase de datos debe seguir [el plan de implementación](../PLAN-DE-IMPLEMENTACION.md).

Crear `clips/`, `etiquetas/`, `splits/` y `caracteristicas/` cuando se capture el primer conjunto. Las etiquetas deben incluir mono, tigre, caballo, serpiente, transición y desconocido, junto con intervalos y grado visible de oclusión.

Dividir por sesión o toma completa. Las cachés de características GPU conservarán identificador de clip, timestamps, hash del extractor y versión de las etiquetas. Mantener los datos locales dentro del proyecto; los modelos preentrenados no contienen ejemplos de tus manos.

## Replay del núcleo implementado

`ejemplos/chaos-meteor.jsonl` contiene observaciones sintéticas de caballo → tigre → serpiente. La CLI `replay` debe producir Chaos Meteor. Este archivo no es una captura, ni un dato de entrenamiento, ni prueba de precisión visual. Los datos propios se recogerán primero para evaluar el checkpoint preentrenado y decidir si hace falta ajustar pesos.

## Evaluación guiada

El panel guarda pruebas de sellos/reposo y recetas en `evaluaciones/<sesión>/`. `observations.jsonl` registra los objetivos pedidos independientemente del detector; `report.json` resume confusión, intentos incluidos/excluidos y umbrales, y enlaza el H264 de `clips/`. Etiquetas provisionales hasta confirmar ejecución; el vídeo todavía necesita revisión para verdad independiente. Las pruebas abortadas conservan datos parciales y motivos. No mezclar frames vecinos entre calibración y evaluación final.
