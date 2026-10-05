# Sellos ya entrenados: revisión de repositorios asiáticos y comparadores

Revisión del 4 de octubre de 2026. Se buscaron `ナルト 印 認識`, `火影忍者 手势 识别`, `나루토 수인 인식` y variantes en GitHub/Gitee. Se contrastaron README, árboles, licencias, etiquetas y código de inferencia mediante fuentes primarias. El idioma de un repositorio no demuestra la nacionalidad de sus autores; la búsqueda coreana y Gitee no aportaron un checkpoint adicional verificable para estos cuatro sellos. No constituye un censo de todos los proyectos existentes.

**Decisión: probar primero un detector RGB ya entrenado para los sellos.** La arquitectura RTMPose + red de apariencia + TCN es una ampliación condicionada a errores medidos. Estimar articulaciones por sí solo no proporciona etiquetas Naruto, y entrenar toda la fusión antes de comprobar un checkpoint pertinente añadiría trabajo evitable.

## Comparación verificada

| Proyecto / contexto | Artefacto comprobado | Qué aporta | Decisión |
|---|---|---|---|
| [Kazuhito00/NARUTO-HandSignDetection](https://github.com/Kazuhito00/NARUTO-HandSignDetection), documentación japonesa | YOLOX-Nano ONNX, **3.610.160 bytes**, MIT | Detecta sellos desde imagen conjunta, sin necesitar separar dos manos. Dataset privado; incluye ejemplos reales y anime | **Primer motor de referencia GPU** |
| [jeyaletheia/NARUTO-CODING](https://github.com/jeyaletheia/NARUTO-CODING), documentación china | ONNX con exactamente el mismo Git blob que Kazuhito; MIT | Añade GUI y simulación de teclado | Es una integración, no una segunda evidencia de entrenamiento o precisión |
| [PINTO0309/hand-gesture-recognition-using-onnx](https://github.com/PINTO0309/hand-gesture-recognition-using-onnx), documentación japonesa | Detector de palma + landmarks + clasificador ONNX; Apache-2.0 | Ruta ONNX alternativa a MediaPipe y herramientas de captura | El CSV clasifica `Open`, `Close`, `Pointer`; **no trae Naruto entrenado** |
| [yaxan/Naruto_Handsign_Classification](https://github.com/yaxan/Naruto_Handsign_Classification), proyecto con colaboradores de varios países | Código de clasificación y vídeo; no hay checkpoint en el árbol revisado ni licencia explícita | Comparación VGG16/MobileNetV2/ResNet/Inception; menciona dificultades con serpiente | No ofrece un peso inmediatamente reutilizable y no valida nuestra confirmación |
| [anhnguyen1204/Naruto_Jutsu_Detection](https://github.com/anhnguyen1204/Naruto_Jutsu_Detection), comparador | MobileNetV2 `.pt` 10.461.690 bytes; GNN `.pt` 691.479 bytes; mapas de 12 clases | RGB y grafo de 42 puntos para dos manos, con captura y entrenamiento | Pesos presentes; no se encontró licencia. No descargados ni ejecutados; estudiar si hace falta otra rama |
| [yogendrarau/sealwork](https://github.com/yogendrarau/sealwork), comparador | MLP ONNX **269.464 bytes**, 13 clases; MIT; prueba de paridad | 126 características, 12 sellos + `none` para transiciones; colección y estabilización | Segundo candidato de geometría, **entrenado con una persona**; no instalar su runtime CPU como ruta del proyecto |
| [bunkerapps/Jutsu-Hero](https://github.com/bunkerapps/Jutsu-Hero), comparador | Clasificador ONNX 258.502 bytes | Juego con MediaPipe y sello entrenado; pipeline de entrenamiento ausente | Licencia personalizada (`NOASSERTION` en API), requiere revisión antes de adoptar |
| [OpenMMLab RTMPose Hand5](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose), ecosistema chino | Pesos/exportaciones públicos de puntos de mano | Geometría reutilizable cuando las articulaciones son visibles | Continúa como ampliación. **Hand5 no es un modelo de sellos Naruto** |

Las revisiones, tamaños y Git blobs están en [repos-sellos-2026-10-04.json](repos-sellos-2026-10-04.json). La comparación no toma los FPS declarados por un README como rendimiento de este PC con Dota.

## Contrato real del modelo elegido

Revisión fijada: `07f4d3231f43f97cbd37653c793825f1dbc94d0e`.

- Entrada: `[1,3,416,416]`, FP32, **BGR 0–255**, sin dividir entre 255 ni normalizar con ImageNet. Redimensionado bilineal uint8; relleno 114 a la derecha/abajo, anclado arriba a la izquierda. [Preprocesamiento original](https://github.com/Kazuhito00/NARUTO-HandSignDetection/blob/07f4d3231f43f97cbd37653c793825f1dbc94d0e/model/yolox/yolox_onnx.py).
- Salida inspeccionada en el ONNX descargado: **`[1,3549,21]`**, es decir, 4 coordenadas, objectness y **16 canales de clase**. El CSV solo nombra 15 clases después de `None`; el canal 15 queda `unmapped_15` y se rechaza. No asumir que hay exactamente doce canales porque hay doce sellos zodiacales.
- La demo usa `labels[class_id + 1]`: el índice 0 del modelo es rata; `None` es una fila de presentación, no la clase cero. Índices verificados para el proyecto: **tigre 2; serpiente 5; caballo 6; mono 8**. [Demo](https://github.com/Kazuhito00/NARUTO-HandSignDetection/blob/07f4d3231f43f97cbd37653c793825f1dbc94d0e/simple_demo.py), [CSV](https://github.com/Kazuhito00/NARUTO-HandSignDetection/blob/07f4d3231f43f97cbd37653c793825f1dbc94d0e/setting/labels.csv).
- El score es `objectness × score_clase`; no una probabilidad calibrada de comando correcto. Mantener las demás clases al calcular competidores. No convertir el mejor de nuestros cuatro canales en un sello si el modelo prefirió otro.
- No hay una clase explícita de transición en este detector. Desconocido, rechazo por score/margen, estabilidad y negativos propios siguen siendo necesarios.

Los tres artefactos descargados —modelo, CSV y licencia— coinciden con sus Git blobs fijados y tienen SHA256 en [el manifiesto local](../modelos/manifiesto-naruto.json). Se conserva la licencia original junto a los pesos.

## Qué se puede reutilizar de los clasificadores de articulaciones

Sealwork separa mano izquierda/derecha por lateralidad, centra cada mano en la muñeca y divide por distancia a MCP9; rellena una mano ausente con ceros. Su vector de paridad contiene **una mano derecha de 63 valores**: el exportador antepone otros 63 ceros para formar la entrada real de 126. No es una inconsistencia de forma. [Exportador](https://github.com/yogendrarau/sealwork/blob/df7dbc96e6bc95a59afe2aa9ba84b6582e3a6745/web/export_onnx.py).

Su normalización borra la traslación relativa entre muñecas y sus pesos se entrenaron con MediaPipe. Alimentarlos directamente con RTMPose 2D, inventando `z=0`, **no es una transferencia validada**. Para compararlo, conservar extractor, lateralidad, espejo y normalización originales, o reentrenarlo con el nuevo extractor. La clase `none` es útil para estudiar transiciones; no garantiza cubrir todos los negativos de juego. La separación temporal publicada mejora frente a mezclar frames vecinos, pero no sustituye nuestras sesiones independientes. [Entrenamiento](https://github.com/yogendrarau/sealwork/blob/df7dbc96e6bc95a59afe2aa9ba84b6582e3a6745/train.py).

## Ruta afinada

1. Congelar y comprobar pesos, índices, forma y preprocesamiento. Ya implementado.
2. Ejecutar YOLOX completo con datos y salida en CUDA. Perfil comprobado; ONNX Runtime es la referencia de desarrollo permitida. TensorRT 11.3 FP32 y NVDEC ya están verificados; véase el plan vigente.
3. Conectar cámara USB, registrar sellos, transiciones y negativos. Probar RGB en sesiones independientes **antes de decidir entrenar**.
4. Si funciona, conservar un único detector de sellos y una máquina de estados temporal. Si falla por dominio visual, ajustar un modelo pequeño con imágenes propias. Si los errores persisten en contacto/oclusión, comparar geometría y fusión bajo el mismo presupuesto.
5. Mantener WiLoR/OmniHands como comparadores condicionados; no agregarlos a un pipeline que aún no necesita 3D.

## Evidencia de construcción y límites

Se creó un entorno Python 3.12.13 aislado; CUDA 12.9 de bibliotecas de usuario, ONNX Runtime GPU 1.26.0 y CuPy 14.2.0, fijados en `requirements-gpu.lock`. La [documentación CUDA de ORT](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html) respalda la combinación de runtime y la carga de bibliotecas; el éxito local se comprobó mediante ejecución y perfil.

La prueba inicial en RTX 4060 produjo **p50 5,08 ms / p95 11,11 ms** en treinta repeticiones de una imagen sintética 720p, después de calentamiento y con perfil activo. Incluye preprocesamiento, red, NMS y metadatos pequeños al host. El error máximo del resize frente a OpenCV fue **1 nivel de uint8**. Todos los eventos de nodos del perfil usan `CUDAExecutionProvider`; fallback CPU deshabilitado. Informe inicial (`runtime/smoke-naruto-cuda.json`, informe local no versionado).

También se comprobó paridad de salidas y NMS (`runtime/paridad-naruto.json`, informe local no versionado) con referencia CPU explícita sobre el mismo tensor preprocesado: error máximo de red 3,93×10⁻⁵ en la entrada sintética, y coincidencia de clases/cajas en cuatro detecciones de la lámina. Esa referencia CPU pertenece al diagnóstico offline y no constituye fallback de uso.

Esto comprueba infraestructura, no exactitud de sellos, latencia cámara→evento, presupuesto de VRAM/CPU, estabilidad USB ni rendimiento con Dota. La etapa de investigación no abrió la cámara. La construcción posterior sí verificó captura/NVDEC/TensorRT y vídeo en Chrome; véase el plan. Las pruebas de recetas usan observaciones simuladas; no entrenamos un modelo nuevo.
