# Revisión del repositorio y calibración inicial de cámara

4 de octubre de 2026. Cámara HONOR trasera por USB, 1280×720, ~30 FPS. Trabajo en la sesión existente de Chrome. Integración con Dota pospuesta por el usuario.

## Resultado real y alcance

| Prueba | Resultado por intentos | Etiquetas | Informe |
|---|---|---|---|
| Sellos/reposo inicial, 80 s | 8/10; captura completa en los diez | Ejecución confirmada por el usuario | [Reporte](datos/evaluaciones/20261004T131356122791Z/report.json) |
| Repetición abortada | Dos intentos con captura suficiente; fuera de totales | Sin confirmación | [Parcial](datos/evaluaciones/20261004T132055288956Z/report.json) |
| Sellos/reposo repetidos, 80 s | 9/10; captura completa en los diez | Ejecución confirmada por el usuario | [Reporte](datos/evaluaciones/20261004T132245725408Z/report.json) |
| Diez recetas, timeout 1,2 s | 0/10; tres eventos de otra receta | Ejecución de las diez confirmada por el usuario | [Reporte](datos/evaluaciones/20261004T132829954661Z/report.json) |

La exactitud por intento mide que al menos 80% de sus imágenes coincidan con el objetivo pedido; no es probabilidad de acertar un comando ni validación en otro día. Los dos pilotos completos de poses suman 17/20 intentos correctos en esta sesión. No repartir sus frames vecinos como si fueran personas o ensayos independientes.

En la segunda toma: mono, tigre, caballo y reposo 2/2; serpiente 1/2. Se revisaron imágenes de los fallos. El primer tigre era elegido como carnero por el modelo; en serpiente aparecieron rata/dragón durante un cambio de altura/orientación. Son hipótesis de sensibilidad visual respaldadas por imágenes y salida, no una atribución de error al usuario. La disposición de dedos ocultos no queda demostrada desde una sola vista.

Un recorte fijo [320,180,960,684] sobre la segunda grabación, comparado con PTS exactos, empeoró a 8/10 frente a 9/10. No se activó ese recorte. El análisis por umbrales en 1.817 imágenes de mantenimiento mostró una decisión válida en reposo al bajar score a 0,65/0,70; con 0,75 y 0,80 no apareció en esas ventanas. Se conserva 0,80 y margen 0,15 por prudencia experimental; no se demuestra tasa cero de activaciones con doce segundos de reposo. Calibración y barrido (`runtime/calibracion-camara.json`, informe local no versionado).

Las recetas expusieron un problema distinto: numerosas caducidades, pérdida de elementos y secuencias equivocadas. El timeout de 1.200 ms pasó a **3.000 ms**, y la guía ahora muestra el siguiente sello según el prefijo observado. La receta objetivo permanece fija; todos los eventos, incluidos los equivocados o repetidos, se conservan y afectan al resultado. No se filtran comandos para aparentar aciertos. **El ajuste necesita una nueva prueba real**; no se cambió el modelo ni se entrenaron pesos.

## Revisión de la implementación

Se revisaron captura/protocolo scrcpy, NVDEC y timestamps, contrato del ONNX, CUDA/TensorRT, estados/gramática, servidor HTTP, CLI/scripts, interfaz, capturas/informes, especificaciones, investigación y lógica del gráfico de recetas.

Cambios derivados de la revisión:

