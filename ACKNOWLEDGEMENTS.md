# Acknowledgements / 謝辞

[English](#english) | [日本語](#日本語)

## English

FlipCapture stands on the work of many open-source developers, researchers, standards groups, and platform maintainers. We sincerely thank everyone who creates, documents, tests, reviews, packages, and supports the following projects and technologies.

### Development disclosure

FlipCapture was developed through iterative AI-assisted coding, including OpenAI ChatGPT/Codex, under human direction. The project owner defined the requirements, selected the features, evaluated behavior, requested corrections, and made the release decisions. AI-generated code and documentation were reviewed and tested before publication.

### Programs, libraries, platforms, and assets

- [Python](https://www.python.org/) and [Tk/Tkinter](https://docs.python.org/3/library/tkinter.html) — application runtime and GUI toolkit.
- [Pillow](https://python-pillow.org/) — image loading, processing, preview, and WebP/GIF output.
- [NumPy](https://numpy.org/), [SciPy](https://scipy.org/), and [scikit-image](https://scikit-image.org/) — numerical processing, masks, contour analysis, line detection, and deskew estimation.
- [MSS](https://github.com/BoboTiG/python-mss) — fast cross-monitor screen capture.
- [pystray](https://github.com/moses-palmer/pystray) — Windows task tray integration.
- [rembg](https://github.com/danielgatis/rembg), [ONNX Runtime](https://onnxruntime.ai/), and [PyMatting](https://github.com/pymatting/pymatting) — local AI background removal and inference support.
- The authors, researchers, and maintainers of the U²-Net and IS-Net models used through rembg.
- [VTracer](https://github.com/visioncortex/vtracer) — raster-to-vector color SVG conversion.
- [ezdxf](https://ezdxf.readthedocs.io/) — DXF generation.
- [PyWinRT](https://github.com/pywinrt/pywinrt) and Microsoft Windows Runtime OCR — local Windows OCR integration.
- [Requests](https://requests.readthedocs.io/) — reliable AI model downloads.
- [FFmpeg](https://ffmpeg.org/) — optional MP4 encoding.
- [Zen Kaku Gothic New](https://github.com/googlefonts/zen-kakugothic) and its authors — the bundled user-interface font.
- [Git](https://git-scm.com/) and [GitHub](https://github.com/) — source control, collaboration, and distribution infrastructure.

Thank you to every contributor to these projects. FlipCapture benefits directly from your engineering, research, documentation, testing, and community support.

### Licensing

FlipCapture itself is distributed under the [GNU General Public License v3.0](LICENSE). Third-party programs, libraries, models, fonts, and other assets remain copyright of their respective authors and are governed by their own licenses. Installing a dependency through `setup.bat` does not change that dependency's license. The bundled Zen Kaku Gothic New license is included at `assets/fonts/OFL-ZenKakuGothicNew.txt`.

## 日本語

FlipCaptureは、多くのオープンソース開発者、研究者、標準化団体、プラットフォーム管理者の成果の上に成り立っています。次のプロジェクトや技術を開発、文書化、テスト、レビュー、パッケージ化、保守してくださっているすべての皆様へ、心より感謝申し上げます。

### 開発方法について

FlipCaptureは、OpenAI ChatGPT/Codexを含むAIとの反復的な対話によるコーディング支援を受け、人間の指示・判断のもとで開発しました。プロジェクト所有者が要件を定め、機能を選択し、動作を評価し、修正を依頼し、公開を判断しています。AIが生成したコードと文書は、公開前に確認とテストを行っています。

### 使用プログラム・ライブラリ・基盤・素材

- [Python](https://www.python.org/)および[Tk/Tkinter](https://docs.python.org/ja/3/library/tkinter.html) — アプリケーション実行環境とGUIツールキット。
- [Pillow](https://python-pillow.org/) — 画像読込、編集、プレビュー、WebP・GIF出力。
- [NumPy](https://numpy.org/)、[SciPy](https://scipy.org/)、[scikit-image](https://scikit-image.org/) — 数値処理、マスク、輪郭解析、直線検出、傾き推定。
- [MSS](https://github.com/BoboTiG/python-mss) — 複数モニター対応の高速スクリーンキャプチャ。
- [pystray](https://github.com/moses-palmer/pystray) — Windowsタスクトレイ連携。
- [rembg](https://github.com/danielgatis/rembg)、[ONNX Runtime](https://onnxruntime.ai/)、[PyMatting](https://github.com/pymatting/pymatting) — ローカルAI背景透過と推論処理。
- rembg経由で使用するU²-Net・IS-Netモデルの研究者、作者、メンテナーの皆様。
- [VTracer](https://github.com/visioncortex/vtracer) — ラスター画像からカラーSVGへの変換。
- [ezdxf](https://ezdxf.readthedocs.io/) — DXF生成。
- [PyWinRT](https://github.com/pywinrt/pywinrt)およびMicrosoft Windows Runtime OCR — WindowsローカルOCR連携。
- [Requests](https://requests.readthedocs.io/) — AIモデルの安定したダウンロード。
- [FFmpeg](https://ffmpeg.org/) — オプションのMP4エンコード。
- [Zen Kaku Gothic New](https://github.com/googlefonts/zen-kakugothic)と作者の皆様 — 同梱UIフォント。
- [Git](https://git-scm.com/)および[GitHub](https://github.com/) — ソース管理、共同作業、配布基盤。

これらのプロジェクトへ貢献されているすべての皆様に感謝いたします。皆様の技術、研究、文書、テスト、コミュニティ活動がFlipCaptureを直接支えています。

### ライセンス

FlipCapture本体は[GNU General Public License v3.0](LICENSE)で配布します。各種プログラム、ライブラリ、AIモデル、フォント、その他の素材の著作権はそれぞれの作者に帰属し、それぞれのライセンスが適用されます。`setup.bat`を通じて依存関係をインストールしても、そのライセンスが変更されることはありません。同梱のZen Kaku Gothic Newのライセンスは`assets/fonts/OFL-ZenKakuGothicNew.txt`に収録しています。
