# csv_merge.py 使用手順書

本書は、`csv_merge.py` を用いて `download` 配下の複数CSVを横方向にマージする手順を説明します。`uv` による実行を前提とします。

---

## 1. 前提条件
- 本リポジトリ直下で作業すること。
- 事前に `ohlc_downloader.py --codelist ...` を実行し、`download` 配下に `assetclass_category_ticker_frequency.csv` が存在すること。
- Python 3.11 以上、`uv` が利用可能であること。

---

## 2. 基本コマンド
```bash
uv run python csv_merge.py --frequency <daily|weekly|monthly> [その他オプション]
```

主なオプション:
- `--frequency {daily,weekly,monthly}`（必須）
- `--column {open,high,low,close,volume,dividends,stocksplits,capitalgains}`（既定: close）
- `--start_end <開始-終了>`（任意。YYYYMMDD-YYYYMMDD / YYYY-MM-DD-YYYY-MM-DD / YYYY/MM/DD-YYYY/MM/DD）
- `--input-dir <dir>`（既定: download）
- `--output <path>`（省略時: `<input-dir>/merged_<frequency>_<column>.csv`）
- `--no-bom`（BOM無しで出力）
- `--codelist <path>`（列順を etf_ticker の順に整列）
- `--verbose`（詳細ログ）

---

## 3. 代表的な利用例

### 3.1 月次・Close列・期間を 2020-01-01 〜 2021-01-01 に絞り、codelist順で出力
```bash
uv run python csv_merge.py \
  --frequency monthly \
  --column close \
  --start_end 2020-01-01-2021-01-01 \
  --codelist codelist.csv \
  --output download/merged_monthly_close.csv
```

### 3.2 週次・Volume列、BOM無し、デフォルトの出力先
```bash
uv run python csv_merge.py \
  --frequency weekly \
  --column volume \
  --no-bom
```

### 3.3 入力ディレクトリを変更してマージ
```bash
uv run python csv_merge.py \
  --frequency daily \
  --input-dir data \
  --column close
```
→ 出力先は既定で `data/merged_daily_close.csv`

---

## 4. 出力仕様
- 列構成: `Date`, `assetclass_category_ticker`, ...
  - 列名はマージ元CSVファイル名から `_<frequency>.csv` を取り除いた stem 部分を使用します。
- 並び順: `Date` 昇順。
- 列順: `--codelist` 指定時は codelist の `etf_ticker` 順。未指定時はファイル由来のティッカー（正規化名）の昇順。
- 欠損補完: 外部結合で欠けた日付は NaN。直前の日に値がある場合のみ 1 ステップ前方補完（limit=1）。
- 文字コード: 既定 UTF-8 (BOM付き)。`--no-bom` 指定でBOM無し。

### 4.1 日付の正規化
- monthly: `Date` を各月の月初（YYYY-MM-01）に正規化します。同一月内に複数行が存在する場合は「その月の中で最も遅い元日付」のレコードを採用します。
- weekly: `Date` を各週の週初（月曜）に正規化し、同一週内では「最も遅い元日付」を採用します。
- daily: 変更なし。

---

## 5. 列指定の詳細
- 指定可能なキーとCSV列名の対応
  - `open` → `Open`
  - `high` → `High`
  - `low` → `Low`
  - `close` → `Close`
  - `volume` → `Volume`
  - `dividends` → `Dividends`
  - `stocksplits` → `Stock Splits`
  - `capitalgains` → `Capital Gains`
- 指定列が存在しないCSVは警告してスキップします。

### 5.1 集約ルール（monthly/weekly 選択時）
- open: 期間内の最初の有効値（最も早い営業日）
- high: 期間内の最大値
- low: 期間内の最小値
- close: 期間内の最後の有効値（最も遅い営業日）
- volume, dividends, capitalgains: 期間内の合計
- stocksplits: 期間内の係数合成（0は非イベントとして無視）。イベント無しは空欄（NaN）

---

## 6. 日付フィルタ（--start_end）
- 受理形式（両端含む）
  - `YYYYMMDD-YYYYMMDD` 例: `20200101-20210101`
  - `YYYY-MM-DD-YYYY-MM-DD` 例: `2020-01-01-2021-01-01`
  - `YYYY/MM/DD-YYYY/MM/DD` 例: `2020/01/01-2021/01/01`
- マージ前に各CSVの `Date` をこの範囲でフィルタします。

---

## 7. よくある警告と対処
- `[WARN] 指定列 'Close' が見つかりません:`
  - そのCSVに該当列が無いか、生成時のオプションが異なる可能性。スキップされます。
- `[WARN] codelistのティッカーに対応するCSVが見つかりません:`
  - codelist にあるティッカーのCSVが `input-dir` に無い場合。ファイル名のサニタイズ（非英数字→`-`）も考慮してください。
- `[WARN] マージ結果が空でした` 
  - 列不一致・期間フィルタで全除外などが原因。オプションや入力ファイルをご確認ください。

---

## 8. トラブルシュート
- 期間フィルタで想定より行数が少ない
  - `--frequency` と入力CSVの末尾（`_<frequency>.csv`）が一致しているか確認。
- 列が想定順にならない
  - `--codelist` を渡しているか、`codelist.csv` の `etf_ticker` に不要な空白・欠損が無いか確認。
- 列名が期待と異なる
  - 列名はファイル名 stem（`assetclass_category_ticker`）です。downloader 側でのサニタイズにより、原ティッカーの記号（例 `.`）は `-` に置換されています。

---

## 9. 補足
- 出力先を省略した場合の既定: `<input-dir>/merged_<frequency>_<column>.csv`
- ディレクトリが存在しない場合は自動で作成します。
- 実行は `uv run` を推奨します。本プロジェクトでは `uv` による依存解決を前提としています。
- マージ後の1ステップ前方補完を無効化する場合は `--no-ffill` を付与してください。
