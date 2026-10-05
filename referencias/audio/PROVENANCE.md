# Efectos de audio del entrenador

Los cinco efectos activos proceden exclusivamente de [Naruto hand signs](https://www.myinstants.com/en/instant/naruto-hand-signs-40193/), uploader Sasukexshisuixitachi ([MP3](https://www.myinstants.com/media/sounds/ytmp3free_BaQB7oM.mp3), 2,143 s). El usuario identificó cuatro golpes de posturas y un quinto de invocación en ese clip.

| Uso | Golpe de origen | Inicio | Fin | Duración | Archivo |
|---|---|---|---|---|---|
| Mono / Quas | 1 | 0,474 s | 0,730 s | 256 ms | `naruto-monkey.wav` |
| Tigre / Wex | 2 | 0,730 s | 1,084 s | 354 ms | `naruto-tiger.wav` |
| Caballo / Exort | 3 | 1,084 s | 1,292 s | 208 ms | `naruto-horse.wav` |
| Serpiente / receta aceptada | 4 | 1,292 s | 1,528 s | 236 ms | `naruto-snake.wav` |
| Hechizo lanzado manualmente | 5 | 1,528 s | 2,143125 s | 615,125 ms | `naruto-confirm.wav` |

La correspondencia es por postura, cualquiera que sea el orden de la receta. Serpiente reproduce el cuarto al aceptar una receta válida, tanto en el entrenador como con Dota. El quinto espera un lanzamiento manual: GSI debe mostrar el inicio de recarga o el gasto de una carga de uno de los diez hechizos en D/F. Preparar el hechizo, cambiarlo entre ranuras o encontrarlo ya disponible no reproduce ese remate. Sin recarga ni gasto de cargas —por ejemplo, Free Spells en Demo Hero— no hay evidencia para emitirlo. El entrenador local no reproduce el quinto.

Los cortes se hicieron tras analizar RMS por ventanas de 2 ms, respetando las transiciones entre golpes. Se remuestreó a 48 kHz **antes** de recortar por índices de muestra. Cada WAV es mono PCM16, con pico normalizado a 0,75, entrada de 3 ms y salida de 6 ms (18 ms en el final). No se modifica velocidad ni tono. Validación de duración, pico, ganancia y hashes (`runtime/audio-cuts-validation.json`, informe local no versionado).

Los WAV en `src/jutsu_invoker/web/audio/` se precargan desde loopback. No hay descarga de terceros durante el juego. El valor inicial es 65 %; se conserva la preferencia del usuario en Chrome (100 % al cargar estos recortes), configurable en el panel.

Tras la escucha, el usuario confirmó ambos momentos y pidió reducir solo el remate. Su ganancia de reproducción bajó de 0,95 a 0,72 (aproximadamente 24 % menos, −2,4 dB), al mismo nivel de los cuatro sellos. El control de volumen general conserva su valor.

La atribución al anime procede del título del uploader; no se verificó episodio ni fuente oficial. No se atribuye una licencia abierta ni autorización de redistribución a ese upload. Los MP3 y WAV no se suben al repositorio público; se preparan localmente con `scripts/prepare_audio.py`. La fuente activa permanece local para trazabilidad. El archivo local archivado `.archivo/audio/naruto-jutsu-source.mp3`, procedente de [Jutsu Activation](https://www.myinstants.com/en/instant/jutsu-activation/), corresponde al montaje anterior y ya no se usa para la confirmación.
