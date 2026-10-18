# LUTPhoto

Apply video LUTs (.cube) to RAW photos without manual editing. Fully local processing.

## Features

- **Batch processing**: Apply one LUT to multiple RAW files simultaneously
- **Color space options**: Rec.709/sRGB, Adobe RGB, S-Log3 (Sony), F-Log (Fujifilm), V-Log (Panasonic)
- **LUT intensity control**: Blend 0-100% between original and LUT-applied result
- **EXIF preservation**: Camera metadata retained in output JPEG files
- **Real-time progress**: Live updates during batch processing
- **Auto-cleanup**: Results automatically deleted after 1 hour

## Requirements

- Python 3.10+

## Installation (internet needed only once)

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```
