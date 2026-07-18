# FlipCapture GitHub公開・配布手順書

## 1. 目的

本書は、FlipCaptureをGitHubで安全かつ再現可能な形で公開するための技術手順をまとめたものです。対象範囲は次のとおりです。

- Gitリポジトリの準備と秘密情報の除外
- GPL-3.0ライセンスの明示
- AI支援開発であることの開示
- 使用プログラム、ライブラリ、AIモデル、素材への謝辞
- 英語・日本語READMEの整備
- 配布先PCで依存関係を導入する`setup.bat`の準備
- 個人設定を含まない配布用ZIPの作成と検査
- Pull Request、GitHub Release、配布ZIPの公開
- 公開後の検証と更新時の注意事項

本書は法律上の助言ではありません。第三者コンポーネントの配布方法を変更する場合、各ライセンスの原文と最新情報を改めて確認してください。

## 2. 公開物の構成

GitHubの`main`ブランチには、少なくとも次のファイルを含めます。

```text
FlipCapture/
├─ LICENSE
├─ README.md
├─ README.ja.md
├─ ACKNOWLEDGEMENTS.md
├─ requirements.txt
├─ setup.bat
├─ start_flipcapture.bat
├─ flipcapture/
├─ assets/
├─ locales/
├─ tests/
└─ docs/
```

公開リポジトリと配布ZIPでは役割が異なります。

- リポジトリ：ソース、テスト、仕様・技術文書、履歴を公開する。
- 配布ZIP：利用者がセットアップして実行するために必要なファイルだけを収録する。
- GitHub Release：バージョン、変更内容、ZIP、チェックサムを固定して公開する。

## 3. GitHub CLIと認証

GitHub CLIをインストールし、対象リポジトリへpushできるアカウントで認証します。

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh auth status
gh auth setup-git
```

複数アカウントが登録されている場合は、明示的に切り替えます。

```powershell
gh auth switch -h github.com -u apusaras-droid
gh api repos/apusaras-droid/FlipCapture --jq '.permissions'
```

`push: true`であることを確認します。認証トークン、ワンタイムコード、資格情報はREADME、ログ、スクリーンショット、コミットへ記録しません。

## 4. 公開してはいけないファイル

`.gitignore`では、少なくとも次を除外します。

```gitignore
.venv/
__pycache__/
*.py[cod]
.pytest_cache/

config/settings.json*
logs/
dist/
```

主な理由は次のとおりです。

- `.venv`：PC固有で巨大な仮想環境。別PCでの再利用に適さない。
- `config/settings.json*`：保存フォルダ、ウィンドウ情報などの個人設定を含む。
- `logs`：ローカルパス、エラー内容、操作履歴を含む可能性がある。
- `dist`：GitHub Releaseで管理する生成物。ソース履歴へ重複登録しない。
- キャッシュ：実行時生成物であり、配布には不要。

コミット前に必ず確認します。

```powershell
git status --short --ignored
git diff --cached --stat
git diff --cached --check
```

秘密情報と個人パスの簡易検査例です。

```powershell
rg -n -i "gh[opsu]_[A-Za-z0-9_]+|api[_-]?key|password|C:\\Users\\|H:/" `
  -g '!.git/**' -g '!.venv/**' -g '!logs/**' -g '!config/**' -g '!dist/**' .
```

この検査だけですべての秘密情報を発見できるわけではありません。`git diff --cached`を人間が確認する工程を省略しないでください。

## 5. GPL-3.0の明示

FlipCapture本体はGNU General Public License v3.0（GPL-3.0）で公開します。

必要な対応は次のとおりです。

1. リポジトリ直下にGPL v3の全文を収録した`LICENSE`を置く。
2. 英語・日本語READMEの冒頭とライセンス節にGPL-3.0であることを書く。
3. GitHub Releaseの説明にもGPL-3.0を明記する。
4. 配布ZIPへ`LICENSE`を収録する。
5. 第三者コンポーネントのライセンスがGPLへ置き換わるわけではないことを書く。

READMEでの表記例です。

```markdown
> **License:** FlipCapture is free software distributed under the
> **GNU General Public License v3.0 (GPL-3.0)**. See [LICENSE](LICENSE).
```

