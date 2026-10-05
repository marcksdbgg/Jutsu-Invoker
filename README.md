# Jutsu Invoker

Prepara los diez hechizos de Invoker usando cuatro sellos de manos de Naruto, con la cámara de un Android conectado por USB. El reconocimiento corre en la GPU y el panel se abre en Chrome.

**Los gestos colocan orbes e invocan; tú lanzas y apuntas con D/F como siempre.** También puedes usar el entrenador sin abrir Dota.

## Qué hace

- Mono → Quas, tigre → Wex, caballo → Exort y serpiente → confirmar la receta.
- Coloca cada orbe al aceptar su sello; serpiente completa los tres e invoca una vez.
- Actúa sobre tu propio Invoker durante una partida, con Dota al frente. Conserva los controles físicos y bloquea el envío al chat y la consola mediante el filtro de entrada.
- Permite ver 21 articulaciones por mano, ajustar la orientación, ocultar el vídeo y calibrar tiempos y umbrales desde el panel.
- Reproduce cuatro efectos por las posturas aceptadas y un remate cuando Dota indica el lanzamiento manual del hechizo.
- Incluye pruebas guiadas de poses y recetas, grabación local y replay de observaciones.

## Requisitos

La implementación actual está orientada a **Linux x86_64, Android por USB y GPU NVIDIA compatible con CUDA 12, TensorRT y NVDEC**. Se comprobó en una RTX 4060, Android HONOR y Chrome con WebCodecs.

Necesitas Python 3.12, `uv`, Android platform-tools (`adb`), FFmpeg, el controlador NVIDIA y Node.js para las pruebas de vídeo y sonido. Android debe permitir depuración USB y estar autorizado en ADB. La captura de cámara requiere Android 12 o posterior.

La integración con Dota utiliza `/dev/uinput` y XI2. La comprobación de foco actual usa **Hyprland y Dota en Xwayland**; otros escritorios, Windows y macOS requieren adaptar esa parte. Un modo de Dota que cambie las ranuras estándar de Invoker se bloquea.

## Instalación

```bash
git clone https://github.com/marcksdbgg/Jutsu-Invoker.git
cd Jutsu-Invoker
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements-gpu.lock
uv pip install --python .venv/bin/python -e .

.venv/bin/python scripts/download_baseline.py
.venv/bin/python scripts/download_scrcpy.py
.venv/bin/python scripts/download_hand_models.py
.venv/bin/python scripts/prepare_hand_models.py
.venv/bin/python scripts/prepare_audio.py

.venv/bin/python -m jutsu_invoker.cli build-engine
.venv/bin/python scripts/verify_tensorrt_parity.py
```

Los instaladores fijan las revisiones y verifican hashes de modelos, servidor de cámara y fuente de audio. Los engines se construyen para la GPU y el entorno local; no se descargan engines de otra máquina. Los paquetes NVIDIA y los pesos pueden ocupar varios GB.

Comprueba la conexión con `adb devices`. Si ADB está fuera de tu PATH, exporta la ruta a `platform-tools` o configura `capture.adb_path` en [la configuración base](config/desarrollo-gpu.toml). El lanzador también busca el SDK en `ANDROID_HOME`, `ANDROID_SDK_ROOT` o `~/Android/Sdk`.

## Entrenador de cámara

```bash
scripts/run_trainer.sh --camera back
```

