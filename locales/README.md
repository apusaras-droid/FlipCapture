# FlipCapture language files

## 日本語

このフォルダの`en.json`または`ja.json`をコピーし、`fr.json`などの名前へ変更してください。`code`には一意の言語コード、`name`には言語選択欄へ表示する名称、`translations`には「日本語原文: 翻訳文」を記述します。ファイルはUTF-8 JSONで保存し、追加・編集後にFlipCaptureを再起動してください。未翻訳項目は日本語で表示されます。不正なファイルは無視され、ログへ記録されます。

## English

Copy `en.json` or `ja.json` in this folder and rename it, for example `fr.json`.

Required structure:

```json
{
  "code": "fr",
  "name": "Français",
  "translations": {
    "入力方式": "Mode de saisie",
    "監視開始": "Démarrer la surveillance"
  }
}
```

- Save the file as UTF-8 JSON.
- `code` must be unique and should normally be a BCP 47 language code.
- `name` is the label shown in the language selector.
- Translation keys are the Japanese source strings used by FlipCapture.
- Missing entries fall back to the Japanese source text instead of preventing startup.
- Invalid files are ignored and recorded in the log.
- Restart FlipCapture after adding or editing a language file.