GPLの適用範囲、著作権者名、`GPL-3.0-only`または`GPL-3.0-or-later`の選択を将来さらに厳密化する場合は、README、ソースヘッダー、Release、SPDX表記の内容を一致させます。

## 6. AI支援開発の開示

FlipCaptureでは、OpenAI ChatGPT/Codexを含むAIとの対話によるコーディング支援を利用しました。READMEと謝辞には、AIだけが自律的に公開したと誤解されないよう、次の責任分担を記載します。

- 人間が要件と機能を決めた。
- 人間が動作を評価し、修正を指示した。
- AIがコードと文書の作成を支援した。
- 公開前にテストとレビューを行った。
- 最終的な公開判断はプロジェクト所有者が行った。

英語・日本語の具体的な文言は`README.md`、`README.ja.md`、`ACKNOWLEDGEMENTS.md`を基準にします。

AI支援の明記は、正確性や安全性を保証する表示ではありません。既知の制約、障害、依存環境についても通常のソフトウェアと同様に文書化します。

## 7. 使用技術への謝辞

`ACKNOWLEDGEMENTS.md`では、少なくとも次のプロジェクトと、その開発者・研究者・メンテナーへ謝意を示します。

- Python、Tk/Tkinter
- Pillow
- NumPy、SciPy、scikit-image
- MSS、pystray
- rembg、ONNX Runtime、PyMatting
- U²-Net、IS-Netの研究者・モデル管理者
- VTracer、ezdxf
- PyWinRT、Microsoft Windows Runtime OCR
- Requests
- FFmpeg
- Zen Kaku Gothic New
- Git、GitHub

謝辞はライセンス表示の代替ではありません。各コンポーネントの著作権とライセンスは、それぞれの作者・配布元に帰属します。

## 8. 依存ライブラリのライセンス確認

### 8.1 直接依存関係

`requirements.txt`に記載した直接依存を確認します。

```powershell
Get-Content requirements.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pip list
```

Pythonパッケージのメタデータを確認する例です。

```powershell
@'
from importlib.metadata import metadata

packages = [
    "Pillow", "numpy", "scipy", "scikit-image", "mss", "pystray",
    "rembg", "onnxruntime", "pymatting", "vtracer", "ezdxf",
    "requests", "winrt-runtime",
]

for package in packages:
    info = metadata(package)
    license_name = info.get("License-Expression") or info.get("License") or "not declared"
    print(package, info.get("Version"), license_name, sep=" | ")
'@ | .\.venv\Scripts\python.exe -
```

パッケージメタデータの`License`欄は、空欄、長文、古い情報の場合があります。最終確認では必ず次も参照します。

- 公式リポジトリの`LICENSE`、`COPYING`、`NOTICE`
- 公式ドキュメントまたはPyPIのプロジェクト情報
- 配布するバージョンに含まれるライセンスファイル
- バイナリwheelが追加で同梱するライブラリのライセンス
- 推移的依存関係

### 8.2 AIモデル

rembg本体のライセンスと、ダウンロードされるU²-Net・IS-Netモデルの利用条件は別に確認します。モデルをZIPへ直接同梱する場合は、モデルのライセンス、論文・作者の表示要件、再配布条件を確認してから行います。

FlipCapture 1.0.0のソースZIPにはAIモデルを同梱せず、初回利用時に取得する設計です。

### 8.3 FFmpeg

FFmpegはユーザー環境の`PATH`または`tools`フォルダから検出するオプション機能です。FFmpegバイナリをZIPへ同梱する場合は、そのビルド構成がLGPL/GPLのどちらに該当するか、外部コーデックを含むかを確認し、対応するライセンス・ソース入手方法を提示します。

FlipCapture 1.0.0のソースZIPにはFFmpegバイナリを同梱していません。

### 8.4 フォント

同梱するZen Kaku Gothic NewはSIL Open Font License 1.1です。配布ZIPにはフォント本体と次のライセンス文を一緒に収録します。

```text
assets/fonts/OFL-ZenKakuGothicNew.txt
```

## 9. 英語・日本語README

GitHubが最初に表示する`README.md`を英語版、`README.ja.md`を日本語版とし、両方の先頭に相互リンクを設けます。

