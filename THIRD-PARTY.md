# Componentes y referencias de terceros

El código del proyecto, los pesos descargados y los recursos multimedia tienen procedencias distintas. Este repositorio no asigna una licencia nueva a componentes de terceros.

| Componente | Fuente | Tratamiento |
|---|---|---|
| Detector YOLOX-Nano de sellos | [Kazuhito00/NARUTO-HandSignDetection](https://github.com/Kazuhito00/NARUTO-HandSignDetection) | MIT según el repositorio de origen; revisión, licencia y hashes fijados en `modelos/manifiesto-naruto.json`. Descarga local. |
| RTMDet y RTMPose Hand5 | [OpenMMLab MMPose](https://github.com/open-mmlab/mmpose) | Código Apache-2.0; procedencia de exports y pesos en `modelos/manifiesto-articulaciones.json`. Descarga local. |
| Transporte de cámara scrcpy | [Genymobile/scrcpy](https://github.com/Genymobile/scrcpy) | Apache-2.0; servidor oficial 4.1 descargado y verificado localmente. |
| Bibliotecas NVIDIA y CUDA | Proveedores indicados en `requirements-gpu.lock` | Se instalan según sus propios términos. No se distribuyen wheels, engines ni bibliotecas en este repositorio. |
| Efectos de sellos | [Procedencia del audio](referencias/audio/PROVENANCE.md) | Fuentes MP3 y recortes WAV excluidos de Git. `scripts/prepare_audio.py` prepara la instalación local. |
| Láminas de referencia | `referencias/sellos-naruto.png`, `referencias/hechizos-invoker.png` | Material aportado para el diseño y diagnóstico; no se declara licencia abierta ni autoría del proyecto sobre él. |

Naruto y Dota 2 pertenecen a sus respectivos titulares. El proyecto es una integración independiente.
