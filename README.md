# youtubedl

YouTube の URL を `source.csv` に列挙し、CLI で MP3/MP4 化や文字起こしをまとめて行えるツールです。  
音声は `audio/`、動画は `video/`、文字起こしは `transcripts/` に出力します。

## 事前準備

1. Python 3.x と `ffmpeg` をあらかじめインストールしておく。
2. 仮想環境を作成し、依存関係を導入する。

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方

1. `source.csv` を UTF-8 で作成し、1 行につき 1 URL を記載する（ヘッダー不要）。
2. 以下のサブコマンドから用途に合わせて実行する。

### 音声ダウンロード（MP3）

```bash
python cli.py audio
```

- `source.csv` の URL ごとに **入力チェック → mp3 変換 → 出力確認** の 3 ステップで処理し、`audio/<title>.mp3` に保存します。
- ログは `[ERROR]` や `[OK]` を含む一定のフォーマットで表示され、ステージ名も確認できます。
- ライブ配信 URL もそのまま処理します（完了まで時間がかかる場合があります）。逆にスキップしたい場合は `--skip-live` を指定してください。
- すでに同名の MP3 が存在する場合はダウンロードを省略し、そのファイルを再利用します。

### 動画ダウンロード（MP4）

```bash
python cli.py video
```

- `yt-dlp` + `ffmpeg` で `video/<title>.mp4` を生成します。
- 音声版と同様に 3 ステップのログが出力されます。
- ライブ配信・アーカイブもデフォルトで処理対象です。スキップしたいときだけ `--skip-live` を利用してください。
- 既に同名 MP4 が存在する場合は再ダウンロードを行いません。

### 文字起こし（Whisper）

```bash
python cli.py transcribe
```

- 事前に `audio/` に MP3 がある前提です。
- `transcripts/<title>.txt` として UTF-8 テキストが保存され、`--quiet` で Whisper の詳細ログを抑止できます（デフォルトは進捗表示あり）。
- Whisper モデルは `--model medium` のように切り替え可能（既定は `small`）。

## カスタマイズ

- 各コマンドには `--source` や `--output`、`--audio-dir` などのオプションがあり、パスを上書きできます。
- ディレクトリが存在しない場合は自動生成し、書き込み不可の場合は即エラー終了します。