```markdown
[English](README.md) | [日本語](README.ja.md)
```

両READMEで内容が食い違わないよう、次の項目は同時に更新します。

- 対応OSとPythonバージョン
- セットアップ方法
- ホットキー
- OCR・AI処理とプライバシー
- FFmpegの扱い
- AI支援開発の表示
- 謝辞へのリンク
- GPL-3.0表記
- Releasesページへのリンク

## 10. `setup.bat`の役割

ソースZIPにはPython仮想環境やインストール済みライブラリを含めません。受取側PCで`setup.bat`を実行し、再現可能な環境を構築します。

FlipCaptureの`setup.bat`は次を行います。

1. 64bit版Python 3.11～3.13を検出する。
2. `.venv`が正常なら再利用し、なければ作成する。
3. pipを更新する。
4. `requirements.txt`からライブラリをインストールする。
5. `pip check`で依存整合性を確認する。
6. `flipcapture.diagnostics`で主要モジュールを実際にimportする。
7. Windows日本語OCR言語とFFmpegを確認する。
8. pipログと診断ログを`logs`へ保存する。
9. 完了後にGUIを起動するか選べるようにする。

自動検証では次を使用できます。

```powershell
cmd /d /c setup.bat --no-launch
cmd /d /c setup.bat --no-launch --skip-install
```

セットアップ失敗時は、画面にエラー分類とログの場所を表示します。依存導入をサイレントに失敗させないことが重要です。

## 11. 公開前テスト

最低限、次を実行します。

```powershell
.\.venv\Scripts\python.exe -m compileall -q flipcapture tests
python -m pytest -q
.\.venv\Scripts\python.exe -m pip check
cmd /d /c setup.bat --no-launch --skip-install
```

さらに、クリーンなWindows Sandbox、仮想マシン、または別PCで次を確認します。

- Python未導入時の案内
- 初回セットアップ
- 日本語言語パックがない場合のOCR案内
- FFmpegがない場合にMP4だけが無効になること
- 100%・150%など混在DPIでの範囲選択
- 一般権限と管理者権限
- タスクトレイからの復帰・終了
- AIモデルの初回取得、タイムアウト、キャンセル

## 12. 配布用ZIPの作成

### 12.1 収録対象

配布ZIPには、実行とライセンス確認に必要なファイルを明示的に指定します。

```powershell
$version = "1.0.0"
New-Item -ItemType Directory -Path dist -Force | Out-Null

tar.exe -a -c `
  -f "dist\FlipCapture-$version-source.zip" `
  --exclude="*/__pycache__/*" `
  --exclude="*.pyc" `
  LICENSE README.md README.ja.md ACKNOWLEDGEMENTS.md `
  requirements.txt setup.bat start_flipcapture.bat `
  flipcapture assets locales docs
```

明示的な一覧を使用すると、`.git`、個人設定、ログ、仮想環境、テストキャッシュを誤って含める危険を減らせます。

### 12.2 ZIP内容検査

```powershell
tar.exe -tf "dist\FlipCapture-$version-source.zip"
```

少なくとも次を確認します。

- `LICENSE`がある。
- 英語・日本語READMEがある。
- `ACKNOWLEDGEMENTS.md`がある。
- フォントとOFLライセンスがある。
- `setup.bat`と`requirements.txt`がある。
- `.git`、`.venv`、`config`、`logs`、`__pycache__`、`dist`がない。
- ユーザー名、ローカル保存先、トークン、APIキーがない。

### 12.3 SHA-256

```powershell
Get-FileHash -Algorithm SHA256 `
  "dist\FlipCapture-$version-source.zip"
```

SHA-256はRelease本文に記載し、アップロード後にGitHub上のasset digestとも照合します。

## 13. Gitブランチ・PR・マージ

公開変更は作業ブランチで行います。

```powershell
git switch main
git pull --ff-only origin main
git switch -c agent/release-1.0.0

git add -- <公開対象ファイル>
git diff --cached --stat
git diff --cached --check
git commit -m "Publish FlipCapture 1.0.0"
git push -u origin agent/release-1.0.0
```

Pull Requestを作成します。

```powershell
gh pr create `
  --repo apusaras-droid/FlipCapture `
  --base main `
  --head agent/release-1.0.0 `
  --title "Publish FlipCapture 1.0.0" `
  --body-file pr-body.md
```

