# Modelos del proyecto

El primer motor es YOLOX-Nano **ya entrenado para sellos Naruto**, revisión fijada de Kazuhito00. Se descargaron el ONNX de 3.610.160 bytes, `labels.csv` y su licencia MIT en `pesos/naruto-yolox/`. [Manifiesto](manifiesto-naruto.json): Git blobs, SHA256, entradas, salidas, etiquetas y preprocesamiento.

Ejecutar `scripts/download_baseline.py` para repetir la descarga verificable. Un archivo existente que no coincida causa error. El modelo tiene salida `[1,3549,21]`; el CSV usa offset +1. El último canal sin etiqueta permanece desconocido. No normalizar su entrada BGR 0–255 como si fuera ImageNet.

Se ejecutó la referencia ONNX Runtime CUDA con perfil e I/O Binding; no se comprobó precisión con las manos del usuario. TensorRT 11.3 FP32 y NVDEC ya se ejecutaron con cámara real; paridad TensorRT/ORT registrada en `runtime/paridad-tensorrt.json`. Los engines van en `runtime/engines/` y conservarán hash del modelo, GPU, formas y versiones de runtime.

No hay todavía un modelo personalizado entrenado. RTMDet-nano, RTMPose Hand5 y los comparadores de geometría se incorporarán si el piloto con pesos existentes lo justifica; véase [investigación de modelos entrenados](../investigacion/REPOS-SELLOS-PREENTRENADOS.md) y [plan](../PLAN-DE-IMPLEMENTACION.md). Los enlaces oficiales de articulaciones siguen en [procedencia de visión](../investigacion/procedencia-vision.json).

## Articulaciones de diagnóstico activas

RTMDet-nano Hand y RTMPose-m Hand5 desde SDK oficial OpenMMLab. Descargar con `scripts/download_hand_models.py` y generar grafos CUDA con `scripts/prepare_hand_models.py`. Archivos, hashes, URLs y contrato en `manifiesto-articulaciones.json`. NMS de detección se reemplaza por CUDA y batch de pose se fija a uno, sin modificar pesos. Ambos perfiles verificados exclusivamente CUDA; los puntos no cambian el clasificador Naruto. Hasta dos manos; una mano tapada puede faltar o tener puntos imprecisos. Los scores de joints son respuestas SimCC, no probabilidades calibradas. MMPose: Apache-2.0, con procedencia de datasets/pesos separada.
