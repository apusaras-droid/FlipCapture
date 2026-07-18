# FlipCapture

[English](README.md) | [日本語](README.ja.md)

FlipCapture is a Windows screen-capture and lightweight animation utility. Its features are implemented in a reusable CLI core and exposed through a Tkinter GUI.

## Setup and launch

Install 64-bit Python 3.11–3.13 first and enable `Add python.exe to PATH` in the Python installer. An internet connection is required during setup and when an AI model is downloaded for the first time.

1. Run `setup.bat`. It creates a virtual environment, installs the libraries, and checks dependencies, OCR, and FFmpeg.
2. Run `start_flipcapture.bat`.
3. Select an input mode and capture directory, optionally select a target window, and start monitoring.

A valid existing `.venv` is reused. Installation details are written to `logs/pip-install.log`, and diagnostic results to `logs/setup-diagnostics.log`. Setup can launch FlipCapture when it finishes. For automation, use `setup.bat --no-launch`. To skip installation and run diagnostics only, use `setup.bat --no-launch --skip-install`.

The release ZIP is also available from the repository's [Releases page](https://github.com/apusaras-droid/FlipCapture/releases).

## Main features

- Capture the monitor under the mouse cursor.
- Capture a selected window or interactively select a rectangular region.
- Run Windows Runtime OCR on a selected region and copy the result to the clipboard.
- Create animated WebP, GIF, or MP4 files from captured images.
- Crop with a rectangle or freehand selection.
- Remove backgrounds from people, characters, and objects with `u2net` or `isnet-anime`.
- Automatically find a likely central subject.
- Rotate images and correct skew automatically or from a manually drawn reference line.
- Convert images to full-color SVG, outline SVG, or silhouette SVG and DXF.
- Run continuously in the Windows task tray.
- Switch between English and Japanese, or add custom JSON locale files.
- Restore settings, the selected tab, and window placement on the next launch.

Hotkey monitoring starts automatically about 0.5 seconds after the GUI opens. Disable `Start hotkey monitoring automatically` to use the manual start button instead.

English is the default language. Select Japanese from `Language` to restart the application in Japanese. Additional UTF-8 JSON languages can be added to `locales`; see the [locale file guide](locales/README.md).

Closing the window keeps FlipCapture running in the task tray by default. The tray menu can restore the window, start or stop monitoring, open the capture directory, or exit completely. Disable `Keep running in task tray when closed` to restore normal close behavior.

## Capture controls

In wheel mode:

- `Alt + Wheel Up`: capture the monitor under the cursor.
- `Alt + Wheel Down`: perform the secondary capture.

In mouse-button mode:

- `Alt + Left Click`: capture the monitor under the cursor.
- `Alt + Right Click`: perform the secondary capture.

The secondary capture can target a selected window or open an interactive rectangular selector. The selector freezes only the monitor under the cursor; drag a region and press Enter to save it, or Esc to cancel. Captured mouse input is suppressed instead of being forwarded to the target application. If no target window is selected, the action is skipped without a dialog and recorded only in the log.

`Alt + Middle Click` opens the OCR selector on the monitor under the cursor. Drag over the text and press Enter to recognize it with Windows OCR and copy it to the clipboard. OCR quality can be set to Standard, High accuracy, or Small text. OCR runs locally and does not upload images or recognized text.

Capturing applications running as administrator may require FlipCapture to run with the same privileges. Enabling `Request administrator privileges at startup` causes Windows to display its standard UAC prompt on future launches. FlipCapture does not store credentials.

## Image editing

Select one image from the image list and choose Crop to draw a rectangle or freehand region. The result can overwrite the source or be saved with `_trim` in its name. If that name already exists, FlipCapture adds a suffix such as `_trim_2`.

Enable AI background removal to extract a person, character, or object inside the selected area and save it as a transparent WebP. `u2net` is intended for general images, while `isnet-anime` is intended for illustrations and characters. Models are downloaded on first use, but the image processing itself remains local.

Automatic subject detection selects a foreground candidate based on its size and distance from the image center. The detected rectangle can be adjusted manually before saving.

The Rotate dialog supports 90-degree steps, 180 degrees, automatic skew correction from long lines, and manual correction from a user-drawn horizontal or vertical reference line. Results can overwrite the source or be saved as `_rotated.webp`.

Vectorization supports:

- Full-color SVG for preserving appearance and shading.
- Outline SVG for editable boundaries.
- Silhouette SVG and DXF for CAD or cutting workflows.

Silhouette DXF can include only the closed exterior `LWPOLYLINE` on the `SILHOUETTE` layer, or also add open internal lines such as eyes, mouth, hair, and clothing on the `INTERNAL` layer. One image pixel equals one DXF drawing unit.

## Animation and FFmpeg

Animation output supports `.webp`, `.gif`, and `.mp4`. MP4 requires FFmpeg. FlipCapture checks for FFmpeg at startup and removes MP4 from the GUI when it is unavailable. It searches these locations before the system `PATH`:

- `tools\ffmpeg\bin\ffmpeg.exe`
- `tools\ffmpeg.exe`

WebP and GIF remain available without FFmpeg. The CLI returns an explicit error if MP4 is requested without FFmpeg.

AI model downloads display progress and use a 10-second connection timeout, a 30-second read timeout, and a 180-second overall timeout. Downloads support cancellation and MD5 verification.

Settings are stored in `config/settings.json`. Runtime logs and structured event records are stored in `logs/flipcapture_YYYYMMDD.log`.

## CLI

```powershell
python -m flipcapture windows
python -m flipcapture capture-full --output-dir C:\captures
python -m flipcapture capture-window --hwnd 123456
python -m flipcapture capture-region --left 100 --top 100 --width 1280 --height 720
python -m flipcapture animate frame1.webp frame2.webp -o animation.webp --duration 150
python -m flipcapture vectorize image.webp --mode color
python -m flipcapture vectorize image.webp --mode outline
python -m flipcapture vectorize image.webp --mode silhouette
python -m flipcapture vectorize image.webp --mode silhouette --dxf-internal
python -m flipcapture ocr image.png --quality high
python -m flipcapture rotate image.webp --angle 90
python -m flipcapture deskew image.webp -o corrected.webp
```

## License

FlipCapture is distributed under the GNU General Public License v3.0. The bundled Zen Kaku Gothic New font is distributed under the SIL Open Font License 1.1; its license text is included with the font files.
