# Screen Recorder

Screen recorder con selezione area multi-monitor, controllo qualità tramite CRF e interfaccia compatta in stile industrial red.

## Caratteristiche

- Selezione area trascinando con mouse (supporta multi-monitor)
- FPS regolabile (1-60)
- Qualità regolabile tramite CRF H.264:
  - Alta (CRF 18) — visivamente lossless
  - Media (CRF 23) — buon compromesso
  - Bassa (CRF 28) — compressione alta, file piccolo
- Salvataggio in MP4 con H.264
- Anteprima in tempo reale delle dimensioni dell'area
- Finestra sempre in primo piano, senza bordi, trascinabile

## Utilizzo (exe precompilato)

1. Scarica `ScreenRecorder.exe` dalla sezione Releases
2. Esegui il file
3. Clicca **Seleziona Area** e trascina sul monitor per scegliere la regione
4. Imposta FPS e Qualità
5. Clicca **Avvia Registrazione**
6. Premi **Arresta Registrazione** per fermare
7. Scegli dove salvare il file MP4

## Build da sorgente

```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed --name ScreenRecorder `
  --icon ThaSkull.ico `
  --add-binary "path\to\imageio_ffmpeg\binaries;imageio_ffmpeg\binaries" `
  --hidden-import mss --hidden-import imageio_ffmpeg `
  --hidden-import PIL.ImageTk --hidden-import cv2 `
  screen_recorder.py
```

Il percorso di `imageio_ffmpeg\binaries` varia in base all'installazione Python. Puoi trovarlo con:

```python
from imageio_ffmpeg import get_ffmpeg_exe
import os
print(os.path.dirname(get_ffmpeg_exe()))
```

## Dipendenze

- opencv-python
- numpy
- mss
- Pillow
- imageio-ffmpeg
- pyinstaller (per buildare l'exe)

## Come funziona

1. **Cattura**: usa `mss` per catturare lo schermo alla risoluzione nativa e all'FPS richiesto
2. **Codifica**: alla fine della registrazione, passa i frame raw a `ffmpeg` (incluso via `imageio-ffmpeg`) che codifica in H.264 con il CRF scelto
3. **Qualità**: il CRF (Constant Rate Factor) controlla la compressione. Più basso = migliore qualità. CRF 18 è considerato visivamente lossless
4. **Fallback**: se ffmpeg non è disponibile, usa `cv2.VideoWriter` con codec `mp4v`
