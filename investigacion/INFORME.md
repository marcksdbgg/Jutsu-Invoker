# Jutsu Invoker

**Decisión vigente del 4 de octubre:** [plan completo](../PLAN-DE-IMPLEMENTACION.md), [checkpoints de sellos](REPOS-SELLOS-PREENTRENADOS.md) y entrenador USB/NVDEC/TensorRT con evaluación guiada. YOLOX preentrenado es el primer motor; fusión/entrenamiento se incorporan si las pruebas lo requieren. Las menciones de ausencia de implementación en este informe describen su revisión inicial.

Investigación y diseño de control por sellos de Naruto para Invoker. Fecha de consulta: 3 de octubre de 2026, hora de Lima.

Decisión de implementación del 4 de octubre de 2026: procesamiento visual en GPU, incluida decodificación NVDEC y ejecución TensorRT. El [plan práctico vigente](../PLAN-DE-IMPLEMENTACION.md) sustituye la comparación CPU como ruta de implementación. Ubicación principal: `~/Proyectos/Jutsu-Invoker`.

Revisión del mapa por petición del usuario: mono = Quas, tigre = Wex, caballo = Exort y serpiente = confirmar.

La propuesta es viable como prototipo local. Recomiendo empezar con el Android conectado por USB, un reconocedor híbrido de articulaciones, imagen conjunta de ambas manos y tiempo, y cuatro signos: mono, tigre, caballo y serpiente. Una gramática de predominio permite representar los diez hechizos con dos a cuatro sellos, incluida la confirmación. La prioridad es reconocer intenciones sin disparos accidentales mientras Dota comparte la GPU.

Para la rama visual de referencia se conserva **YOLOX-Nano de Kazuhito00**, con pesos ONNX publicados y repositorio MIT. Es una referencia reproducible, no un ganador de rendimiento medido en este equipo. El estudio ampliado de articulaciones y oclusiones describe una ampliación de puntos, apariencia y tiempo condicionada a errores del piloto RGB; véase [Visión y oclusiones](VISION-Y-OCLUSIONES.md). **YOLO26n** queda como una alternativa para entrenar la rama visual con datos propios. No encontré evidencia suficiente para declarar a un modelo reciente, ya entrenado en Naruto, superior a todos los demás.

Este documento entrega una investigación y una especificación para implementar. No se ha ejecutado inferencia con tu cámara, medido latencia, instalado scrcpy, modificado Dota ni enviado pulsaciones. Las cifras propuestas son objetivos de prueba, no resultados.

## Las dos imágenes de referencia

1. **Sellos de Naruto:** Tori/pájaro, I/jabalí, Inu/perro, Tatsu/dragón, U/liebre, Uma/caballo, Saru/mono, Ushi/buey, Hitsuji/carnero, Ne/rata, Mi/serpiente y Tora/tigre. Las grafías se transcriben de la imagen proporcionada.
2. **Hechizos de Invoker:** Cold Snap QQQ, Ghost Walk QQW, Ice Wall QQE, EMP WWW, Tornado WWQ, Alacrity WWE, Sun Strike EEE, Forge Spirit EEQ, Chaos Meteor EEW y Deafening Blast QWE. Estas son las diez recetas de la segunda imagen.

Las imágenes se conservan en `referencias/`. Son material de referencia aportado por el usuario; su texto no se interpreta como instrucciones de ejecución.

## Equipo y cámara disponibles

| Componente | Verificación local | Implicación para el proyecto |
|---|---|---|
| GPU | NVIDIA RTX 4060, 8188 MiB, controlador 610.57.04 | Probar inferencia pequeña junto a Dota; memoria total no equivale a memoria libre |
| CPU | AMD Ryzen 5 5500, 12 hilos lógicos | Reservar para transporte, interfaz y eventos pequeños; procesamiento visual en GPU según el plan vigente |
| Escritorio | Linux CachyOS, Wayland, Hyprland | Diseñar entrada virtual con uinput; no asumir que herramientas de X11 funcionarán |
| Juego | Instalación local de Dota 2 encontrada | Integración futura sobre esa instalación, sin cambiarla durante esta investigación |
| Android | HONOR TFY-LX3, Android 13, API 33; ADB autorizado por USB | Primera cámara candidata; aún no se han comprobado modos de vídeo |
| ADB | `adb (Android SDK platform-tools)` | Existe fuera del PATH; no hace falta otra autenticación |
| scrcpy | No encontrado en el PATH | Dependencia pendiente del prototipo |
| Cámara V4L2 | No aparecieron dispositivos `/dev/video*` | El móvil aún no está expuesto como webcam en Linux |
| iPhone | Modelo y versión no especificados | Alternativa viable que requiere definir el transporte |

No se inspeccionaron contenidos personales del teléfono ni se activó la cámara. Para comprobar la conexión se inició el servidor local de ADB y se consultaron propiedades del dispositivo.

