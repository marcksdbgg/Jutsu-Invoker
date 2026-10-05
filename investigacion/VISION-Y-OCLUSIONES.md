# Jutsu Invoker: articulaciones, oclusiones y modelos actuales

**Revisión vigente del 4 de octubre:** el [plan completo](../PLAN-DE-IMPLEMENTACION.md) y la [investigación de checkpoints de sellos](REPOS-SELLOS-PREENTRENADOS.md) priorizan YOLOX Naruto preentrenado. La fusión de este estudio queda como ampliación si el piloto RGB falla. El entrenador ya ejecuta cámara USB/NVDEC/TensorRT y vídeo en Chrome. La evaluación personal y calibración siguen pendientes; las cifras de este estudio histórico no son resultados del piloto.

Actualización del 3 de octubre de 2026. Este documento amplía y actualiza la decisión de visión del informe inicial. Investigación de publicaciones, repositorios, código de inferencia y disponibilidad de pesos; todavía no es un benchmark de la cámara ni de la RTX 4060 del proyecto.

La [implementación vigente](../PLAN-DE-IMPLEMENTACION.md), definida el 4 de octubre de 2026, utiliza GPU para vídeo y visión. Las comparaciones CPU de este estudio se conservan como contexto técnico.

## Decisión propuesta

Conservar tu asignación: **mono = Quas, tigre = Wex, caballo = Exort y serpiente = confirmar**. La elección responde a tu criterio de practicidad. No hace falta forzar una asociación elemental del anime para justificarla.

La ampliación que propongo evaluar si falla el piloto RGB es un **reconocedor híbrido de cuatro sellos**: articulaciones para la geometría, un recorte RGB que contenga las dos manos para reconocer su contacto y superposición, y un clasificador temporal que utilice únicamente imágenes presentes y pasadas. La salida debe incluir «transición» y «desconocido». No exigiría reconstruir una malla 3D perfecta antes de reconocer un comando.

Para esa ampliación geométrica GPU, compararía **RTMDet-nano de manos + RTMPose-m Hand5**, con decodificación NVDEC y ejecución TensorRT. **MediaPipe en CPU** queda como referencia histórica de comparación; tu implementación usará GPU. Ambos necesitan un clasificador específico para nuestros cuatro sellos: sus pesos de articulaciones no vienen entrenados para convertirlos en comandos de Invoker. La rama RGB y la fusión temporal requieren entrenamiento o calibración con tus manos.

Como alternativa 3D avanzada evaluaría **WiLoR con su modo `--fast`**, sujeto a sus licencias y a una medición real con dos manos. Para estudiar interacción entre manos, **OmniHands** es más directamente pertinente. **StableHand** aporta investigación reciente sobre oclusión y calidad de las estimaciones, pero su distribución actual no es un sustituto inmediato de una webcam de baja latencia. No hay evidencia suficiente para prometer que un único modelo público sea el mejor en tus cuatro sellos frontales y mientras juega Dota.

## Lo que puede y no puede resolver el seguimiento de dedos

Un localizador estima normalmente 21 puntos por mano: muñeca y articulaciones hasta la punta de cada dedo. Podemos calcular flexión, separación, orientación y relaciones entre ambas manos. Es una representación más estructurada que clasificar solamente píxeles, pero también pierde información: dos esqueletos estimados pueden parecer similares aunque el patrón visible de contacto sea diferente.

En tus sellos se combinan tres problemas:

| Problema | Consecuencia para el reconocedor | Respuesta de diseño |
|---|---|---|
| Una mano tapa los dedos de la otra | Un punto puede ser una predicción plausible sin observación directa | Reducir su peso; conservar evidencia RGB; permitir rechazo |
| Las dos manos se cruzan o se tocan | El detector puede unir cajas, perder una mano o intercambiar identidades | Seguir identidades en el tiempo y mantener un recorte conjunto |
| El movimiento entre sellos se parece brevemente a otro sello | Un clasificador por imagen puede añadir un token incorrecto o confirmar | Entrenar transiciones y exigir evidencia reciente y estable |
| Desenfoque o dedos pequeños en la imagen | La forma fina deja de ser observable | Mejorar encuadre e iluminación antes de aumentar el modelo |

