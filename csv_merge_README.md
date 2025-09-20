# csv_merge.py 概要

`csv_merge.py` は、`ohlc_downloader.py --codelist` が生成する `download` 配下の CSV（`assetclass_category_ticker_frequency.csv`）を横方向（ワイド形式）にマージするユーティリティです。マージ軸は `Date` 列で、結合は外部結合（outer）です。

## 目的
- 同一頻度（daily/weekly/monthly）で書き出された複数の銘柄の系列を、ひとつのワイドCSVにまとめる。
- 列は銘柄ごとに1列。列名はファイル名の stem（`assetclass_category_ticker`）。
- 列の値は `--column` で指定（既定: `close`）。
- 指定期間でのフィルタ（`--start_end`）に対応。
- `--codelist` を渡すと、列順を `etf_ticker` の順に整える。

## 主な特徴
- 対象抽出: `download/*_<frequency>.csv` のみ。
- 列名: `assetclass_category_ticker`（ファイル名から `_<frequency>.csv` を除いた部分）。
- 列の候補: `open, high, low, close, volume, dividends, stocksplits, capitalgains`。
- 日付フィルタ: `YYYYMMDD-YYYYMMDD` / `YYYY-MM-DD-YYYY-MM-DD` / `YYYY/MM/DD-YYYY/MM/DD`（両端含む）。
- 欠損補完: 前日データが存在する場合に限り 1 ステップのみ前方補完（limit=1）。`--no-ffill` で無効化可。
- 文字コード: 既定 UTF-8 (BOM付き)、`--no-bom` でBOM無し。

## 依存関係と実行前提
- Python 3.11 以上
- ランタイムは `uv` を推奨（本プロジェクト方針）
- ライブラリ: `pandas`（`uv` が `pyproject.toml` と `uv.lock` を元に解決）

## クイックスタート
```bash
# 月次・Close列・期間指定・codelist順でマージ
uv run python csv_merge.py \
  --frequency monthly \
  --column close \
  --start_end 2020-01-01-2021-01-01 \
  --codelist codelist.csv \
  --output download/merged_monthly_close.csv
```

## オプション一覧
- `--frequency {daily,weekly,monthly}`（必須）
  - 抽出するファイル名の末尾 `_frequency.csv` と一致するもののみ対象。
- `--column {open,high,low,close,volume,dividends,stocksplits,capitalgains}`（既定: `close`）
  - CSV列名の対応: stocksplits → `Stock Splits`、capitalgains → `Capital Gains`、他は先頭大文字（例 close → `Close`）。
- `--start_end <開始-終了>`（任意）
  - 例: `20200101-20210101` / `2020-01-01-2021-01-01` / `2020/01/01-2021/01/01`。両端含む。
- `--input-dir <dir>`（既定: `download`）
  - 対象 CSV を探すベースディレクトリ。
- `--output <path>`（任意）
  - 省略時は `<input-dir>/merged_<frequency>_<column>.csv`。
- `--no-bom`
  - 出力CSVのBOMを付与しない。
- `--codelist <path>`（任意）
  - `etf_ticker` 列の順序で列順を整える。ファイル名との照合は、ティッカーを「英数字以外を `-` に置換」した正規化名で行う。
- `--verbose`
  - 進捗やスキップ理由を詳細表示。

## 入力ファイル仕様
- 生成元: `ohlc_downloader.py --codelist ...`
- ファイル名形式: `assetclass_category_ticker_frequency.csv`
  - 例: `Equity_US_SPY_monthly.csv`（実際は downloader 側のサニタイズで空白・記号は `-` に置換）
- 必須列: `Date` と指定の値列（例: `Close`）

## マージ結果の仕様
- 列: `Date`, `assetclass_category_ticker` ...
- 並び: `Date` 昇順。`--codelist` 指定時は列順を `etf_ticker` の順に整列。
- 欠損: 外部結合により無い日は NaN。直前に値がある場合のみ 1 ステップ前方補完。

### 日付の正規化と列ごとの集約
- monthly: 各行の `Date` を月初（YYYY-MM-01）に正規化し、列ごとに以下のルールで集約します。
- weekly: 各行の `Date` を週初（月曜）に正規化し、同様に集約します。
- daily: 変更なし（そのままの暦日）。

集約ルール（monthly/weekly 時）
- open: 期間内の最初の有効値（最も早い営業日）
- high: 期間内の最大値
- low: 期間内の最小値
- close: 期間内の最後の有効値（最も遅い営業日）
- volume, dividends, capitalgains: 期間内の合計
- stocksplits: 期間内の係数合成（0は非イベントとして無視）。イベントが無ければ空欄（NaN）

## 既知の注意点
- 列が存在しないファイルは警告してスキップします。
- `--codelist` に存在しても、対応するCSVが無ければ警告してスキップします。
- downloader 側のサニタイズ（非英数字 → `-`、連続 `-` 圧縮）により、ファイル名の `ticker` は原ティッカーと若干異なる場合があります。

---

必要に応じて CLI エントリポイント（例: `uv run csv-merge ...`）の追加も可能です。ご希望があればお知らせください。