Abre [el panel local](http://127.0.0.1:32147/) en Chrome. Coloca las manos completas frente a la cámara y mantén cada sello hasta ver su letra aceptada. Serpiente confirma; **Cancelar** borra la receta pendiente. Con varios Android conectados, añade `--serial <dispositivo>`.

El perfil guardado usa cámara trasera y giro **180°**, para el celular colocado boca abajo. Puedes cambiarlo en **Ajustes de detección y vídeo → Más ajustes → Giro**. El giro se aplica también a la imagen que reciben los modelos.

Los ajustes del panel persisten en `config/usuario.json`, que queda fuera de Git. Valores iniciales:

| Parámetro | Valor |
|---|---|
| Reinicio por inactividad | 1,6 s |
| Mono | Score ≥0,75; 100 ms y 4 imágenes frescas |
| Tigre / caballo | Score ≥0,8; 150 ms y 5 imágenes frescas |
| Serpiente | Score ≥0,8; 200 ms y 7 imágenes frescas |
| Margen entre clases | 0,15 |
| Frescura máxima de imagen | 100 ms |
| Búfer de presentación del vídeo | 60 ms |

Mantener visible un elemento ya guardado conserva la receta. Un hueco breve entre imágenes reinicia la estabilidad de la pose y conserva los elementos hasta el plazo de inactividad; una imagen antigua no autoriza enviar teclas. El rótulo **candidato** no significa que se haya aceptado un sello.

## Integración con Dota

En una instalación nueva, registra la ruta del juego y el archivo de controles del jugador:

```bash
.venv/bin/python -m jutsu_invoker.cli install-dota \
  --game-dir /ruta/a/steamapps/common/dota\ 2\ beta \
  --bindings /ruta/a/Steam/userdata/ID/570/remote/cfg/dotakeys_personal.lst
```

`--bindings` debe señalar el archivo VDF real de controles de tu cuenta; [el lector](src/jutsu_invoker/dota.py) exige teclas simples distintas para orbes, Invoke, selección de héroe y las dos ranuras de lanzamiento. La integración genera un token local y la configuración GSI; ambos quedan fuera de Git.

En Steam → Dota 2 → Propiedades → Opciones de lanzamiento añade **`-gamestateintegration`**, conservando las demás opciones, y reinicia Dota.

```bash
scripts/run_trainer.sh --camera back --dota
```

En Chrome abre **Dota · invocar con sellos → Activar invocación**, con chat y consola cerrados. Vuelve al juego y controla a Invoker. El envío exige identidad propia, héroe vivo y sin silencio/stun/hex, partida activa sin pausa, cámara y GSI recientes y foco en Dota.

No necesita cambiar Q/W/E/R ni D/F. Selecciona al héroe antes de cada etapa. Si modificas los orbes manualmente, serpiente reconstruye la fórmula completa. **Nunca envía D/F ni lanza el hechizo automáticamente.** Enter o la tecla de consola en Dota suspenden los sellos; Escape permite continuar.

| Hechizo | Sellos |
|---|---|
| Cold Snap | Mono → serpiente |
| Ghost Walk | Mono → tigre → serpiente |
| Ice Wall | Mono → caballo → serpiente |
| EMP | Tigre → serpiente |
| Tornado | Tigre → mono → serpiente |
| Alacrity | Tigre → caballo → serpiente |
| Sun Strike | Caballo → serpiente |
| Forge Spirit | Caballo → mono → serpiente |
| Chaos Meteor | Caballo → tigre → serpiente |
| Deafening Blast | Mono → tigre → caballo → serpiente |

Para los pares, el primero es el predominante: Ghost Walk envía **Q → W → Q + R**. Deafening Blast acepta los tres elementos en cualquier orden. [Lógica completa, tiempos y límites](DOTA-INTEGRACION.md).

## Sonido

**Activar sonido** o **Activar invocación** desbloquea el audio en Chrome. El volumen inicial es 65 % y se conserva la preferencia del usuario. Los primeros cuatro cortes corresponden a mono, tigre, caballo y serpiente; el quinto acompaña el lanzamiento manual observado en Dota. El remate tiene el nivel reducido solicitado durante la calibración.

GSI permite inferir el lanzamiento por el inicio de recarga o el gasto de una carga, siguiendo la identidad del hechizo en D/F. Prepararlo o cambiarlo de ranura no reproduce el remate. Con **Free Spells** en Demo Hero, si no cambia recarga ni cargas, no hay confirmación sonora del lanzamiento. El entrenador local reproduce solo los cuatro efectos de posturas.

Los clips de audio se preparan localmente y no se incluyen en Git. [Procedencia y cortes](referencias/audio/PROVENANCE.md). Una vez preparados, no se descargan recursos externos durante el juego.

## Pruebas y evaluación

```bash
# Requiere haber preparado los efectos locales con prepare_audio.py.
scripts/run_tests.sh

# Replay sintético; no usa cámara ni envía teclas.
.venv/bin/python -m jutsu_invoker.cli replay datos/ejemplos/chaos-meteor.jsonl

# Diagnóstico de entorno.
.venv/bin/python scripts/preflight.py --output runtime/preflight.json
```

La suite verificada contiene **100 pruebas Python y 13 Node**: recetas, estabilidad, cancelación, entrada manual, chat, identidad, cambios de sesión, HTTP local, vídeo y audio sin duplicados. Las pruebas del núcleo no requieren GPU ni Dota; ejecutar todo requiere NumPy y los cinco WAV locales.

En el panel, **Prueba de precisión** guía poses aisladas o las diez recetas. Los informes y grabaciones se guardan solo en `datos/evaluaciones/` y `datos/clips/`. Un informe es provisional hasta confirmar que se ejecutaron las poses, y necesita revisión del vídeo para una evaluación independiente.

Durante la calibración se observaron los diez hechizos preparados en Demo Hero, y lanzamientos manuales en ambas ranuras. El último piloto de recetas dio 9/10 antes de los últimos ajustes; **no es una garantía de precisión para otras personas, sesiones o modos**. La cámara se comprobó cerca de 30 FPS; el impacto sobre FPS de Dota y la estabilidad térmica prolongada siguen sin medirse. [Historial de calibración](REVISION-Y-CALIBRACION.md).

## Organización

| Carpeta | Contenido |
|---|---|
| `src/jutsu_invoker/` | Captura, GPU, reconocedor temporal, GSI, entrada y panel web |
| `scripts/` | Descarga verificable, preparación y diagnósticos |
| `tests/` | Pruebas del núcleo, servidor, vídeo y audio |
| `config/` | Perfil base y ajustes locales ignorados |
| `diseno/` | Recetas, contratos y ejemplo de GSI |
| `modelos/` | Manifiestos; pesos descargados fuera de Git |
| `investigacion/` | Investigación de repositorios y modelos |
| `referencias/` | Láminas de diseño y procedencia del audio |
| `grafico/` | Explicación interactiva de las recetas |
| `datos/` | Ejemplo sintético; capturas y evaluaciones ignoradas |
| `runtime/` | Estado, tokens, logs y engines locales, todo ignorado |

El repositorio conserva código, documentación, manifiestos y referencias estáticas. El entorno `.venv`, modelos, grabaciones, credenciales, preferencias y diagnósticos de la máquina permanecen locales. Los documentos históricos mencionan informes locales que no están versionados.

[Plan de implementación](PLAN-DE-IMPLEMENTACION.md) · [Modelos preentrenados](investigacion/REPOS-SELLOS-PREENTRENADOS.md) · [Componentes de terceros](THIRD-PARTY.md)