Si desde una única cámara dos configuraciones producen prácticamente la misma imagen porque los dedos distintivos están completamente tapados, el problema es ambiguo. Un modelo 3D puede escoger una explicación probable, pero no recuperar certeza que la imagen no contiene. Por eso una mano reconstruida de aspecto convincente no basta para ejecutar Invoke.

Aplicación a los cuatro sellos: comprobar especialmente **caballo frente a tigre**, donde la configuración de dedos puede quedar oculta; **mono**, donde importa la disposición relativa de ambas manos; y **serpiente**, cuyo entrelazado produce mucha oclusión y además tiene la responsabilidad de confirmar. Son hipótesis de confusión para probar con vídeo propio, no resultados medidos.

## Comparación de candidatos y alcance real de sus resultados

### MediaPipe Hand Landmarker: referencia ligera

Ofrece 21 puntos por mano, coordenadas de imagen y coordenadas 3D locales, lateralidad y seguimiento. Configurar dos manos explícitamente; el valor inicial habitual es una. Su modo asíncrono puede descartar entradas si sigue ocupado, lo que favorece trabajar con muestras frescas. La documentación publica 17,12 ms en CPU y 12,27 ms en GPU para Pixel 6: esas cifras no describen este HONOR ni la RTX 4060. [Documentación oficial](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker), [guía Python](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python).

