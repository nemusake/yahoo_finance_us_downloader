# ohlc_downloader オプション/コマンド解説

本書は `ohlc_downloader.py` の各オプションの意味と、動作上の注意点を詳しく説明します。

## 実行コマンドの基本形
```
uv run python ohlc_downloader.py --ticker <シンボル> --frequency <daily|weekly|monthly> [期間指定] [出力指定] [調整/指数オプション]
uv run python ohlc_downloader.py --codelist <CSVパス> --frequency <daily|weekly|monthly> [期間指定] [調整/指数オプション]
```

## 主要オプション
- `--ticker`（必須）
  - 例: `AAPL`, `7203.T`, `'^GSPC'`
  - 記号（`^` など）を含む場合は引用を推奨。WindowsのCMDでは `^^GSPC` のようにエスケープが必要な場合があります

- `--frequency`
  - `daily` → `1d`
  - `weekly` → `1wk`
  - `monthly` → `1mo`
  - 日/週/月足では出力のDate列は `YYYY-MM-DD` に正規化（時刻・TZは出力しません）

- 期間指定（`--period` / `--start` / `--end`）
  - `--period`: `1mo`, `6mo`, `1y`, `5y`, `max` など
  - `--start`, `--end`: `YYYY-MM-DD` / `YYYY/MM/DD` / `YYYYMMDD`
  - `--start` または `--end` を指定すると `--period` は自動無効化（yfinance仕様）
  - endは「排他的（exclusive）」です。日足で `--end 2025-01-01` は実質 2024-12-31 まで

- 出力指定
  - `--output <path>`: 出力ファイルパスを指定
  - `--stdout`: 標準出力へ出力（`--output` 未指定時の `download/<ticker>_<frequency>.csv` 自動保存を無効化）
  - `--no-bom`: BOMを付与しない（既定はBOM付き = `utf-8-sig`）
  - 出力ファイルの既定（`--output` 未指定・`--stdout` なし）
    - `download/<ticker>_<frequency>.csv` を自動保存。`download` フォルダが無ければ作成、既存ファイルは上書き
    - ファイル名はサニタイズし、英数字以外は `-` に置換
    - 例: `^GSPC` → `download/GSPC.csv`, `BRK.B` → `download/BRK-B.csv`, `7203.T` → `download/7203-T.csv`

- 複数ティッカー取得（`--codelist`）
  - `--codelist <CSVパス>`: ヘッダー付きCSV（UTF-8/BOM可）を読み込み、列 `etf_ticker` にある全銘柄を一括取得
  - `--codelist` 併用時は `--stdout`/`--output` は無効。各銘柄を `download/<ticker>_<frequency>.csv` に保存
  - 列名の大文字小文字は無視（例: `ETF_Ticker` でも可）

- 調整/指数オプション
  - `--no-adjust`: 未調整の生OHLCを出力（既定は調整後OHLC）
    - 未調整では配当落ち日に価格のギャップが見えます
    - この場合、`Adj Close` 列（調整系列）も出力されます
  - `--total-return-index`: TRI（配当再投資を仮定、基準100）列を追加
    - 既定（調整後OHLC）では Close を使用、`--no-adjust` 時は Adj Close を使用

## 配当・分割と価格の関係（重要）
- 調整後OHLC（既定）
  - 過去価格が配当・分割でバックアジャストされ、配当落ちのギャップは価格に現れにくくなります
  - Dividends列には配当発生日の金額が入ります
  - 調整後Closeの隣接比から累積したリターンは、配当再投資を仮定したトータルリターンに整合します

- 未調整OHLC（`--no-adjust`）
  - 配当落ち日にCloseが配当分だけギャップダウンします
  - 調整系列は `Adj Close` 列に出力されます

- 参考: 指数の例
  - `^GSPC` は価格リターン指数（配当除く）であり、指数自体に配当イベントはありません（Dividends=0が通常）
  - 配当込み指数を見たい場合はトータルリターン指数（例: `^SP500TR`）を参照してください

## 使用例
- SPY の日足・過去5年（配当あり、TRI列追加）
```
uv run python ohlc_downloader.py --ticker SPY --frequency daily --period 5y --total-return-index
```

- 1557.T（東証S&P500連動JDR）日足・過去3年、未調整で出力（配当落ちのギャップ確認）
```
uv run python ohlc_downloader.py --ticker 1557.T --frequency daily --period 3y --no-adjust
```

- ^GSPC の1999年〜2025年（Dividendsは通常0）
```
uv run python ohlc_downloader.py --ticker '^GSPC' --frequency daily --start 19990101 --end 20250919
```

## 注意事項
- CSVは既定で `utf-8-sig`（BOM付き）。Excelでの互換性を考慮
- 分足などには期間制約あり（Yahoo! Finance側の制限）
- ネットワークやレート制限により取得に失敗する場合は時間をおいて再試行
- 取得データの利用はYahoo!の利用規約に従ってください
