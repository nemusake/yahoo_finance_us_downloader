# ohlc_downloader.py README

Yahoo! Finance からOHLCV（始値・高値・安値・終値・出来高）と配当・分割イベントを取得し、CSV（UTF-8 BOM付き）で出力するダウンローダーです。

- 実行ファイル: `ohlc_downloader.py`（リポジトリ直下）
- データ取得: `yfinance`
- 出力: CSV（既定はBOM付き）。未指定時は `download/<ticker>_<frequency>.csv` に保存（フォルダが無ければ自動作成）／`--stdout` で標準出力
- 日付指定: `YYYY-MM-DD` / `YYYY/MM/DD` / `YYYYMMDD`
- 頻度: `daily`/`weekly`/`monthly` → `1d`/`1wk`/`1mo`
  - 上記頻度では出力のDate列は `YYYY-MM-DD`（時刻・TZは出力しません）
  - 既定は「調整後OHLC」（配当・分割を織り込む）。`--no-adjust` で未調整に切替可能

## 前提条件
- Python 3.11 以上
- uv（依存解決・実行）

補足: uvとは？
- Python向けの高速なパッケージマネージャ兼実行ツールです（pip + venv の置き換え/補完）。
- 役割: `uv sync` で依存関係を解決・ロック、`uv run` で仮想環境を自動用意してコマンドを実行します。
- インストール例:
  - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
  - Windows (PowerShell): `irm https://astral.sh/uv/install.ps1 | iex`
  - 参考: https://docs.astral.sh/uv/


## セットアップ
```
uv sync
```

## 使い方（基本）
```
uv run python ohlc_downloader.py --ticker 7203.T --frequency daily --period 1y --output toyota.csv
```

主な引数
- `--ticker` 必須。例: `AAPL`, `7203.T`, `'^GSPC'`（記号含む場合は引用推奨）
- `--frequency` `daily` | `weekly` | `monthly`（既定: `daily`）
- `--period` 例: `1mo`, `6mo`, `1y`, `5y`, `max`（既定: `1y`）
- `--start`, `--end` 例: `2020-01-01` / `20200101`（どちらか/両方指定可）
  - `--start` または `--end` を指定すると `period` は自動的に無効化（yfinanceの仕様に合わせるため）
- `--output` 出力ファイルパス。未指定時は `download/<ticker>_<frequency>.csv` に自動保存（既存ファイルは上書き）
- `--stdout` 出力先を標準出力にする（自動保存を無効化）
- `--no-bom` BOMを付与しない
- `--no-adjust` 未調整の生OHLCを出力（既定は調整後OHLC）
- `--total-return-index` TRI列（配当再投資を仮定、基準100）を追加

## 使い方（複数ティッカー：codelist）
`--codelist` にヘッダー付きCSV（UTF-8/BOM可）を指定すると、列 `etf_ticker` に含まれる全ティッカーを取得し、各ティッカーごとに `download/<asset_class>_<category>_<ticker>_<frequency>.csv` へ出力します（codelist専用の命名規則）。

```
uv run python ohlc_downloader.py --codelist codelist.csv --frequency daily --period 5y
```

注意
- `--codelist` 使用時は `--ticker` は不要です（指定されていても無視されます）。
- 複数銘柄のため `--stdout`/`--output` は無効です。出力先は自動で `download` 配下になります。
- CSVの列名解釈は大文字小文字を区別しません（例: `ETF_Ticker` でも可）。
- 出力ファイル名の構成要素は codelist の `asset_class`（8列目）と `category`（7列目）、`etf_ticker`、`frequency` です。
  - `asset_class` または `category` が空・欠損の場合は `unknown` を補完します。
  - 同一 `etf_ticker` が複数行に現れた場合、最初に出現した分類（asset_class/category）を採用し、異なる分類が後続で見つかれば警告を表示します（出力は1ファイル）。
  - ファイル名は英数字以外を `-` にサニタイズし、連続した `-` は1つに圧縮します。

## 例
- 標準出力（BOM付き）に出力
```
uv run python ohlc_downloader.py --ticker AAPL --frequency monthly --period 5y --stdout > aapl.csv
```
- SPY 配当込みのTRI列を追加（既定＝調整後）
```
uv run python ohlc_downloader.py --ticker SPY --frequency daily --period 5y --total-return-index
```
- 未調整（配当落ちのギャップを見たい場合）
```
uv run python ohlc_downloader.py --ticker SPY --frequency daily --period 1y --no-adjust
```
- ^GSPC（指数は配当イベントを持たないためDividendsは通常0）
```
uv run python ohlc_downloader.py --ticker '^GSPC' --frequency daily --start 1999-01-01 --end 2025-09-19
```

## 振る舞いの要点（配当・分割 / 調整）
- 調整後OHLC（既定）
  - 過去価格が配当・分割でバックアジャストされるため、配当落ちのギャップは価格には現れません
  - ただし配当発生日には Dividends 列に金額が入ります
  - Closeの隣接比から累積したリターンは、配当再投資を仮定したトータルリターンに整合します
- 未調整OHLC（`--no-adjust`）
  - 配当落ち日にCloseが配当分だけギャップダウンします
  - DataFrameに Adj Close 列が出力され、これは調整系列です
- TRI列（`--total-return-index`）
  - 調整後系列を基準100でスケールした指数を追加します
  - `--no-adjust` 時は Adj Close、既定（調整後）時は Close を使用

## その他
- CSVは既定で `utf-8-sig`（BOM付き）。Excelで文字化けしにくい
- 取得カラムは yfinance 準拠（Open, High, Low, Close, Volume, Dividends, Stock Splits など）
- 分足などの期間制約はYahoo! Finance側の仕様に依存
- データ利用はYahoo!の利用規約に従ってください

詳細な各オプションの説明は「ohlc_downloader_オプションコマンド解説.md」を参照してください。
