#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
download配下の *_<frequency>.csv を横持ちでマージするスクリプト。

用途:
  - ohlc_downloader.py を --codelist オプションで実行して生成された
    "assetclass_category_ticker_frequency.csv" を対象に、指定列（既定: close）を
    Date列で横方向に結合する（外部結合）。

例:
  uv run python csv_merge.py --frequency monthly \
    --column close \
    --start_end 20200101-20210101 \
    --codelist codelist.csv \
    --output download/merged_monthly_close.csv

主な仕様:
  - --frequency は {daily,weekly,monthly} から選択（必須）
  - --column は {open,high,low,close,volume,dividends,stocksplits,capitalgains}（既定: close）
  - --start_end は日付範囲フィルタ。YYYYMMDD-YYYYMMDD / YYYY-MM-DD-YYYY-MM-DD / YYYY/MM/DD-YYYY/MM/DD を受理
  - --codelist 指定時は、codelistの etf_ticker 列の順序で列順を整える
  - 出力は既定で UTF-8 (BOM付き)。--no-bom 指定で BOM 無し
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Optional, Iterable

import pandas as pd


def _normalize_date_str(s: Optional[str]) -> Optional[str]:
    """柔軟な日付表現を YYYY-MM-DD に正規化する。

    対応例:
      - YYYYMMDD -> YYYY-MM-DD
      - YYYY/MM/DD -> YYYY-MM-DD
      - YYYY-MM-DD -> そのまま
    空やNoneはそのまま返す。
    """
    if not s:
        return s
    s = s.strip()
    if "/" in s:
        s = s.replace("/", "-")
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def _parse_start_end(arg: Optional[str]) -> tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    """--start_end の値を (start_ts, end_ts) に変換する。両端含む。

    受理形式:
      - 20200101-20210101
      - 2020-01-01-2021-01-01
      - 2020/01/01-2021/01/01
    """
    if not arg:
        return (None, None)
    s = str(arg).strip()
    if "-" not in s:
        raise ValueError("--start_end は '開始-終了' の形式で指定してください")
    parts = s.split("-", 1)
    if len(parts) != 2:
        raise ValueError("--start_end の解析に失敗しました")
    start_raw, end_raw = parts[0].strip(), parts[1].strip()
    start = _normalize_date_str(start_raw) if start_raw else None
    end = _normalize_date_str(end_raw) if end_raw else None
    start_ts = pd.to_datetime(start) if start else None
    end_ts = pd.to_datetime(end) if end else None
    return (start_ts, end_ts)


def _sanitize_ticker_for_filename(t: str) -> str:
    """ohlc_downloader.py と同じポリシーでティッカーをファイル名用に正規化する。
    - 英数字以外はハイフン('-')に置換
    - 連続するハイフンは1つに圧縮
    - 先頭末尾のハイフンは除去
    例: '^GSPC' -> 'GSPC', 'BRK.B' -> 'BRK-B', '7203.T' -> '7203-T'
    """
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(t))
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "data"


def _iter_target_files(input_dir: str, frequency: str) -> Iterable[str]:
    """input_dir 配下から、末尾が _<frequency>.csv のファイルパスを列挙。"""
    if not os.path.isdir(input_dir):
        return []
    suffix = f"_{frequency}.csv"
    for name in os.listdir(input_dir):
        if not name.endswith(suffix):
            continue
        full = os.path.join(input_dir, name)
        if os.path.isfile(full):
            yield full


def _extract_parts_from_filename(path: str, frequency: str) -> Optional[tuple[str, str, str, str]]:
    """ファイル名 'asset_category_ticker_frequency.csv' から
    (asset, category, ticker, stem) を抽出。失敗時は None。
    列名としては stem= 'asset_category_ticker' を用いる。
    """
    base = os.path.basename(path)
    suf = f"_{frequency}.csv"
    if not base.endswith(suf):
        return None
    stem = base[: -len(suf)]  # 'asset_category_ticker'
    # 右から2つの '_' で区切って3要素を得る（堅牢）
    try:
        asset, category, ticker = stem.rsplit("_", 2)
    except ValueError:
        return None
    return asset, category, ticker, stem


def _load_series_from_csv(path: str, column_key: str) -> Optional[pd.DataFrame]:
    """CSVからDateと選択列を読み込み、列名をそのまま（後でリネーム）で返す。

    - 読み込み時に 'utf-8-sig' とする（BOM考慮）
    - Date列をDatetimeに変換し、タイムゾーンは落とす
    - 指定列が存在しない場合は None
    """
    # 列名マップ
    colmap = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
        "dividends": "Dividends",
        "stocksplits": "Stock Splits",
        "capitalgains": "Capital Gains",
    }
    want = colmap[column_key]

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception as e:
        print(f"[WARN] CSV読み込みに失敗: {path}: {e}", file=sys.stderr)
        return None

    if "Date" not in df.columns:
        print(f"[WARN] Date列が見つかりません: {path}", file=sys.stderr)
        return None
    if want not in df.columns:
        print(f"[WARN] 指定列 '{want}' が見つかりません: {path}", file=sys.stderr)
        return None

    # Dateを正規化（時刻が付いていても日付化）
    try:
        idx = pd.to_datetime(df["Date"], errors="coerce")
        # tz-aware -> naive
        try:
            if getattr(idx, "tz", None) is not None:
                idx = idx.tz_convert(None)
        except Exception:
            pass
        df["Date"] = idx.dt.date
    except Exception:
        pass

    return df[["Date", want]].copy()


