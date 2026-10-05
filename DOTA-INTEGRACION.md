# Invocación con sellos en Dota

El enlace coloca orbes al aceptar cada sello y prepara el hechizo al confirmar con serpiente. **Tú lanzas con D/F y apuntas como siempre.** El modo local continúa disponible sin `--dota`.

## Usarlo

En esta máquina ya se instalaron GSI y el enlace de teclas. Steam → Dota 2 → Propiedades → Opciones de lanzamiento debe conservar `-gamestateintegration`. El envío utiliza Q/W/E/R y tu tecla de selección de héroe, leídas de tus controles actuales. No necesita consola ni cargar otro archivo de binds.

```bash
scripts/run_trainer.sh --camera back --dota
```

En [el panel](http://127.0.0.1:32147/), abre **Dota · invocar con sellos** y **Activar invocación**. Vuelve a Dota. Solo actúa con tu Invoker vivo, sin silencio/stun/hex, durante pregame o partida en curso, sin pausa, con cámara y estado recientes y el juego al frente. Se suspende al perder estas condiciones; vuelve a empezar la receta al recuperarlas. No depende del nombre del modo, pero exige las ranuras estándar de Invoker: Q/W/E en 0/1/2 e Invoke en 5. Modos que alteran esas habilidades se bloquean.

## Las diez recetas

El primer sello decide el elemento predominante. Un selector mantenido se acepta una sola vez; volver al mismo no lo duplica. La tabla muestra los orbes nuevos enviados en cada etapa; R significa Invoke, no lanzamiento.

| Hechizo | Sellos | Antes de serpiente | Al confirmar |
|---|---|---|---|
| Cold Snap | Mono → serpiente | Q | Q Q R |
| Ghost Walk | Mono → tigre → serpiente | Q, W | Q R |
| Ice Wall | Mono → caballo → serpiente | Q, E | Q R |
| EMP | Tigre → serpiente | W | W W R |
| Tornado | Tigre → mono → serpiente | W, Q | W R |
| Alacrity | Tigre → caballo → serpiente | W, E | W R |
| Sun Strike | Caballo → serpiente | E | E E R |
| Forge Spirit | Caballo → mono → serpiente | E, Q | E R |
| Chaos Meteor | Caballo → tigre → serpiente | E, W | E R |
| Deafening Blast | Mono → tigre → caballo → serpiente | Q, W, E | R |

Deafening Blast admite los tres selectores en cualquier orden. Ghost Walk necesita **dos Quas y un Wex**; agregar W al final de mono → tigre produciría Tornado.

Se selecciona explícitamente tu héroe antes de cada etapa para evitar aplicar las órdenes a Forge Spirits u otras unidades. Si cambias orbes o selección manualmente entre gestos, el contador de entrada invalida el prefijo: serpiente vuelve a colocar los tres orbes correctos antes de Invoke. Si hay entrada manual durante el envío, se cancela. Los controles físicos no se capturan ni se consumen.

Cancelar o dejar caducar la receta limpia el entrenador, pero conserva en Dota los orbes que ya colocaste. La siguiente receta forma tres orbes nuevos y desplaza los anteriores. Puedes preparar orbes mientras Invoke está en cooldown; serpiente exige que esté disponible y nunca espera ni reintenta automáticamente. Un orbe que no se usa en la receta puede estar sin aprender.

## Tiempos y controles

El plazo entre sellos es **1,6 s** desde la última evidencia fiable de un elemento guardado; mantenerlo visible conserva la receta. Mono requiere 100 ms y 4 imágenes; tigre 90 ms y 4 (~100 ms a 30 FPS); caballo 150 ms y 5; serpiente 200 ms y 7. Se pueden cambiar en **Ajustes de detección y vídeo**, junto a scores, margen y frescura. Guardar ajustes limpia la receta y desactiva la invocación para aplicar el cambio; actívala nuevamente al terminar.

Un hueco breve de cámara (>100 ms) reinicia la estabilidad de la pose, pero conserva los selectores hasta el plazo de inactividad de 1,6 s. Una imagen vieja nunca añade evidencia ni permite enviar teclas. El contexto de Dota tolera ese corte breve; pérdida de foco, chat, cambio de héroe, cámara detenida o pérdida prolongada sí invalidan la receta. Un envío interrumpido invalida los orbes contabilizados; una confirmación nueva y fresca reconstruye los tres antes de R. No se repite el envío fallido automáticamente.

**Sonido:** el panel carga cinco recortes del mismo clip Naruto hand signs ([fuentes](referencias/audio/PROVENANCE.md)), con volumen inicial 65 % y silencio persistentes en Chrome. Mono, tigre y caballo usan los tres primeros golpes al aceptarse; serpiente usa el cuarto cuando completa una receta válida. El quinto espera a que lances manualmente con D/F: se infiere del inicio de recarga o del gasto de una carga en GSI, para uno de los diez hechizos en las ranuras D/F. Preparar un hechizo o encontrarlo disponible no produce el remate. La comparación sigue la identidad del hechizo al cambiar entre ranuras y descarta el estado inicial, cambios de sesión, datos antiguos, regeneración de cargas y cuenta regresiva de una recarga existente. Con Free Spells, si no cambia recarga ni cargas, no hay evidencia y no suena el quinto. El entrenador local solo reproduce los cuatro golpes de posturas. Los candidatos, rechazos y sellos mantenidos no disparan avisos repetidos. Web Audio se habilita con un clic en Activar sonido o Activar invocación; SSE entrega los avisos con Chrome detrás de Dota. El estado HTTP comparte las mismas identidades para no duplicarlos. Reabrir, reconectar o quitar silencio no reproduce eventos antiguos. Los cinco WAV se precargan localmente; durante el juego no se descargan de terceros.

GSI no ofrece aquí una notificación explícita de lanzamiento: la confirmación es una inferencia a partir de `cooldown`, `charges` y `max_charges`, campos también documentados en el [lector Dota2GSI](https://github.com/antonpup/Dota2GSI/blob/master/Dota2GSI/Nodes/AbilitiesProvider/Ability.cs). No se emiten teclas D/F para producirla.

El enlace usa pulsaciones de 25 ms y separación de 25 ms. Después de aceptar serpiente, la parte de envío ocupa nominalmente 200 ms para un selector, 150 ms para dos y 100 ms para tres, incluyendo selección del héroe. Son tiempos programados, no una medición de latencia completa. Una reparación completa usa nominalmente 250 ms. Todo evento caduca en 500 ms. La confirmación GSI tiene un máximo de 1,5 s; si no llega, el modo se desactiva y no repite R.

El dispositivo virtual solo admite tus teclas de orbes, Invoke y selección de héroe: en esta máquina **Q/W/E/R y 2**. No admite D/F. No modifica tus binds ni captura exclusivamente el teclado. El enlace anterior F13–F17 no funcionó en esta sesión y se retiró su línea propia de autoexec; su archivo quedó como referencia inactiva. La integración vigente no depende de él.

**Chat y consola:** GSI sigue informando `playing` con chat abierto, por lo que el envío directo exige XI2. Se observa entrada manual sin guardar texto ni consumir teclas. Enter y la tecla de consola, con Dota al frente, suspenden los sellos; Escape en Dota permite continuar. Las pulsaciones propias se contabilizan por separado para evitar la autocancelación. La entrada manual invalida el prefijo, y una pulsación simultánea adicional conserva su efecto sobre el contador. Activa el modo con chat y consola cerrados: no se puede deducir una ventana de texto que ya estuviera abierta antes de activar el filtro. El usuario comprobó chat vacío, hechizo sin cambios y reanudación tras Escape. Enter en otra aplicación no activa ese bloqueo.

Chrome distingue **candidato** de **aceptado**. Una predicción de tigre con la cara en pantalla puede aparecer como candidata sin enviar W: necesita score, margen, tiempo e imágenes suficientes para aceptarse. No usar ese rótulo candidato como prueba de un sello confirmado.

## Evidencia y límites

Informe local de Dota (`runtime/dota-live-validation.json`, informe local no versionado) conserva acciones y confirmaciones GSI sanitizadas; no incluye token ni identificadores de cuenta. Las pruebas reales iniciales en Demo Hero confirmaron Cold Snap, EMP, Sun Strike, Alacrity y Chaos Meteor con el transporte previo. El usuario confirmó Cold Snap. Los intentos incrementales con teclas dedicadas fallaron y se conservaron en el informe; no se presentan como validación. El nuevo envío directo incremental se registra aparte de las pruebas previas.

La suite contiene 108 pruebas Python y 13 Node. Incluye las diez recetas incrementales, seis órdenes de QWE, reparación por entrada manual, cancelaciones, orbes no aprendidos, cooldown de Invoke, identidad, estado, cambios de sesión/foco, liberación de teclas, modificación de controles, slots alterados, HTTP autenticado y ausencia de reintentos. La detección de lanzamiento cubre los diez hechizos en D/F, cambios de ranura, gasto de cargas, estado inicial y datos inválidos sin producir pulsaciones. XI2 está disponible en este Xwayland; el envío directo se rechaza al activarlo si ese filtro no está disponible.

Otros modos no se han ejercitado individualmente y el FPS de Dota no se ha medido. La cadencia de cámara no demuestra la ausencia de impacto sobre el juego. Las pruebas de precisión de manos siguen siendo sesiones separadas.

La exigencia de `-gamestateintegration` está documentada por [Valve](https://www.dota2.com/newsentry/4491783379124370818). El lector de entrada usa las estructuras XI2 de los headers de X.Org instalados en esta máquina, sin acceso a memoria del juego ni captura exclusiva del teclado.

Comprobación posterior del envío directo: GSI real confirmó selección incremental y Ghost Walk con Q→W→Q→R, además de Cold Snap, EMP, Sun Strike, Chaos Meteor, Alacrity, Forge Spirit y Tornado. Las acciones no incluyeron D/F. Informe actualizado (`runtime/dota-live-validation.json`, informe local no versionado). Los otros modos siguen sin ejercitarse individualmente. El usuario confirmó el bloqueo real del chat.

Después de corregir los cortes breves, GSI confirmó Chaos Meteor tras E→W→E→R. Una repetición encontró Chaos Meteor ya disponible en D y no volvió a enviar R. También se confirmaron Ice Wall y Deafening Blast; el informe acumula ya los diez hechizos observados con envío directo en Demo Hero, en distintas ejecuciones. Esto no constituye una medida de 10/10 precisión ni valida otros modos.

La nueva confirmación de lanzamiento ya registró en GSI real el inicio de recarga de Chaos Meteor, Ghost Walk y EMP en D, y Tornado en F. Ninguna acción del enlace incluyó D/F. La escucha de los cinco recortes queda pendiente de confirmación del usuario.

El usuario confirmó la escucha del cuarto golpe en serpiente y del quinto al lanzar manualmente. A petición suya se redujo solo la ganancia del remate de 0,95 a 0,72 (24 % menos, −2,4 dB); los sellos y el volumen general conservan su nivel.
