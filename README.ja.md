# FlipCapture

[English](README.md) | [日本語](README.ja.md)

Windows向けの連続スクリーンキャプチャ／簡易アニメーション作成ツールです。CLIを中核として、Tkinter GUIから同じ機能を利用します。

## セットアップと起動

事前に64bit版Python 3.11～3.13をインストールし、インストール画面で`Add python.exe to PATH`を有効にしてください。セットアップおよびAIモデルの初回取得にはインターネット接続が必要です。

1. `setup.bat`を実行します。仮想環境の作成、ライブラリ導入、依存関係・OCR・FFmpeg診断まで自動で行われます。
2. `start_flipcapture.bat`を実行します。
3. 入力方式、保存先、必要なら対象ウィンドウを選び「監視開始」を押します。

既存の`.venv`が正常なら再利用されます。導入ログは`logs/pip-install.log`、診断結果は`logs/setup-diagnostics.log`へ保存されます。セットアップ完了後は、そのままFlipCaptureを起動することもできます。自動処理では`setup.bat --no-launch`、ライブラリ導入を省略して再診断する場合は`setup.bat --no-launch --skip-install`を使用できます。

配布用ZIPはリポジトリの[Releasesページ](https://github.com/apusaras-droid/FlipCapture/releases)からも取得できます。

初期設定ではGUI起動から約0.5秒後にホットキー監視が自動で始まります。「起動時にホットキー監視を自動開始」を無効にすると、監視開始ボタンによる手動操作へ戻せます。

初期表示言語は英語です。画面上部の`Language`から日本語へ切り替えられ、選択すると新しい言語で自動再起動します。独自言語は`locales`へUTF-8 JSONを追加できます。形式は[言語ファイルの説明](locales/README.md)を参照してください。

閉じるボタンを押しても初期設定では終了せず、タスクトレイでホットキー監視を継続します。トレイメニューから画面表示、監視開始／停止、保存フォルダ表示、完全終了ができます。通常の閉じる動作へ戻す場合は`Keep running in task tray when closed`を無効にします。

入力方式、保存先、OCR画質、矩形／ウィンドウ方式、通知・トレイ設定、アニメーション設定、前回のタブ、ウィンドウ位置とサイズは自動保存され、次回起動時に復元されます。

初期設定では`Alt＋ホイール上`がマウスカーソルのあるモニター、`Alt＋ホイール下`が第2キャプチャです。「Alt＋左右クリック」へ切り替えた場合、左クリックがカーソル位置のモニター、右クリックが第2キャプチャになります。第2キャプチャは指定ウィンドウまたは毎回選択する矩形範囲から選べます。矩形方式では画面を固定表示し、ドラッグ後にEnterで切り抜いて保存します。Escでキャンセルできます。該当する入力は対象アプリへ送られません。指定ウィンドウが未選択の場合、その操作は画面通知なしでスキップされ、ログにのみ記録されます。

`Alt＋マウスホイールクリック（中ボタン）`はOCR専用です。カーソルがあるモニターを固定表示し、文字範囲をドラッグしてEnterを押すと、Windows標準の日本語OCRで認識してクリップボードへコピーします。OCR画質は「標準／高精度／小さい文字」から選べます。OCRはPC内で実行され、画像や文字を外部サービスへ送信しません。

管理者として動いているアプリ上の入力を取得するには、本ツール側も同じ権限が必要になる場合があります。認証情報は保存しません。

「起動時に管理者権限を要求」を有効にすると、次回以降のGUI起動時にWindows標準のUAC確認が表示されます。有効にした直後、その場で管理者権限による再起動を選ぶこともできます。無効に戻せば通常権限で起動します。

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

`animate`の出力拡張子には`.webp`、`.gif`、`.mp4`を指定できます。MP4にはPATH上のFFmpegが必要です。

起動時にFFmpegを検証し、見つからない場合はGUIのMP4選択肢を無効化します。PATH以外に`tools\ffmpeg\bin\ffmpeg.exe`または`tools\ffmpeg.exe`へ配置したバイナリも自動検出します。CLIでMP4を指定した場合は明示的なエラーを返します。

AIモデルの初回取得画面には進捗率を表示します。接続10秒、データ待機30秒、全体180秒のタイムアウトを設け、キャンセル操作とMD5検証に対応しています。

設定は`config/settings.json`、動作ログとJSON形式の操作イベントは`logs/flipcapture_YYYYMMDD.log`に保存されます。

画像一覧で画像を1枚選択して「トリミング」を押すと、ドラッグ操作で保存範囲を指定できます。元画像への上書き、または元の名前に`_trim`を付けた新規画像としての保存を選べます。同名の別画像がすでにある場合は`_trim_2`のように連番を付けます。

画像一覧の「回転」では、左90度、右90度、180度に加え、画像内の長い直線を使った自動傾き補正ができます。「基準線を手動指定」では、水平または垂直にしたい線の始点と終点をクリックして補正できます。結果をプレビューしてから、元画像へ上書きまたは`_rotated.webp`の別名で保存できます。

トリミング画面の「AIで切り出し、背景を透過」を有効にすると、選択範囲内の人物・キャラクター・小物を抽出して透過WebPで保存します。`u2net`は汎用、`isnet-anime`はイラスト／キャラクター向けです。AIモデルは初回使用時に自動取得されるため、初回だけ時間とインターネット接続が必要です。画像は外部サービスへ送信されず、処理はPC内で行われます。

「中央の対象を自動検出」は、前景候補の面積と画像中央への近さから対象を選び、トリミング範囲を自動設定します。検出後の矩形はドラッグで指定し直せます。複数の対象がある画像では、保存前に範囲を確認してください。

「フリーハンド」を選ぶと、マウスで囲んだ範囲の外側を透明化できます。AI背景透過と併用した場合、囲み線はAIへの制約として働き、範囲内ではAIが小物やキャラクターの輪郭を抽出します。フリーハンド使用時の出力は透過WebPです。

画像一覧の「ベクター化」では、フルカラーSVG、輪郭線SVG、シルエットSVG＋DXFから方式を選択できます。フルカラーは見た目重視、輪郭線は編集用、シルエットはCADや切断加工向けです。DXFでは1ピクセルを1作図単位として出力します。

シルエットDXFでは「外形線のみ」と「外形線＋内部線」を選択できます。外形線は閉じた`LWPOLYLINE`として`SILHOUETTE`レイヤーへ、目・口・髪・服などの内部線は開いた`LWPOLYLINE`として`INTERNAL`レイヤーへ出力します。

## ライセンス

FlipCaptureはGNU General Public License v3.0で配布します。同梱のZen Kaku Gothic NewフォントはSIL Open Font License 1.1で配布され、ライセンス本文をフォントと一緒に収録しています。