Dos detalles de implementación son decisivos: las coordenadas «world» tienen un origen local por mano; restar las dos muñecas de esos sistemas no da la separación física entre manos. Además, no debemos interpretar la confianza de presencia o lateralidad como certeza de cada dedo oculto. El grafo oficial separa presencia y landmarks; no entrega una medición fiable de visibilidad individual por articulación. [Grafo oficial de landmarks](https://github.com/google-ai-edge/mediapipe/blob/master/mediapipe/modules/hand_landmark/hand_landmark_cpu.pbtxt).

Es una referencia práctica, no una afirmación de SOTA en oclusión bimanual. En Android existe una ruta GPU documentada, pero trasladar el cálculo al teléfono requiere probar latencia y temperatura. [Guía Android](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/android).

### RTMPose-m Hand5: candidato GPU reproducible

El proyecto oficial publica un detector RTMDet-nano para manos y RTMPose-m a 256×256 para 21 articulaciones 2D. Hay checkpoints y exportaciones ONNX. Hand5 mezcla cinco conjuntos de entrenamiento de manos. El repositorio tiene licencia Apache-2.0; las condiciones de los datasets son independientes. La tabla específica de manos deja vacíos los tiempos de ejecución: no sería correcto atribuirle las latencias de modelos corporales de la misma página. [Proyecto RTMPose](https://github.com/open-mmlab/mmpose/blob/main/projects/rtmpose/README.md), [configuración Hand5](https://github.com/open-mmlab/mmpose/blob/759b39c13fea6ba094afc1fa932f51dc1b11cbf9/configs/hand_2d_keypoint/rtmpose/hand5/rtmpose-m_8xb256-210e_hand5-256x256.py).

Es un estimador por mano, no un modelo que resuelva explícitamente el contacto entre dos manos. Lo selecciono por sus artefactos disponibles y facilidad de evaluación en GPU, no porque se haya demostrado superior a MediaPipe en Naruto. Verifiqué respuesta HTTP 200 de los dos paquetes ONNX: aproximadamente 3,84 MB para el detector y 51,27 MB para pose. El tamaño descargable no mide VRAM ni latencia.

### WiLoR: alternativa 3D avanzada con pesos públicos

WiLoR combina localización y reconstrucción 3D de manos; fue publicado en CVPR 2025. El repositorio añadió en marzo de 2026 un modo rápido con precisión reducida y poda de profundidad; el autor declara hasta 1,6× de aceleración. Tiene pesos públicos, pero requiere componentes MANO y publica condiciones CC-BY-NC-ND-4.0 para sus modelos. No debe presentarse como una solución íntegramente permisiva. [Repositorio y condiciones](https://github.com/rolpotamias/WiLoR), [artículo CVPR](https://openaccess.thecvf.com/content/CVPR2025/papers/Potamias_WiLoR_End-to-end_3D_Hand_Localization_and_Reconstruction_in-the-wild_CVPR_2025_paper.pdf).

La cifra de hasta 175 FPS del artículo corresponde al detector en su evaluación, no al sistema completo de dos manos, teléfono y Dota. **WiLoR-mini** simplifica la inferencia y distribución; su nombre no demuestra que sea una red pequeña o un modelo destilado diferente. [WiLoR-mini](https://github.com/warmshao/WiLoR-mini).

Lo probaría como comparador 3D, inicialmente sobre clips. Si supera la calidad del sistema ligero y cabe en el presupuesto de tiempo y GPU, se puede estudiar su incorporación. No hace falta renderizar mallas en cada frame de juego.

### OmniHands: interacción entre manos como objetivo explícito

El proyecto se presenta como TOG 2026 y ofrece variantes para imagen, vídeo y múltiples vistas. Modela ambas manos y su relación, por lo que es pertinente para contacto y oclusión. Hay enlaces a checkpoints y requiere MANO. No encontré una licencia explícita en la revisión consultada; disponibilidad de código no equivale a permiso de redistribución. [Página del proyecto](https://omnihand.github.io/), [repositorio](https://github.com/LinDixuan/OmniHands).

La demo de vídeo lee primero las imágenes, extrae tokens y luego procesa secuencias; su configuración utiliza nueve frames. No es evidencia de un flujo causal de webcam sin espera. La variante de imagen evita depender de un vídeo completo, pero sigue necesitando integración y benchmark. La última actividad del repositorio observada es de 2024: la etiqueta bibliográfica de 2026 no implica pesos nuevos de 2026. [Demo inspeccionada](https://github.com/LinDixuan/OmniHands/blob/935e1f580975263be799ebf56932e27ab18e1a01/run_demo.py).

### StableHand: investigación reciente que merece atención

StableHand presentó un preprint en mayo de 2026 y una versión ampliada en septiembre; el repositorio anuncia aceptación en NeurIPS 2026. Reconstruye movimiento bimanual 4D desde vídeo egocéntrico mediante estimación de calidad y un modelo generativo temporal. Publica pesos y ejemplos, con licencia MIT para su propio código. Sus mejoras reportadas en HOT3D y ARCTIC no son resultados sobre una cámara frontal realizando Naruto. [Proyecto](https://huajian-zeng.github.io/projects/stablehand/), [artículo](https://arxiv.org/abs/2605.18553), [repositorio](https://github.com/huajian-zeng/stablehand).

La distribución utiliza propuestas y cachés preprocesadas, señales adicionales y muestreo iterativo; el listado de pendientes incluye código de preprocesamiento y entrenamiento. La inferencia inspeccionada opera sobre clips completos. No hay una demo equivalente a «conectar webcam y reconocer cuatro sellos con Dota». Las restricciones de dependencias como WiLoR y MANO siguen siendo relevantes aunque el código propio sea MIT. [Inferencia inspeccionada](https://github.com/huajian-zeng/stablehand/blob/0471a45e325ffa167cc6a8484d712a21befd3e47/sample/infer_clips.py).

La idea que sí adoptaría es estimar la calidad por componentes: una muñeca bien localizada no demuestra que todos los dedos estén bien reconstruidos. Eso inspira el diseño; no significa que ya hayamos transferido o reproducido StableHand.

### Otros modelos que delimitan la decisión

| Modelo | Utilidad y limitación para este proyecto |
|---|---|
| [HaMeR, CVPR 2024](https://github.com/geopavlakos/hamer) | Referencia fuerte de malla 3D por mano; código MIT y requisitos MANO separados. No garantiza resolver contacto entre ambas manos ni baja latencia compartiendo GPU. |
| [InterWild, CVPR 2023](https://github.com/facebookresearch/InterWild) | Reconstrucción de manos interactuando y traslación relativa. Código con licencia no comercial; repositorio archivado. Referencia bimanual, no el modelo más reciente. |
| [PAD-Hand, CVPR 2026](https://github.com/DominoAI-Lab/PAD-Hand-CVPR-2026) | Refinamiento de vídeo con inicialización WiLoR y difusión orientada a plausibilidad física. Publica código y checkpoints; la demo no demuestra inferencia causal de webcam. No encontré licencia explícita. |
| [Naruto YOLOX de Kazuhito00](https://github.com/Kazuhito00/NARUTO-HandSignDetection) | Mantenerlo como referencia RGB ya entrenada, con las limitaciones del informe inicial. Reconoce apariencia del sello; no es seguimiento de articulaciones ni SOTA 2026. |

No hay un ranking único útil: precisión de malla en milímetros, FPS del detector y exactitud de nuestros comandos miden cosas distintas. «SOTA» debe indicar tarea, dataset, condición de oclusión y coste; la fecha reciente de un repositorio no resuelve esa comparación.

## Arquitectura concreta para manos superpuestas

**Android por USB → último frame → región de ambas manos → dos ramas de evidencia → fusión causal → gramática → entrenador local.**

1. **Captura:** usar inicialmente la cámara trasera del Android fija frente a ti, con vista previa en el PC. Probar 720p a 60 FPS y comparar 30 FPS si el modo no está disponible o introduce más cola. Es un objetivo, no una capacidad ya verificada del teléfono. Priorizar manos grandes, luz uniforme y exposición corta. La cámara frontal del móvil también se compara si facilita el encuadre. USB reduce una fuente de variación, pero no elimina codificación y buffering.
2. **Región de interés:** delimitar el espacio frente al torso donde haces sellos. Detectar manos dentro de él y mantener además un recorte conjunto con margen. Si al entrelazarlas aparece una sola caja, conservar el recorte conjunto; no descartar automáticamente toda la muestra por no encontrar dos palmas.
3. **Rama de articulaciones:** dos recortes de 256×256 para RTMPose o dos tracks de MediaPipe. Guardar posiciones, características geométricas, identidad temporal y calidad. Nunca ordenar izquierda/derecha solamente por posición horizontal: al cruzarse se intercambiarían. Resolver la inversión de cámara una sola vez.
4. **Rama RGB:** una red pequeña sobre el recorte de ambas manos aprende contorno, solapamiento y contacto visible. Comparar primero el Naruto ONNX existente; después entrenar una cabeza específica o una red compacta con datos propios. Los cuatro sellos, transición y desconocido deben formar parte de la salida. No se entrega aquí un checkpoint nuevo ya entrenado.
5. **Fusión:** concatenar características geométricas, representación RGB y máscaras de calidad; clasificarlas con una pequeña GRU o TCN causal. Empezar comparando 4–8 frames pasados. Esa ventana representa contexto, no obliga a esperar ocho frames desde cada sello; la regla de aceptación determina la espera adicional.
6. **Decisión:** aceptar un sello una vez cuando la evidencia reciente sea estable. Las muestras obsoletas, extrapoladas o ambiguas no deben añadir tokens. Serpiente confirma solo una receta válida y con una condición de aceptación más exigente que los elementos.

La rama geométrica debe conservar **dos escalas de información**. Dentro de cada mano: vectores de huesos normalizados, ángulos y distancias punta-palma. Entre manos: separación de muñecas en la imagen, orientaciones, distancias relativas y patrón de solapamiento. Normalizar cada mano de manera independiente y desechar su posición relativa destruiría parte de la información necesaria para distinguir los sellos.

Las máscaras de calidad propuestas se calculan con consistencia temporal, variación de longitudes aparentes, saltos de identidad, desenfoque, recortes fuera de cuadro y acuerdo entre ramas. Son indicadores que deben calibrarse; no una medida infalible de visibilidad. Una distribución SimCC concentrada o una probabilidad alta del clasificador también pueden estar equivocadas fuera de sus datos de entrenamiento.

No impondría que ambas ramas coincidan siempre: cuando hay oclusión, las articulaciones pueden fallar y el contorno conjunto seguir siendo distintivo. Entrenaría la fusión con pérdida simulada de puntos y con ejemplos reales de oclusión para que aprenda cuándo usar cada evidencia. Para confirmar exigiría información visual reciente suficiente; nunca solo una pose mantenida por extrapolación.

Si una sola vista frontal no separa caballo y tigre con fiabilidad, el siguiente cambio útil es ajustar ligeramente la orientación de las manos durante esos sellos, conservando tu asignación. Una segunda cámara oblicua es una alternativa posterior: mejora observabilidad, pero requiere sincronización y, si se triangula 3D, calibración geométrica. No es requisito de la primera versión.

## Datos propios y evaluación que deciden si funciona

Propuesta inicial de captura: tres sesiones separadas, variando iluminación, manga, distancia y velocidad dentro del uso esperado. Incluir cada sello sostenido, las doce transiciones dirigidas entre los cuatro sellos, las diez recetas completas y actividad normal: teclado, ratón, tocarse la cara, cruzar brazos y descansar. La cámara debe estar en su posición real de juego.

Separar entrenamiento, ajuste y evaluación por sesión o toma completa, no repartir aleatoriamente frames vecinos del mismo vídeo. Etiquetar inicio y fin del sello, transición, desconocido y grado de oclusión visible. No inventar una verdad 3D de dedos que no se ven. Las augmentaciones de imagen no sustituyen vídeos reales de manos entrelazadas.

Comparar sobre el mismo conjunto:

| Variante | Pregunta que responde |
|---|---|
| RGB solamente | ¿Ya basta la apariencia de cuatro sellos personalizados? |
| Articulaciones solamente | ¿Qué información pierde por oclusión? |
| Fusión RGB + articulaciones | ¿Disminuyen confusiones sin demasiada latencia? |
| Fusión + tiempo causal | ¿Disminuyen tokens espurios durante transiciones? |
| WiLoR / OmniHands, si sus condiciones permiten la prueba | ¿La geometría avanzada aporta una mejora medible que compensa el coste? |

Medir precisión y recuperación por sello, matriz de confusión, porcentaje de muestras rechazadas y cobertura. Un sistema que rechaza casi todo puede tener precisión alta y ser inútil. La métrica principal es **receta completa correcta**, con atención a Invoke accidental, duplicados y tokens perdidos. El modo compacto no corrige borrados: perder tigre en mono→tigre→serpiente puede cambiar el hechizo.

Registrar p50, p95 y p99 de sello formado hasta evento; FPS y VRAM con Dota en una escena repetible; edad de cada frame utilizado y latencia de captura. Probar dos manos y la cámara real. Ni FPS sin cámara ni tiempos de una sola mano equivalen al sistema final.

Mantener como metas iniciales **p95 ≤150 ms de sello formado a evento**, menos de 5% de pérdida de FPS mediano de Dota y al menos 95% de recetas completas correctas en el primer piloto. Son umbrales de ingeniería para iterar, no rendimiento obtenido ni suficiencia para uso competitivo. Examinar también tiempos de frame extremos y falsas confirmaciones por hora. Cero errores en treinta minutos solo da evidencia limitada; requiere sesiones más largas.

## Orden de implementación

Primero resolver captura USB y entrenador visual sin salida al juego con YOLOX Naruto preentrenado en GPU. Evaluar sus errores en sesiones independientes; ejecutar el par de articulaciones ONNX, entrenar apariencia y añadir fusión causal únicamente si la comparación lo justifica. Mantener GPU como ruta elegida y resolver sobrecarga ajustando la cadencia y la visualización, con medidas reales. Solo si la fusión ligera no resuelve las oclusiones, evaluar reconstrucción 3D avanzada o una segunda vista.

El siguiente entregable técnico sería un entrenador que muestre cámara, puntos estimados, calidad, sello y receta; debe permitir revisar por qué rechazó una transición. La integración Dota y la distinción entre invocar y lanzar siguen descritas en el [informe general](INFORME.md).

## Qué quedó comprobado en esta actualización

- Mapeo y las diez recetas actualizados; archivo HTML autónomo exportado.
- Lectura de fuentes primarias y de las demos de OmniHands y StableHand para distinguir procesamiento por clips de entrada en vivo.
- Comprobación de disponibilidad HTTP de los paquetes oficiales RTMDet, RTMPose y MediaPipe; revisiones y licencias observadas registradas en `procedencia-vision.json`.
- No se entrenaron modelos, no se ejecutó inferencia de cámara y no se midió rendimiento mientras corre Dota. La comparación anterior fundamenta una implementación; no reemplaza ese experimento.