- H264 Baseline/Level 3.1 explícito; grabación real comprobada con ffprobe: 1280×720 y cero B-frames. Chrome muestra el vídeo con su decoder compatible. No se afirma aceleración del navegador; NVDEC/CUDA/TensorRT están activos en reconocimiento.
- Evaluación con objetivo independiente del detector, preparación/mantenimiento/reposo, observaciones JSONL, confusión, exclusiones y vídeo enlazado. Imágenes obsoletas o captura insuficiente no cuentan como aciertos de reposo.
- Frescura comprobada también después de inferir; las ventanas usan timestamp de captura. Las pausas programadas de preparación no se presentan como cortes inesperados de cámara.
- PTS, cajas y clases originales incluidos en observaciones nuevas para localizar los fallos exactamente en el vídeo. Primera toma anterior a ese campo: revisión de imágenes con alineación aproximada, expresamente indicada.
- Conservación del último informe al reiniciar y confirmación de etiquetas sin perder ensayos ni sustituir sus umbrales históricos.
- Dibujo de referencia sobre vídeo, avisos de otros sellos rechazados y guía de secuencia. Corregido desbordamiento a 390 px; tamaño de Chrome restaurado.
- Documentación de estado sincronizada; eliminado `exit_score` inactivo de la receta y declarada la configuración TOML como autoridad de umbrales. Replay usa esa configuración.

Validación: **36 pruebas automatizadas**; diez recetas y permutaciones; frescura, huecos, latch, protocolo fragmentado, GOP, grabación, controles locales, evaluación, reinicio de informes y timeout ampliado. La configuración vigente exige 150 ms/5 imágenes para elementos y 200 ms/7 para serpiente; el replay de capturas reales sigue identificado como evaluación retrospectiva. Detector de calidad de interfaz: cero fallos; aviso de guiones en valores iniciales, que son indicadores vacíos de métricas.

## Lo que queda para avanzar

La cámara y la recogida de evidencia funcionan. La confirmación de recetas todavía falla: validar el ajuste temporal/guía, revisar los fallos restantes y repetir en una sesión separada con negativos de teclado/ratón/transiciones. El piloto de reposo es demasiado corto para medir una tasa de falsas confirmaciones por hora. No se midió latencia absoluta del sensor, pico de VRAM con juego ni rendimiento compartido.

El adaptador GSI/uinput está preparado en código, desactivado por defecto y sin prueba de juego. El archivo preparado permanece fuera de Dota; no se envió entrada al juego. Hace falta probar sus datos reales y controles después de la calibración visual. RTMPose está activo como diagnóstico de articulaciones; no interviene en la decisión del sello ni en la confirmación. La fusión entrenada permanece pendiente de evidencia.

## Corrección de transiciones y articulaciones

El usuario confirmó que realizó las diez secuencias. El informe conserva 0/10 y los tres eventos erróneos; no se sustituyeron sus umbrales históricos.

La causa de las cancelaciones era temporal: el plazo se medía desde el último token aceptado, incluso manteniendo la pose visible. Además, volver a un selector tras perderlo cancelaba toda la fórmula. Ahora el último frame fiable de un elemento ya guardado renueva la actividad; desconocido/ambigüedad conserva el prefijo durante 3 s, sin añadir evidencia ni renovar el plazo. Volver a un elemento elegido se ignora sin cancelar. Una pose nueva exige 150 ms/5 imágenes; serpiente exige 200 ms/7. Los huecos >100 ms, frames viejos, reinicio de cámara y cancelación manual conservan sus reglas.