PR本文には、変更内容、理由、ユーザー影響、検証結果を記載します。マージ前に`mergeable`とCI結果を確認します。

```powershell
gh pr view <PR番号> --json mergeable,mergeStateStatus,statusCheckRollup
gh pr merge <PR番号> --merge
```

## 14. GitHub ReleaseとZIPの公開

PRを`main`へマージした後、マージコミットを対象にReleaseを作成します。

```powershell
gh release create v1.0.0 `
  "dist\FlipCapture-1.0.0-source.zip#FlipCapture 1.0.0 source ZIP" `
  --repo apusaras-droid/FlipCapture `
  --target main `
  --title "FlipCapture 1.0.0" `
  --notes-file release-notes.md
```

Release本文には次を含めます。

- 主要機能と変更点
- 英語・日本語のインストール手順
- AI支援開発の表示
- 開発者・研究者への謝辞
- GPL-3.0と第三者ライセンスの扱い
- ZIPのSHA-256

公開後はasset情報を確認します。

```powershell
gh release view v1.0.0 `
  --repo apusaras-droid/FlipCapture `
  --json url,isDraft,tagName,targetCommitish,assets
```

`isDraft`が`false`、タグが正しく、ZIP名・サイズ・digestが一致していることを確認します。

公開済みReleaseのZIPを同じバージョン名のまま差し替えると、以前取得したファイルとチェックサムが一致しなくなります。正式公開後の変更は原則としてバージョンを上げ、例として`v1.0.1`を作成します。

## 15. 公開後の確認

GitHubへログインしていない状態、またはプライベートブラウズで確認します。

- リポジトリのトップに英語READMEが表示される。
- 日本語READMEへ移動できる。
- `LICENSE`と`ACKNOWLEDGEMENTS.md`を開ける。
- Release一覧に対象バージョンが表示される。
- 配布ZIPを取得できる。
- ZIPのSHA-256がRelease本文と一致する。
- ZIPを展開し、`setup.bat`を実行できる。

確認先：

- Repository: <https://github.com/apusaras-droid/FlipCapture>
- Releases: <https://github.com/apusaras-droid/FlipCapture/releases>

GitHubやCDNのキャッシュで古い画面が表示される場合は、数分待つか`Ctrl + F5`で再読込します。APIとraw URLによる確認も併用します。

## 16. FlipCapture 1.0.0公開記録

初回公開時の記録です。

| 項目 | 値 |
|---|---|
| Repository | `apusaras-droid/FlipCapture` |
| Default branch | `main` |
| Release | `v1.0.0` |
| Asset | `FlipCapture-1.0.0-source.zip` |
| Asset size | `2,974,359 bytes` |
| SHA-256 | `DF3BC0C2C65D86FD78A64CD4A5C03DCADAEDD23CCC440C5CEE48797DAFAED1A5` |
| License | `GPL-3.0` |
| README | English / 日本語 |
| Test result | `17 passed` |

## 17. 更新版公開チェックリスト

- [ ] バージョン番号を決めた。
- [ ] `main`を最新化して作業ブランチを作った。
- [ ] 個人設定、ログ、トークン、ローカルパスがない。
- [ ] READMEの英語版と日本語版を同時更新した。
- [ ] AI支援開発の表示と謝辞を確認した。
- [ ] GPL-3.0の`LICENSE`とREADME表記を確認した。
- [ ] 直接依存・推移的依存・モデル・フォント・FFmpegのライセンスを確認した。
- [ ] `requirements.txt`と`setup.bat`を検証した。
- [ ] テスト、compileall、pip check、診断が成功した。
- [ ] クリーンな配布ZIPを作った。
- [ ] ZIP内容に不要物や秘密情報がない。
- [ ] SHA-256を取得した。
- [ ] PRをレビューして`main`へマージした。
- [ ] マージコミットを対象にGitHub Releaseを作った。
- [ ] ZIP、Release本文、checksumを公開した。
- [ ] 未ログイン状態でリポジトリとZIPを確認した。