def _aggregate_by_frequency(df: pd.DataFrame, frequency: str, column_key: str) -> pd.DataFrame:
    """頻度に応じてDateを月初/週初に正規化し、列ごとに適切な集約を行う。

    ルール（monthly/weekly時のみ適用。dailyはそのまま）:
      - open: 最初の有効値（最も早い営業日）
      - high: 最大値
      - low:  最小値
      - close:最後の有効値（最も遅い営業日）
      - volume, dividends, capitalgains: 合計
      - stocksplits: 係数の積（0は非イベントとして無視）。イベント無しはNaN
    """
    if df is None or df.empty:
        return df
    d = df.copy()
    if d.shape[1] < 2:
        return d
    value_col = d.columns[1]

    # daily は日付正規化のみ
    if frequency == "daily":
        try:
            d["Date"] = pd.to_datetime(d["Date"], errors="coerce").dt.date
        except Exception:
            pass
        return d

    # アンカー（日付のバケット先頭）
    orig_dt = pd.to_datetime(d["Date"], errors="coerce")
    if frequency == "monthly":
        anchor = orig_dt.dt.to_period("M").dt.to_timestamp(how="start")
    elif frequency == "weekly":
        anchor = orig_dt.dt.to_period("W-MON").dt.to_timestamp(how="start")
    else:
        try:
            d["Date"] = pd.to_datetime(d["Date"], errors="coerce").dt.date
        except Exception:
            pass
        return d

    d["__anchor"] = anchor
    d["__orig_dt"] = orig_dt
    d = d.sort_values(by="__orig_dt")
    grp = d.groupby("__anchor", sort=True, dropna=False)

    def first_valid(g: pd.Series):
        s = g[g.notna()]
        return s.iloc[0] if len(s) else pd.NA

    def last_valid(g: pd.Series):
        s = g[g.notna()]
        return s.iloc[-1] if len(s) else pd.NA

    if column_key == "open":
        agg = grp[value_col].apply(first_valid)
    elif column_key == "close":
        agg = grp[value_col].apply(last_valid)
    elif column_key == "high":
        agg = grp[value_col].max(skipna=True)
    elif column_key == "low":
        agg = grp[value_col].min(skipna=True)
    elif column_key in ("volume", "dividends", "capitalgains"):
        agg = grp[value_col].sum(min_count=1)
    elif column_key == "stocksplits":
        series = grp[value_col].apply(lambda x: pd.to_numeric(x, errors="coerce").replace(0, pd.NA))
        # 上のapplyで階層化されるため、再計算: 各グループで積（min_count=1→全NaNならNaN）
        agg = grp.apply(lambda g: pd.to_numeric(g[value_col], errors="coerce").replace(0, pd.NA).prod(min_count=1))
    else:
        # 既定は close 相当
        agg = grp[value_col].apply(last_valid)

    out = pd.DataFrame({
        "Date": pd.to_datetime(agg.index).date,
        value_col: agg.values,
    })
    return out


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="download配下のCSVをマージ（横持ち、外部結合）")
    p.add_argument("--frequency", required=True, choices=["daily", "weekly", "monthly"], help="対象の頻度")
    p.add_argument(
        "--column",
        choices=[
            "open",
            "high",
            "low",
            "close",
            "volume",
            "dividends",
            "stocksplits",
            "capitalgains",
        ],
        default="close",
        help="マージ対象の列（既定: close）",
    )
    p.add_argument("--start_end", default=None, help="日付範囲 'YYYYMMDD-YYYYMMDD' 等（両端含む）")
    p.add_argument("--input-dir", default="download", help="入力ディレクトリ（既定: download）")
    p.add_argument("--output", default=None, help="出力CSVパス（未指定時は download/merged_<freq>_<col>.csv）")
    p.add_argument("--no-bom", action="store_true", help="BOMを付与しない（既定は付与）")
    p.add_argument("--no-ffill", action="store_true", help="マージ後の1ステップ前方補完を無効化")
    p.add_argument("--codelist", default=None, help="codelist.csv のパス（列 etf_ticker の順に整列）")
    p.add_argument("--verbose", action="store_true", help="進捗を詳しく表示")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    # 入力ファイル列挙
    files = list(_iter_target_files(args.input_dir, args.frequency))
    if not files:
        print(f"[ERROR] 対象ファイルが見つかりません（{args.input_dir} 内 *_{{{args.frequency}}}.csv）", file=sys.stderr)
        return 2

    # codelist順の構築（オプション）。順序は codelist の etf_ticker 順を採用
    ordered_tickers: list[str] | None = None
    if args.codelist:
        try:
            df_codes = pd.read_csv(args.codelist, dtype=str, encoding="utf-8-sig")
        except Exception as e:
            print(f"[ERROR] codelistの読み込みに失敗: {e}", file=sys.stderr)
            return 2
        cols = [str(c).strip().lower() for c in df_codes.columns]
        df_codes.columns = cols
        if "etf_ticker" not in df_codes.columns:
            print("[ERROR] codelistに 'etf_ticker' 列がありません", file=sys.stderr)
            return 2
        ordered_tickers = []
        for tk in df_codes["etf_ticker"].astype(str).tolist():
            t = (tk or "").strip()
            if not t or t.lower() == "nan":
                continue
            ordered_tickers.append(t)

    # start_end の解釈
    start_ts, end_ts = _parse_start_end(args.start_end)

    # マージ用のベースDataFrame（Date列を起点）
    merged: Optional[pd.DataFrame] = None

    # 対象ファイル -> 出力列名（= stem） の順序を決める
    items: list[tuple[str, str]] = []  # (path, output_colname)
    if ordered_tickers is not None:
        # codelistの順で、存在するファイルを拾う
        # まず sanitized_ticker -> (path, stem) のMapを作る
        by_sanitized: dict[str, tuple[str, str]] = {}
        for p in files:
            parts = _extract_parts_from_filename(p, args.frequency)
            if parts:
                _, _, tk_sanitized, stem = parts
                by_sanitized[tk_sanitized] = (p, stem)
        for tk in ordered_tickers:
            s = _sanitize_ticker_for_filename(tk)
            got = by_sanitized.get(s)
            if got:
                p, stem = got
                items.append((p, stem))
            else:
                print(f"[WARN] codelistのティッカーに対応するCSVが見つかりません: {tk}", file=sys.stderr)
    else:
        # ファイル一覧からアルファベット順（安定）
        tmp: list[tuple[str, str]] = []
        for p in files:
            parts = _extract_parts_from_filename(p, args.frequency)
            if parts:
                _, _, tk_sanitized, stem = parts
                tmp.append((p, tk_sanitized, stem))
        tmp.sort(key=lambda x: x[1])
        items = [(p, stem) for (p, _, stem) in tmp]

    # 列名キー
    col_key = args.column

    # 各ティッカーのシリーズを順次マージ
    for (path, out_name) in items:
        if args.verbose:
            print(f"[INFO] 読み込み: {path}", file=sys.stderr)
        df = _load_series_from_csv(path, col_key)
        if df is None or df.empty:
            print(f"[WARN] スキップ（空もしくは読込失敗）: {path}", file=sys.stderr)
            continue

        # 頻度に応じたDate正規化 + 列ごとの集約
        df = _aggregate_by_frequency(df, args.frequency, col_key)

        # 期間フィルタ（両端含む）: 正規化後のDateに対して適用
        if start_ts is not None or end_ts is not None:
            dts = pd.to_datetime(df["Date"], errors="coerce")
            mask = pd.Series(True, index=df.index)
            if start_ts is not None:
                mask &= dts >= start_ts
            if end_ts is not None:
                mask &= dts <= end_ts
            df = df.loc[mask].copy()

        # 列名をティッカーにリネーム
        value_col = df.columns[1]
        df = df.rename(columns={value_col: out_name})

        # マージ（外部結合）
        if merged is None:
            merged = df
        else:
            merged = pd.merge(merged, df, on="Date", how="outer")

    if merged is None or merged.empty:
        print("[WARN] マージ結果が空でした（対象列が存在しない/フィルタで排除された可能性）", file=sys.stderr)
        return 0

    # 日付昇順、必要なら重複除去
    try:
        merged["Date"] = pd.to_datetime(merged["Date"], errors="coerce").dt.date
    except Exception:
        pass
    merged = merged.sort_values(by=["Date"]).drop_duplicates(subset=["Date"])  # 念のため

    # 列順: Date, 指定順（列名は 'asset_category_ticker'）
    col_order = ["Date"]
    if items:
        col_order.extend([out for (_, out) in items])
        # 重複があれば一意化（理屈上は重複しない想定だが保険）
        seen = set()
        uniq = []
        for c in col_order:
            if c not in seen:
                uniq.append(c)
                seen.add(c)
        col_order = uniq
    merged = merged[[c for c in col_order if c in merged.columns]].copy()

    # 欠損補完: その銘柄の前行にデータがある場合のみ前方補完（limit=1）
    data_cols = [c for c in merged.columns if c != "Date"]
    if data_cols and not args.no_ffill:
        merged[data_cols] = merged[data_cols].ffill(limit=1)

    # 出力先
    if args.output:
        out_path = args.output
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
    else:
        out_dir = args.input_dir or "download"
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"merged_{args.frequency}_{args.column}.csv")

    enc = "utf-8" if args.no_bom else "utf-8-sig"
    merged.to_csv(out_path, index=False, encoding=enc)
    print(f"[OK] Wrote: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