Se contrastó el patrón de secuencias con permanencia temporal de [gesturecontrol](https://github.com/Mizuna737/gesturecontrol). Implementación propia de la gramática; no se instaló ni ejecutó su automatizador. [RTMPose de OpenMMLab](https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose) proporciona detector RTMDet-nano de manos y 21 articulaciones RTMPose-m Hand5.

Articulaciones: archivos oficiales y SHA fijados en [manifiesto](modelos/manifiesto-articulaciones.json). RTMDet 320 BGR y pose 256 RGB, recorte afín 1,25; preprocessing y ambos modelos en CUDA. Se extrajeron cajas/puntuaciones antes del NMS del export y se hace NMS en CUDA; pesos sin cambios. Batch de pose fijado a uno, hasta dos manos, diagnóstico limitado a 15 Hz. Pipeline antiguo indica 192×256 en transforms, pero grafo y SimCC especifican 256×256: se usa este contrato comprobado.

Los puntos se vinculan al PTS del vídeo: solo datos anteriores dentro de 150 ms, y datos recientes dentro de 300 ms. Se retiran al perder vídeo/conexión. Respuestas bajas aparecen en gris; los dedos ocluidos pueden estar mal localizados o ausentes. No se inventa una segunda mano ni se presenta este dibujo como precisión anatómica medida.

Validación CUDA (`runtime/articulaciones-validacion.json`, informe local no versionado): ambos perfiles contienen exclusivamente CUDAExecutionProvider; error máximo normalizado de detector 0,00000018, media afín 0,00454 respecto a OpenCV. Una mano en imagen local: mediana 11,1 ms y p95 19,5 ms para la rama completa en ese ensayo, sin medir precisión de joints. En cámara con ambos modelos ~30 FPS, CPU del proceso ~0,28 hilos; métricas de esta sesión, sin benchmark compartido con Dota.

Replay de las diez recetas (`runtime/recetas-replay-mejora.json`, informe local no versionado): nueva política 3/10 frente a 0/10 original; desaparecen las caducidades en esa evidencia. Objetivos no entran al reconocedor. Se cuentan recetas erróneas y dobles. Es un ajuste sobre capturas existentes, **no una nueva medida de precisión**. Persisten sellos visuales omitidos o confundidos; temporalidad no recupera un sello que el clasificador nunca observó con confianza.

Comprobación interactiva posterior: usuario confirmó puntos visibles y Cold Snap tras mono mantenido 4–5 s, neutro ~0,5 s y serpiente. Chrome mostró además recetas en prueba libre, sin etiquetas de objetivo ni métrica formal. Próximo ensayo: las diez recetas con esta configuración y guía; Dota sigue desactivado.

## Teléfono invertido y confusión tigre/carnero

El usuario colocó el teléfono cabeza abajo para usarlo así de forma habitual. `capture_orientation_degrees=180` se pasa como `capture_orientation=180` al servidor scrcpy 4.1: la rotación ocurre antes de codificar y alcanza vídeo, NVDEC, ambos modelos, coordenadas y grabaciones. No se aplica solo CSS. [Documentación oficial de giro](https://github.com/Genymobile/scrcpy/blob/v4.1/doc/camera.md#rotation). Valor persistente en config/desarrollo-gpu.toml; 0 devuelve la orientación anterior. Los nuevos sidecars y observaciones registran este valor.

El usuario hizo posteriormente su propia prueba completa: [reporte](datos/evaluaciones/20261004T141531245102Z/report.json), 8/10, provisional hasta confirmar específicamente las diez ejecuciones. Deafening Blast produjo Ghost Walk: Q/W aceptados, pero faltó E antes de serpiente. Ghost Walk no produjo receta: la pose de tigre se elegía como carnero ~0,90 y expiró Q. No se bajó el umbral de aceptación ni se asignó carnero directamente a W.

Dos imágenes del mismo vídeo, alineadas con PTS exactos: frame 1000, tigre original ~0,886; frame 4145, carnero original ~0,897. En el segundo, la vista reflejada detectó tigre ~0,899 y contexto cuadrado 3,5 veces el mayor lado de la caja ~0,878. Se añadió un refinamiento limitado: solo ante carnero ≥0,5, ambas vistas deben elegir tigre con score ≥0,85 y margen ≥0,15. La respuesta usada toma el mínimo de las vistas. Las clases soportadas originales se conservan. Las dos vistas son transformaciones correlacionadas; su acuerdo no equivale a probabilidad calibrada ni a dos muestras independientes.

Implementación CUDA en tiger_refinement.py; no usa el objetivo del piloto. Detecciones originales y ambas vistas permanecen en los metadatos de observaciones. La estabilidad temporal sigue siendo obligatoria. Dos inferencias adicionales solo en el caso ambiguo.

Validación retrospectiva (`runtime/tiger-refinement-validation.json`, informe local no versionado): recupera frame 4145 como tigre; conserva frame 1000. En 303 frames muestreados de la toma de poses previa, 290/303 decisiones correctas antes y después, cero cambios y cero tigres fuera de intentos de tigre. Hay 60 frames de reposo y aproximadamente 60 de cada sello. **No hay ensayo negativo específico de carnero real**: falta medir si esta corrección confunde esa pose o transiciones nuevas. No se afirma 100% ni precisión en otra sesión.

Después de corregir el giro, el usuario confirmó haber realizado dos intentos de tigre; el historial contiene aceptaciones W. No hubo segmentación independiente de ambos intentos para medir 2/2. El refinamiento posterior se verificó con imágenes guardadas y pruebas de lógica; necesita una nueva toma para medir su mejora en cámara.

Validación actual: 40 pruebas automatizadas, incluyendo discrepancia entre vistas, umbral/margen, conservación de otros sellos y metadatos originales; JS y compilación sin errores. Cámara activa ~30 FPS con orientación 180°; Dota permanece desactivado.


## Ajuste solicitado: mono, reinicio de 1,6 s y configuración personal

El usuario reporta buenas combinaciones, vídeo irregular y mono lento al iniciar. Se conserva el modelo y se cambia únicamente la aceptación de mono a score ≥0,75, estabilidad 100 ms y cuatro imágenes frescas; antes compartía 0,8, 150 ms y cinco. Tigre/caballo y confirmación conservan sus valores. El barrido retrospectivo de 1.817 imágenes tenía cero decisiones soportadas en reposo a 0,75; es evidencia de calibración limitada, no validación del perfil nuevo. El timeout solicitado pasa de 3.000 a 1.600 ms, conservando la semántica de actividad desde evidencia fiable del elemento ya guardado.

Panel debajo del vídeo: reinicio, estabilidad/confianza de mono y búfer. El desplegable **Más ajustes** expone mínimos de imágenes, estabilidad/score de otros sellos, margen, liberación, frescura/huecos, FPS de presentación, frecuencia de joints, refinamiento de tigre y giro. Guardado atómico local en `config/usuario.json`, con validación numérica/tipos/rangos y restauración del TOML base. Cambio entre fotogramas cancela receta pendiente y desarma el adaptador de Dota; giro reconecta. Una prueba activa impide modificar valores, y una prueba nueva no arranca mientras haya cambios pendientes. Los informes anteriores conservan sus umbrales históricos.

La vista previa dibujaba lotes inmediatamente: intervalos entre dibujos de 1,6–94,4 ms, p95 91,2 ms, aunque el contador era ~30 FPS. Se separa decodificación de presentación y se programa por PTS con `requestAnimationFrame`: búfer configurable 60 ms, cola máxima ocho frames, cierre de recursos y descarte de imágenes decodificadas antiguas. Las dependencias comprimidas siguen completas. [WebCodecs](https://www.w3.org/TR/webcodecs/) define timestamps de VideoFrame/EncodedVideoChunk en microsegundos, usados para esta sincronización. La ventana posterior dio 33,3–33,4 ms, p95 33,4 ms a ~30 FPS. Búfer añade retraso al vídeo; no a la gramática ni inferencia. Pestaña oculta suspende presentación y receta/historial no se reconstruyen cada 75 ms.

Verificación: **48 pruebas Python + 5 Node**, JS y compilación correctos, guardado real desde Chrome comprobado, panel legible en escritorio y a 390 px sin desbordamiento. Métricas (`runtime/preview-fluidity.json`, informe local no versionado). Último piloto anterior: 9/10 recetas en `datos/evaluaciones/20261004T143521341975Z/report.json`, provisional. El ajuste nuevo de mono y timeout requiere una toma posterior para cuantificar precisión; no se reutiliza 9/10 como resultado del cambio. Cámara trasera permanece a 180°, Dota desactivado.


## Integración con Dota y selección progresiva

Se habilitó la integración a petición del usuario después de la calibración. Las menciones anteriores a Dota desactivado describen esas pruebas históricas. La guía vigente es [DOTA-INTEGRACION.md](DOTA-INTEGRACION.md).

GSI real y autenticado confirmó hechizos preparados en Demo Hero con el primer transporte por teclas normales. El usuario confirmó Cold Snap; también se observaron EMP, Sun Strike, Alacrity y Chaos Meteor en la ranura D. Estos resultados no validan automáticamente el transporte nuevo ni todas las partidas. GSI mantuvo `activity=playing` con chat abierto: **ese campo no detecta por sí solo el chat**. Por eso el enlace actual utiliza teclas dedicadas no textuales F13–F17 y comprueba entrada manual, sin modificar Q/W/E/R ni D/F. El enlace se carga por autoexec al reiniciar, evitando depender de la tecla de consola del teclado español.

El envío progresivo coloca un orbe por selector y completa únicamente los recuentos restantes con serpiente. Ghost Walk recibe Q, W, Q+Invoke; Tornado W, Q, W+Invoke. La entrada manual invalida el prefijo y obliga a completar tres orbes nuevos. Cancelaciones no desactivan permanentemente el modo ni revierten los orbes ya colocados. Los cambios de contexto eliminan la receta pendiente; nunca se reproduce al volver a Dota. No se lanzan hechizos.

Verificación automatizada: 82 pruebas Python + 5 Node; incluye las diez recetas incrementales, seis órdenes de QWE, reparación de prefijo, cooldown, orbes sin aprender, duplicados, cambios de foco/sesión, slots alterados, teclas modificadas, autenticación HTTP, liberación de teclas, falta de confirmación y ausencia de reintentos. XI2 está disponible en esta sesión Xwayland. El informe real registra aparte qué etapas se han comprobado en el juego.

La primera comprobación incremental falló: los eventos fueron reconocidos, pero el enlace se cancelaba tras F17. En este Xwayland F13–F17 no tienen keysym F13–F17; el contador confundía esas teclas propias con entrada manual. Se corrigió la exclusión usando los keycodes evdev reales 191–195, verificados en `/usr/share/X11/xkb/keycodes/evdev` y los códigos Linux 183–187. Una prueba de regresión cubre las cinco teclas propias frente a Q, Shift y clic de selección. Esta corrección requiere una nueva comprobación real; no se presenta el intento fallido como éxito.

Tras corregir el contador, F13–F17 se enviaron sin autocancelación, pero el usuario confirmó que no aparecieron orbes y Ghost Walk quedó sin confirmación GSI. A petición del usuario, el transporte vigente vuelve a las teclas normales verificadas Q/W/E/R y selección 2, con envío incremental Q→W→Q→R para Ghost Walk. Solo se retiró la línea propia de autoexec; los binds personales quedaron intactos. XI2 separa una pulsación propia esperada de una pulsación manual adicional del mismo código y bloquea chat/consola con Enter; Escape dentro de Dota permite continuar. Sin XI2 se rechaza activar el transporte directo. Activar requiere tener chat/consola cerrados, puesto que no hay un estado GSI fiable de ese foco. Chrome muestra candidato/aceptado para aclarar predicciones de la cara que no generan W. La suite vigente contiene 85 pruebas Python + 5 Node.

El transporte directo incremental quedó confirmado por GSI auténtico en Demo Hero: Ghost Walk tras Q→W→Q→R, junto a Cold Snap, EMP, Sun Strike y Chaos Meteor. Se conservaron las etapas de selector y confirmación en `runtime/dota-live-validation.json`; no hubo entradas D/F. Nuevas protecciones cubren overrides `Units` de Invoker, bindings alternativos modificados y entrada manual que aparece justo antes de enviar. Suite: 87 pruebas Python + 5 Node.

### Cortes breves de cámara y sonido · 2026-10-04

El usuario confirmó que el chat quedó vacío, el hechizo no cambió y Escape reanudó los sellos. Después reportó que caballo→tigre se borraba antes de un segundo. Se identificaron dos cancelaciones adicionales al timeout: el hueco/edad de vídeo de 100 ms y el cambio de contexto que ese retraso provocaba en Dota. Ahora los cortes breves reinician evidencia de pose, conservando el prefijo hasta 1,6 s de inactividad; datos atrasados nunca renuevan el plazo ni habilitan teclas. Pérdida real de foco/estado/cámara sigue cancelando. Un envío interrumpido invalida el seguimiento de orbes y requiere una confirmación nueva, sin reintento automático. Enter fuera de Dota ya no activa el bloqueo de texto.

Se añadió percusión ninja sintetizada, una vez por selector aceptado y por confirmación de serpiente, con volumen inicial 35 % y silencio persistentes en Chrome. SSE local permite entregar el aviso sin depender de temporizadores en segundo plano. El historial no se reproduce al abrir, reconectar ni quitar silencio. 93 pruebas Python + 10 Node pasan; panel comprobado en Chrome, escritorio y 390 px. La prueba real posterior de caballo→tigre→serpiente y escucha queda pendiente de respuesta del usuario.

Comprobación posterior real: Chaos Meteor confirmado por GSI tras E→W→E→R; la repetición quedó `already_available` sin repetir Invoke. Ice Wall y Deafening Blast también observados. Los diez hechizos constan ahora en el historial directo acumulado de Demo Hero; no se presenta como piloto etiquetado 10/10. Escucha del sonido pendiente de confirmación del usuario.

### Audio ajustado tras la escucha del usuario

El usuario confirmó que el par conserva sus elementos y prepara Chaos Meteor, pero pidió el efecto del anime y más volumen. Se sustituyó el sintetizador por dos recortes con [procedencia documentada](referencias/audio/PROVENANCE.md): 260 ms para sello aceptado y 560 ms para hechizo preparado, precargados desde loopback; volumen inicial y actual 65 %. En modo Dota la confirmación depende de GSI o del hechizo ya disponible en D, sin sonido de éxito al reconocer una receta cuyo envío falla. En modo local confirma la receta. Canal SSE y sondeo comparten identidad para evitar duplicados. 94 Python + 12 Node pasan. Escucha final de los clips pendiente.

### Recortes del mismo clip de cinco golpes

El usuario pidió que los tres primeros sonidos de Naruto hand signs acompañen las posturas y su remate final confirme Invoke. Se aislaron 1→mono (256 ms), 2→tigre (354 ms), 3→caballo (208 ms) y 5→confirmación (615,125 ms), omitiendo 4. Serpiente no suena antes de la confirmación del juego. Se conserva la preferencia de volumen de Chrome (100 % al cargar los recortes; valor inicial 65 %), la entrega SSE y el bloqueo de sonidos repetidos. Cortes, niveles y hashes (`runtime/audio-cuts-validation.json`, informe local no versionado); [procedencia](referencias/audio/PROVENANCE.md). Suite: 94 Python + 13 Node.


### Cuarto golpe para serpiente y remate al lanzar · 2026-10-04

El usuario cambió la asignación: se añadió el cuarto golpe (1,292–1,528 s, 236 ms) a serpiente cuando acepta una receta válida. El quinto ya no acompaña Invoke ni un hechizo disponible en D: espera el lanzamiento manual con D/F, inferido del inicio de recarga o del consumo de una carga en GSI. La comparación sigue la identidad del hechizo en D/F y descarta el estado inicial, la recarga ya en curso, cambios de sesión y datos antiguos. No envía teclas de lanzamiento. Sin cambios de recarga/cargas (Free Spells), no genera remate; el entrenador local conserva solo los cuatro golpes de posturas. Los cinco WAV están precargados en Chrome y se conserva el volumen del usuario (100 %, valor inicial 65 %). Suite: 100 Python + 13 Node. La escucha y el lanzamiento manual reales de este cambio están pendientes de respuesta; los diez hechizos preparados previamente siguen siendo evidencia distinta. Cortes (`runtime/audio-cuts-validation.json`, informe local no versionado), [procedencia](referencias/audio/PROVENANCE.md), [integración](DOTA-INTEGRACION.md).

Comprobación real posterior: GSI registró inicio de recarga de Chaos Meteor, Ghost Walk y EMP en D, y Tornado en F. El enlace no emitió D/F. Estos son eventos de lanzamiento distintos de las confirmaciones de preparación; la escucha del remate queda pendiente del usuario.

El usuario confirmó la escucha del cuarto golpe en serpiente y del quinto al lanzar manualmente. A petición suya se redujo solo la ganancia del remate de 0,95 a 0,72 (24 % menos, −2,4 dB); los sellos y el volumen general conservan su nivel.


### Respuesta de tigre · 2026-10-05

Se separó la aceptación de tigre de la de caballo. Tigre conserva score ≥0,8 y margen ≥0,15; necesita cuatro imágenes frescas y 90 ms en lugar de cinco y 150 ms. A 30 FPS cuatro imágenes abarcan unos 99 ms: exigir 100 ms exactos podía obligar a esperar la quinta por redondeo de PTS. Imágenes débiles, ambiguas, antiguas o de otras clases siguen reiniciando el candidato; no se acumulan a través de una transición. Mono, caballo y serpiente conservan sus perfiles. Confianza, estabilidad y mínimo de imágenes de tigre se editan en el panel y las preferencias anteriores conservan sus otros valores.

Replay de las mismas 22 pruebas medidas de poses/repose del 4 de octubre: cuatro intentos de tigre aceptados en ambos perfiles; cero aceptaciones W en los otros 18. Desde la primera evidencia fiable de tigre, los tiempos pasan de [825,06; 297,02; 165,01; 165,01] ms a [330,03; 231,02; 99,01; 99,01] ms. Son pruebas retrospectivas de la toma usada para calibrar, no una nueva medida de precisión ni latencia desde el sensor. Informe local no versionado: `runtime/tiger-latency-replay.json`.

El refinamiento continúa exigiendo espejo y contexto independientes con score ≥0,85. Si el espejo falla, se omite la segunda inferencia, pues el acuerdo ya es imposible; no se altera la clasificación. No se atribuye una mejora de latencia GPU medida a este ahorro. La [guía primaria de MediaPipe](https://ai.google.dev/edge/api/mediapipe/python/mp/tasks/vision/GestureRecognizer) también describe el descarte de imágenes para reducir latencia en streaming; aquí se conserva el productor existente con una sola imagen pendiente y timestamps frescos, sin añadir otro modelo. Suite: 108 Python + 13 Node.


### Desconexión por reescritura de controles · 2026-10-05

GSI seguía recibiendo el estado del propio Invoker, pero el enlace estaba desarmado con «Las teclas de Dota cambiaron». El hash del archivo de controles difería del instalado, aunque Q/W/E/R, selección 2 y lanzamiento D/F seguían iguales. El historial anterior mostraba Tornado confirmado antes del bloqueo. Comparar todos los bytes trataba una reescritura ajena a esos controles como una modificación de entrada.

La instalación registra ahora una firma de los controles efectivos: habilidades y variantes, selección, modos/modificadores, opciones por héroe y órdenes sobre teclas protegidas. Se ignoran formato, metadatos y controles ajenos; siguen bloqueándose modificaciones relevantes y colisiones nuevas. Las instalaciones antiguas mantienen el hash estricto hasta volver a instalar explícitamente. Se registró la firma local y se reinició el entrenador manteniendo URI/token GSI, sin modificar los controles físicos ni exigir reinicio de Dota. El enlace volvió a armarse y recibe estado reciente. La comprobación posterior con gestos se registra aparte cuando haya evidencia del juego.

Suite: **114 Python + 13 Node**, todas correctas. Se añadieron regresiones para formato/metadatos y teclas ajenas permitidas, y para variante de lanzamiento, colisión, modo y override de Invoker bloqueados.