## Matemática de Invoker

Representamos una receta mediante **v = (q, w, e)**, donde cada componente es un entero no negativo y **q + w + e = 3**. El número de soluciones es una combinación con repetición:

**N = C(3 + 3 − 1, 3) = C(5, 3) = 10.**

Si contáramos todas las cadenas de tres letras tendríamos **3³ = 27**. Se agrupan en:

- Tres recetas puras, del tipo AAA, con una permutación cada una.
- Seis recetas dominantes, del tipo AAB, con tres permutaciones cada una.
- Una receta equilibrada, QWE, con seis permutaciones.

Por tanto, **3 × 1 + 6 × 3 + 1 × 6 = 27**. QQW, QWQ y WQQ representan el mismo vector (2,1,0), es decir, Ghost Walk. WWQ representa (1,2,0), Tornado. La composición distingue los hechizos; el orden de esos tres orbes no distingue la receta. Esta derivación usa las recetas de tu imagen. Valve describe tres componentes y diez hechizos y relaciona Quas con hielo, Wex con tormenta y Exort con fuego. [Invoker, Valve](https://www.dota2.com/hero/invoker).

Geométricamente, las recetas son diez puntos de una malla triangular: tres vértices puros, seis puntos de borde y un centro equilibrado. Esto permite enseñar la lógica por familias en vez de memorizar diez claves arbitrarias.

La conmutatividad de la receta **no significa que el orden de ejecución de los hechizos, sus objetivos o el estado de las ranuras sea irrelevante**. Invocar prepara una habilidad; lanzarla es otra acción. Tampoco hay que confundir Invoke con una canalización obligatoria del personaje: nuestro sello final es una confirmación del controlador.

## Correspondencia elegida con los sellos

El usuario eligió este mapa por practicidad y velocidad de manos. Sustituye la propuesta inicial y es el mapa vigente del proyecto.

| Sello | Función | Criterio de diseño | Comprobación visual pendiente |
|---|---|---|---|
| Saru, mono | Quas, Q | Asignación elegida por el usuario | Relación horizontal y contacto de las manos |
| Tora, tigre | Wex, W | Asignación elegida por el usuario | Configuración de dedos extendidos y orientación de palmas |
| Uma, caballo | Exort, E | Asignación elegida por el usuario | Geometría que lo distingue de tigre |
| Mi, serpiente | Confirmar, Invoke | Cierre del gesto con las manos entrelazadas | Oclusión fuerte y rechazo de cierres transitorios |

Estas asignaciones son una convención de Jutsu Invoker, no equivalencias canónicas Naruto–Dota. Se mantienen fijas mientras calibramos la detección. La facilidad física se evaluará con tus transiciones y tiempos, sin sustituir tu preferencia por una asociación temática.

La inspección de articulaciones debe conservar la relación entre ambas manos. No basta reconocer cada mano de forma independiente: mono y serpiente pueden ocultar dedos, y distinguir caballo de tigre exige observar detalles que un modelo podría inferir mal. El estudio ampliado en `VISION-Y-OCLUSIONES.md` desarrolla la solución híbrida propuesta.

## Gramática recomendada

La propuesta principal es el **modo compacto por predominio**, con confirmación explícita:

- **A → serpiente:** tres orbes A; receta pura.
- **A → B → serpiente**, con A distinto de B: dos orbes A y uno B; el primero domina.
- **Q → W → E → serpiente:** uno de cada elemento; equilibrio. Se aceptan las seis permutaciones si los tres son distintos.

El orden sí tiene significado en la gramática compacta: Q→W significa QQW y W→Q significa WWQ. Es una abreviación que produce una receta, no un cambio de las reglas de Dota.

| Hechizo | Vector Q W E | Receta | Sellos compactos, terminando en serpiente | Asociación propuesta |
|---|---|---|---|---|
| Cold Snap | 3 0 0 | QQQ | Mono → serpiente | Frío puro |
| Ghost Walk | 2 1 0 | QQW | Mono → tigre → serpiente | Frío dominante vuelto aire |
| Ice Wall | 2 0 1 | QQE | Mono → caballo → serpiente | Frío al que se da fuerza o forma |
| EMP | 0 3 0 | WWW | Tigre → serpiente | Tormenta pura |
| Tornado | 1 2 0 | WWQ | Tigre → mono → serpiente | Aire dominante que atrapa |
| Alacrity | 0 2 1 | WWE | Tigre → caballo → serpiente | Velocidad con potencia |
| Sun Strike | 0 0 3 | EEE | Caballo → serpiente | Fuego puro |
| Forge Spirit | 1 0 2 | EEQ | Caballo → mono → serpiente | Fuego al que se da cuerpo |
| Chaos Meteor | 0 1 2 | EEW | Caballo → tigre → serpiente | Fuego puesto en movimiento |
| Deafening Blast | 1 1 1 | QWE | Mono → tigre → caballo → serpiente | Equilibrio de los tres |

La tabla conserva todas las recetas de la imagen. Las asociaciones de la última columna son recursos didácticos, no descripciones físicas literales de los poderes.

Hay **3 + 6 + 1 = 10** fórmulas semánticas. Contando serpiente, requieren **2, 3 o 4 sellos**, con media de **2,8** si los diez hechizos se usan por igual. La gramática literal usa cuatro eventos de sello, más las separaciones necesarias entre repeticiones. La reducción media del 30% se refiere a eventos, no promete 30% menos latencia total.

La serpiente funciona como delimitador: el prefijo Q→W no ejecuta Ghost Walk automáticamente, porque aún podría continuar con E para formar Deafening Blast. Esto evita añadir un tiempo de espera para adivinar si terminaste. Mantener mono quieto produce un único evento; no cuenta como QQQ por sí mismo en el modo literal.

No existe una codificación universal de diez hechizos en exactamente dos selecciones de un alfabeto de tres símbolos: **3² = 9**. Habría que añadir otro símbolo, duración u otro canal, o usar longitud variable como aquí. Tampoco afirmamos que esta gramática sea óptima para todos los usuarios: diez sellos directos más confirmación usan menos movimientos por hechizo, pero exigen memorizar y distinguir más clases.

**Modo literal opcional:** un evento de mono equivale a una Q, tigre a W, caballo a E y serpiente a Invoke. Permite aprender la receta real y mantiene una correspondencia gesto–pulsación. Para QQQ se hacen tres eventos separados por una salida clara del sello. Los modos deben seleccionarse explícitamente; nunca interpretar la misma secuencia con ambos a la vez.

## Modelos encontrados y comparación

La búsqueda incluyó GitHub, Hugging Face, Kaggle y referencias a Roboflow, con comprobación de árboles de archivos, metadatos y, en candidatos relevantes, historial del archivo de pesos. Una fecha de actualización del repositorio no es una fecha de entrenamiento. Los porcentajes publicados usan conjuntos de datos distintos y no son directamente comparables.

| Candidato | Evidencia y fecha comprobada | Ventajas | Limitaciones y decisión |
|---|---|---|---|
| [Kazuhito00, YOLOX-Nano](https://github.com/Kazuhito00/NARUTO-HandSignDetection/blob/main/README_EN.md) | ONNX de 3 610 160 bytes; archivo actualizado el 21-04-2022; repositorio con actividad hasta 10-07-2023 | Detector del conjunto de manos; 14 sellos descritos; entrada 416; código MIT | Datos completos privados; incluye imágenes de anime; sensibilidad a ropa y fondo reconocida por el autor. **Referencia RGB preentrenada** |
| [lucasfernandoprojects](https://github.com/lucasfernandoprojects/hand-sign-detection) | `models/best.pt`, 6,24 MB; repositorio 26-06-2024 | Doce sellos, pesos disponibles, modelo pequeño; repositorio GPL-3.0 | Datos iniciales de 1200 fotos capturadas por el autor; generalización a otra persona sin demostrar. Comparador útil |
| [hqrris0n](https://github.com/hqrris0n/gesture-detection) | `myModels/mainv1/best.pt`, 6,27 MB; pesos del 12-09-2024 aunque el repositorio llegó a agosto de 2026 | Doce signos y ejemplo de mapeo a teclado; MIT declarado | Flujo pensado para Windows; no benchmark conjunto con Dota. **No es un entrenamiento nuevo de agosto de 2026** |
| [eeshawn11, Hugging Face](https://huggingface.co/eeshawn11/naruto_hand_seal_detection) | YOLOv8, doce clases, `.pt` de 87,6 MB; última modificación 10-03-2023 | Checkpoint directamente localizable | Declara mAP@0.5 de 0,995, no verificado por la plataforma; dependencias antiguas y licencia no indicada en la ficha. No elegir por ese porcentaje |
| [Farrellhrs](https://github.com/Farrellhrs/naruto-jutsu-recognition) | Julio de 2026; modelos CoreML y ONNX presentes | Pipeline de landmarks y RandomForest; test declarado 97,47%, macro-F1 0,971; estudia separación de datos | Descarta imágenes sin manos detectables; sin licencia identificada. Buen referente para iPhone y validación, no ganador demostrado en oclusiones |
| [anhnguyen1204](https://github.com/anhnguyen1204/Naruto_Jutsu_Detection) | Mayo de 2026; MobileNetV2, GAT y SqueezeNet con pesos | CNN y grafo de 42 puntos para comparar | Validación declarada 98,4% y 97,9%; no licencia identificada ni prueba entre personas. Confirmación de 15 frames resulta lenta para nuestro objetivo |
| [NabilCollison-Cofie](https://github.com/NabilCollison-Cofie/Naruto-Hand-Sign-Recognition-Project) | `.h5` de 265 576 bytes; archivo modificado 08-09-2026 | Checkpoint reciente localizado | Documentación pública muy escasa y sin licencia identificada. Recencia insuficiente para recomendarlo |
| [GR4Yxx](https://github.com/GR4Yxx/NarutoHandSignDetection) | Marzo de 2026, MediaPipe y MLP para Jetson Nano | Arquitectura ligera y ejemplos de entrenamiento | No se encontraron los pesos `.pth` en el árbol consultado ni licencia. No es una solución preentrenada lista |
| [ParshvCrafts](https://github.com/ParshvCrafts/Naruto) | Agosto de 2026, MIT, entrenamiento en navegador | Recolección personalizada y clase neutral | El flujo pide entrenar; usa ventana de 45 frames y confirmación larga. Referencia de interfaz, no detector inmediato para Dota |
| [Jajamchlramoji](https://github.com/jajamchlramoji/NarutoHandSignJutsu) | Actualización 01-10-2026 | Proyecto reciente en la búsqueda | Sin checkpoint convencional identificado en el árbol consultado. No prueba de que sea el mejor modelo |

**Hallazgo de procedencia:** `jeyaletheia/NARUTO-CODING` (2025) y el archivo conservado en `huanglizhuo/Ketsuin` (2026) tienen el mismo blob Git del ONNX de Kazuhito00: `41ba540d4281d07182dc10dff264efc90a13266d`. Son reutilizaciones verificadas del archivo, no evidencia de dos modelos mejorados. [NARUTO-CODING](https://github.com/jeyaletheia/NARUTO-CODING), [Ketsuin](https://github.com/huanglizhuo/Ketsuin).

El dataset clásico de [Kaggle, Vikranth Kanumuru](https://www.kaggle.com/datasets/vikranthkanumuru/naruto-hand-sign-dataset) contiene doce sellos y una clase adicional “zero”; la ficha muestra licencia desconocida. Un dataset no equivale a un modelo ya entrenado. La licencia del notebook tampoco resuelve la de sus imágenes. Para entrenar y redistribuir un modelo nuevo conviene usar capturas propias y datasets con permisos documentados.

### La alternativa moderna

[YOLO26](https://docs.ultralytics.com/models/yolo26/) es una familia publicada en enero de 2026. Su variante nano tiene 2,4 millones de parámetros; el fabricante reporta 1,7 ms en T4 con TensorRT a 640 para su prueba COCO. **Ese número no mide Naruto, tu RTX 4060, el teléfono ni Dota simultáneo.** La familia ofrece inferencia sin NMS y licenciamiento AGPL-3.0/Enterprise. No se encontró en esta búsqueda un checkpoint Naruto YOLO26 con validación y permisos suficientes para recomendarlo directamente.

Decisión actualizada: usar el ONNX Naruto como primer motor RGB GPU y evaluar con capturas propias. RTMPose Hand5 y entrenamiento de fusión se incorporan solo si mejoran los errores medidos. MediaPipe queda como referencia del estudio previo; considerar YOLO26n solamente para la rama RGB si se justifica. El estudio [Visión y oclusiones](VISION-Y-OCLUSIONES.md) detalla la comparación con modelos 3D recientes.

### Por qué no depender solamente de MediaPipe

[MediaPipe Hand Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker/python) entrega puntos de manos y seguimiento; eso no implica conocer los doce sellos. [Gesture Recognizer](https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer) necesita un clasificador adecuado para categorías personalizadas. Los sellos juntan y ocultan dedos de ambas manos: el fallo del localizador puede impedir que el clasificador reciba una muestra útil.

El proyecto Farrellhrs declara 2177 imágenes descartadas por no detectar manos. Su precisión de clasificación no debe interpretarse como probabilidad de reconocer cualquier frame de entrada. Para Jutsu Invoker propongo usar un detector RGB de la figura conjunta como base; landmarks y un clasificador pequeño serían una comparación o comprobación auxiliar. No imponer “dos manos detectadas” como requisito universal, porque algunos sellos ocultan una de ellas.

## Uso del Android y del iPhone

### Android por USB como primera opción

[scrcpy admite captura de cámara desde Android 12](https://github.com/Genymobile/scrcpy/blob/master/doc/camera.md), selección frontal o trasera y solicitud de FPS. El teléfono con Android 13 cumple el requisito de versión; la compatibilidad concreta debe probarse. En Linux, [su salida V4L2](https://github.com/Genymobile/scrcpy/blob/master/doc/v4l2.md) permite abrir el vídeo como una webcam mediante `v4l2loopback`. Por defecto esa salida no añade buffering deliberado; siguen existiendo exposición, codificación, transporte y decodificación.

Propuesta para la siguiente etapa, todavía no ejecutada:

```bash
# Consultas después de instalar scrcpy y poner ADB en el PATH.
scrcpy --list-cameras
scrcpy --list-camera-sizes

# Ejemplo condicionado a que el teléfono admita este modo y video10 exista.
scrcpy --video-source=camera --camera-facing=back \
  --camera-size=1280x720 --camera-fps=60 \
  --video-codec=h264 --no-audio --no-control \
  --v4l2-sink=/dev/video10 --no-video-playback
```

No fijar `/dev/video10` sin comprobar que está libre y crear el dispositivo correspondiente. En CachyOS, el módulo de loopback debe corresponder al kernel instalado. Si 720p60 no funciona, medir 720p30 antes de cambiar de cámara. Lo que importa es la cadencia efectiva y la antigüedad del frame, no solo el FPS declarado por el teléfono.

AOSP ofrece [modo webcam USB desde Android 14 QPR1](https://source.android.com/docs/core/camera/webcam), sujeto a implementación del fabricante. No contar con él en este Android 13. La depuración USB no convierte automáticamente el teléfono en webcam.

Situar el móvil sobre o bajo el monitor, apuntando de frente al pecho y ambas manos, aproximadamente a 0,6–1,2 m como punto de partida. No hace falta que sea su cámara frontal: la trasera también puede apuntar hacia ti. Probar ambas, usar luz frontal y evitar exposiciones largas, enfoque que oscile y filtros de belleza. Normalizar orientación y espejo antes de inferir y mantener esa misma convención en entrenamiento.

### Integración propia para Android

Si el transporte resulta ser el cuello de botella, desarrollar una app con CameraX/Camera2 que recorte la región de manos, marque tiempos y entregue el último frame por USB con un túnel ADB. [CameraX permite descartar imágenes antiguas con KEEP_ONLY_LATEST](https://developer.android.com/media/camera/camerax/analyze). Un canal TCP por ADB exige controlar las colas a nivel de aplicación; por sí solo no garantiza baja latencia.

Evitar enviar vídeo RGB sin compresión a 720p60: **1280×720×3×60 = 165 888 000 bytes/s**, alrededor de 166 MB/s sin contar cabeceras. H.264 reduce tráfico pero añade codificación; un recorte pequeño o inferencia en el teléfono pueden ser mejores según las mediciones. En ese último caso se envían eventos de gesto y confianza, liberando la GPU del PC, aunque cambia el requisito inicial de inferencia en GPU del escritorio.

### iPhone

[Continuity Camera es una función para Mac](https://support.apple.com/en-lamr/102546); no asumir que ofrece una webcam nativa en este Linux. Para una integración propia hay dos rutas:

- App iOS con AVFoundation y vídeo comprimido hacia el PC. [AVCaptureVideoDataOutput permite descartar frames tardíos](https://developer.apple.com/documentation/avfoundation/avcapturevideodataoutput/alwaysdiscardslatevideoframes). Habría que preparar compilación, firma y despliegue con el entorno de desarrollo de Apple.
- App iOS que reconoce localmente y manda solo eventos. Reduce transporte de imágenes, pero exige evaluar la inferencia en ese iPhone y resolver la licencia del código/modelo que se reutilice.

Para cable, [libusbmuxd e iproxy](https://github.com/libimobiledevice/libusbmuxd) proporcionan transporte de puertos a un servicio del dispositivo. **No capturan la cámara por sí mismos:** necesitan una app que sirva el vídeo o los eventos y el emparejamiento correspondiente. WebRTC en una red local es otra posibilidad, pendiente de medir latencia y variabilidad. Por simplicidad, empezar con el Android ya conectado y mantener el iPhone como alternativa.

## Arquitectura y latencia

La propuesta actualizada combina dos ramas de evidencia:

**Móvil → último frame → articulaciones + recorte RGB de ambas manos → fusión temporal causal → gramática → adaptador de salida.**

Un receptor GSI independiente observa el estado disponible de Dota. No debe bloquear la captura ni inferir que una tecla se ejecutó simplemente porque fue enviada. La primera salida será un entrenador local que muestra la receta reconocida; luego se validará el adaptador de juego.

Procesar una región del torso donde estén ambas manos; un encuadre fijo basta para empezar. Si te mueves mucho, añadir detección de persona a menor frecuencia y seguimiento de su región. Un modelo grande de cuerpo, cara y manos en cada frame añade trabajo que no hace falta para cuatro comandos. Si aparece otra persona o se pierde la región elegida, suspender decisiones.

### Configuración inicial propuesta

- Captura 1280×720 a 60 FPS si el móvil lo sostiene; inferencia a 30–60 decisiones por segundo y batch 1.
- Cola de captura de tamaño 1: reemplazar el frame pendiente por el más reciente, no procesar una cola atrasada.
- Ruta GPU inicial: NVDEC → BGR/letterbox CUDA → YOLOX Naruto 416×416 → NMS CUDA → aceptación por timestamps. ONNX Runtime CUDA es la referencia construida; TensorRT final y captura quedan pendientes. RTMDet/RTMPose y fusión son ampliaciones condicionadas; MediaPipe conserva su papel de comparador.
- TensorRT como runtime final; ONNX Runtime CUDA como referencia de exportación con perfil comprobado. No activar redes en CPU automáticamente.
- Probar TensorRT FP16 solo después de medir la referencia; validar paridad de clases, umbrales y geometría. Construir y calentar el motor fuera de la partida.
- Dibujar una vista pequeña a 15–30 FPS; evitar vídeo de depuración o grabación continua durante la medición final.

[ONNX Runtime CUDA](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html) permite configurar el límite de su arena de memoria, pero ese límite **no representa toda la VRAM del proceso**. [El proveedor TensorRT](https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html) dispone de FP16 y caché de motores. Compatibilidad CUDA/cuDNN/TensorRT y particiones que caigan a CPU deben verificarse con las versiones elegidas.

**El archivo de pesos de 3,61 MB no implica un consumo de 3,61 MB en GPU.** Contextos, activaciones y espacios de trabajo pueden ser mucho mayores. El plan actualizado propone intentar menos de 1,5 GiB adicional y menos del 5% de pérdida de FPS mediano en Dota, revisando también los peores tiempos de frame. Son criterios de aceptación, no capacidad demostrada. Si la GPU está saturada, ajustar la cadencia y la visualización y evaluar dejar margen con los ajustes de Dota, conservando la ruta GPU.

### Medir la latencia completa

Definir **L = exposición y captura + transporte + decodificación + preprocesamiento + inferencia + estabilidad del gesto + salida + respuesta del juego**. Medir también el tiempo humano de formar y cambiar sellos: casi seguro será relevante, aunque una red tarde pocos milisegundos.

Objetivos iniciales propuestos:

| Medida | Objetivo para la primera evaluación | Qué incluye |
|---|---|---|
| Inferencia del detector, p95 | ≤10 ms con Dota | Solo red y sincronización correspondiente |
| Sello ya formado hasta evento aceptado, p95 | ≤150 ms | Cámara, transporte, inferencia y filtro |
| Final de serpiente hasta Invoke observado, p95 | ≤250 ms | Lo anterior, pulsaciones y confirmación disponible |
| Pérdida mediana de FPS de Dota | <5% | Misma escena y ajustes, varias ejecuciones |
| Falsas confirmaciones durante actividad normal | Cero en una sesión inicial de 30 min | No equivale a demostrar tasa cero a largo plazo |

Cuatro frames a 60 FPS abarcan 50 ms entre el primero y el cuarto; a 30 FPS, tres abarcan unos 66,7 ms. Exposición y llegada del primer frame añaden tiempo. Mantener un sello 15 frames, como algunos ejemplos, ya consume del orden de 250–500 ms según la cadencia antes de sumar otras etapas.

Registrar p50/p95/p99 y errores de secuencia. Para latencia GPU, sincronizar correctamente o usar eventos GPU; medir solo cuánto tarda una llamada asíncrona en retornar subestima el coste. Para teléfono y PC, sincronizar relojes o medir externamente con vídeo de alta velocidad: restar timestamps de relojes distintos sin calibración no es válido.

## Detección de intención y máquina de estados

Valores iniciales para calibración, no constantes probadas: confianza de entrada 0,80; de salida 0,55; margen entre clases 0,15; permanencia mínima 50 ms y al menos tres observaciones frescas para elementos; para serpiente, el plan GPU propone 66 ms y cuatro observaciones; timeout entre sellos de 1,2 s. Algunas salidas de detectores no son probabilidades calibradas: los umbrales y el margen solo se comparan dentro de un mismo modelo y deben ajustarse con validación.

1. **Desarmado:** no genera acciones. Un control manual arma el sistema y otro lo cancela; el entrenador puede comenzar armado porque no controla Dota.
2. **Listo:** espera un sello elemental válido dentro de la región elegida.
3. **Acumulando:** acepta una etiqueta estable una sola vez; mantenerla no añade tokens. Una segunda etiqueta distinta cambia de token. Una repetición solo se acepta después de una liberación clara en modo literal.
4. **Confirmando:** serpiente estable y fórmula válida producen una sola intención. Serpiente sin fórmula no hace nada. No completar silenciosamente una fórmula inválida.
5. **Esperando resultado:** un adaptador puede procesar esa intención una sola vez, con identificador y caducidad. No reintentar ciegamente si no se observa el resultado.
6. **Rearme:** exige liberar serpiente y una nueva secuencia. La pérdida de foco, cámara, persona o estado necesario cancela el trabajo pendiente y libera teclas.

Los frames inciertos de una transición no cuentan como comandos. Una ausencia breve puede tolerarse dentro del timeout sin concatenar etiquetas espurias; un intervalo largo o un fallo de cámara cancela. La estabilidad se mide en milisegundos y continuidad de muestras, no solamente en “N frames”. No añadir una espera global de medio segundo después de cada signo.

**Riesgo específico de la gramática compacta:** si se pierde W en Q→W→serpiente, podría reconocerse Cold Snap en vez de Ghost Walk. Las fórmulas son únicas, pero no corrigen borrados de tokens. Mostrar o anunciar discretamente la fórmula candidata, rechazar transiciones ambiguas y medir errores de hechizo completo. La confirmación disminuye activaciones accidentales; no vuelve infalible al clasificador.

## Cómo conectarlo con Dota 2

### Dos canales diferentes

**Entrada:** el adaptador transforma una intención humana en las teclas configuradas del juego. En este Linux, [uinput permite crear un dispositivo de entrada virtual](https://docs.kernel.org/input/uinput.html). Un helper pequeño con permisos limitados puede manejar pulsación y liberación; [ydotool](https://github.com/ReimuNotMoe/ydotool) es una referencia técnica. No ejecutar todo el sistema de visión como root ni asumir que PyAutoGUI/X11 controlará correctamente Wayland.

**Observación:** Game State Integration recibe estados que Dota envía mediante HTTP POST. No es una API para ordenar casts. La [implementación Dota2GSI](https://github.com/antonpup/Dota2GSI) documenta configuración en `game/dota/cfg/gamestate_integration/` y datos de héroe y habilidades. Valve indicó que requiere [`-gamestateintegration`](https://store.steampowered.com/news/posts/?appids=570&enddate=1656109094&feed=steam_community_announcements) y que puede tener impacto por frame.

El archivo de ejemplo de este proyecto escucha conceptualmente en `127.0.0.1:32147`, pide datos mínimos y no se ha instalado en Dota. Un intervalo de 0,1 s es un punto de partida, no garantía de actualizaciones a 100 ms. Mantener el receptor en localhost y no guardar identificadores de cuenta que no hagan falta.

### Flujo de una invocación

Ejemplo: **caballo → tigre → serpiente** significa Chaos Meteor.

1. El filtro confirma E→W→R y la gramática produce (0,1,2).
2. En modo compacto, el adaptador prepara **E, E, W, Invoke**, usando las teclas reales configuradas, no letras asumidas. En modo literal se emite una pulsación por evento reconocido.
3. Pulsaciones repetidas necesitan eventos key-down y key-up separados. Probar intervalos de 15–30 ms como punto de partida; no enviar un bloque instantáneo que el juego pueda perder.
4. Respetar enfriamiento, estado del héroe, pausa, foco, selección del héroe y caducidad de la intención. Si el resultado es incierto, cancelar y mostrar el fallo; no dejar un cast pendiente para después.
5. Consultar qué habilidad quedó disponible en las ranuras invocadas, cuando el payload GSI realmente lo permita. No asumir que el hechizo nuevo siempre estará en D ni que siempre cambia de ranura igual; depende de lo que ya estaba invocado.
6. **Lanzar es una decisión adicional.** Al inicio, dejar que tú apuntes y uses la tecla de lanzamiento. Después puede evaluarse un gesto dedicado o pedal que active la ranura confirmada, con quickcast configurado expresamente.

La disponibilidad de nombres de habilidades, su posición y su correspondencia con teclas debe comprobarse en un payload real de tu versión. Ausencia de un dato no significa cooldown cero. GSI puede llegar tarde y no necesariamente expone chat abierto, ventana enfocada, selección o cursor: no sustituir esas comprobaciones por supuestos. Para prototipo, un control físico mantenido de armado y desactivación manual al abrir chat reduce errores.

### Puntería y ergonomía

Cold Snap necesita objetivo; Tornado, EMP, Sun Strike, Meteor y Blast requieren ubicación o dirección según el comportamiento del hechizo; Alacrity requiere resolver objetivo/autolanzamiento; Ice Wall depende de la orientación; Ghost Walk y Forge Spirit no se apuntan igual. El adaptador necesita una política por habilidad y verificarla en el cliente, especialmente con mejoras de objetos. No basta reconocer una receta.

Con ambos brazos haciendo sellos no puedes mantener simultáneamente el ratón y el teclado como siempre. La primera experiencia razonable es **invocar con sellos y recuperar el ratón para apuntar y lanzar**, o usar el sistema como entrenador/espectáculo. Mantener un cursor previo o apuntar con la cabeza son extensiones que requieren otra evaluación de usabilidad. No hay evidencia para prometer que este control supere la velocidad de un jugador entrenado con teclado.

### Restricción de uso real

El [Steam Subscriber Agreement, sección 4](https://store.steampowered.com/subscriber_agreement/) restringe scripts, macros y otras automatizaciones. La expansión de un gesto a E,E,W,Invoke es precisamente el tipo de diseño que requiere aclaración de Valve antes de darlo por admitido en partidas. Una equivalencia 1:1 tiene menos automatización, pero tampoco encontré una aprobación explícita para este controlador. La existencia de GSI o uinput no constituye permiso. El entrenador externo puede desarrollarse primero; una prueba en Demo o lobby privado comprueba funcionamiento, **no demuestra una excepción contractual ni inmunidad frente a sanciones**.

## Plan de implementación y decisión experimental

| Etapa | Trabajo | Evidencia para avanzar |
|---|---|---|
| 1. Cámara | Instalar scrcpy y loopback, consultar modos, probar 720p30/60 | Cadencia real, frames recientes, temperatura y reconexión fiables |
| 2. Visión aislada | YOLOX Naruto en GPU y aceptación temporal; personalización/fusión si hace falta | Calidad bajo oclusión, matriz de confusión y latencia |
| 3. Gramática | Entrenador local, modo compacto y literal, audio/indicador de fórmula | Las diez recetas correctas y sin repeticiones por sostener el sello |
| 4. Evaluación conjunta | Dota en una escena reproducible y detector sin enviar teclas | p95/p99, VRAM y tiempos de frame dentro del presupuesto |
| 5. Personalización | Capturas tuyas, fusión de articulaciones y RGB, clasificador temporal causal | Menos errores en sesiones nuevas, cobertura y coste compartido medidos |
| 6. Integración | Receptor GSI mínimo, adaptador de entrada y lanzamiento separado | Confirmación de estado, fallo controlado y revisión de condiciones de uso |

Para entrenar, propongo **tres sesiones separadas**, dos condiciones de luz, varias distancias y ropa distinta. Recoger 10–20 ejecuciones por signo y sesión, transiciones y varios minutos de negativos: escribir, usar ratón, rascarse, manos cruzadas y salir de cámara. Capturar clips y dividir por sesión antes de extraer frames; mezclar frames vecinos entre entrenamiento y test inflaría el resultado.

Etiquetar una caja alrededor de ambas manos cuando formen un sello. Incluir otros signos de Naruto como negativos para los cuatro comandos, en lugar de forzar cualquier mano a una clase válida. Conservar una convención de lateralidad y comprobar cada aumento por espejo: algunos sellos cambian o pierden sentido. Probar un recorte de contexto suficiente para distinguir posición relativa de ambas manos.

Comparar sobre **los mismos clips**: RGB solamente, articulaciones solamente, fusión y fusión temporal. Medir la ruta GPU completa con Dota; mantener YOLOX y MediaPipe como referencias del estudio previo. El estudio ampliado define cuándo evaluar WiLoR u OmniHands. Medir 20 repeticiones de cada receta y una sesión de actividad normal sin sellos. Una meta inicial de ≥95% de recetas completas correctas es un umbral de ingeniería, no un resultado publicado.

Para errores raros, observar cero disparos en 30 minutos no prueba seguridad prolongada: con un modelo de Poisson, la cota superior aproximada al 95% sería todavía 3/0,5 ≈ 6 por hora. Ampliar horas de prueba antes de usarlo sin supervisión. El tiempo ahorrado por bajar 20 ms de confirmación no compensa confundir Meteor con Sun Strike.

## Entregables y estado de la investigación

La carpeta `~/Proyectos/Jutsu-Invoker` contiene este informe, las dos referencias, un mapa de recetas JSON, una configuración GSI de ejemplo inactiva, evidencia de procedencia de modelos y una verificación matemática reproducible.

Se comprobó la correspondencia de las 27 cadenas literales con las diez recetas y la cobertura de las diez recetas por la gramática compacta. Esto valida la lógica combinatoria, no la precisión de visión ni la integración con Dota.

Pendientes experimentales: FPS y transporte del HONOR, facilidad real de los cuatro sellos, rendimiento compartido con Dota, payload GSI de esta instalación, teclas efectivas, puntería y aceptación del controlador por Valve. Ningún repositorio consultado resuelve por sí solo esos puntos.

**Siguiente paso concreto:** seguir las fases 0–2 del [plan práctico](../PLAN-DE-IMPLEMENTACION.md): entorno fijado, cámara USB, NVDEC y modelos GPU. La especificación está en `diseno/pipeline-vision.json` y la investigación ampliada en [Visión y oclusiones](VISION-Y-OCLUSIONES.md). El gráfico interactivo actualizado se encuentra en `grafico/Jutsu-Invoker.html`.
