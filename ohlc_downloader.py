#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Yahoo! Finance からOHLCVの時系列データを取得し、CSV（UTF-8 BOM付き）で出力するスクリプト。

使い方例:
  uv run python ohlc_downloader.py --ticker 7203.T --frequency daily --period 1y --output toyota.csv

オプション:
  --ticker      単一ティッカー指定。例: AAPL, 7203.T
  --frequency   daily / weekly / monthly（デフォルト: daily）
  --period      例: 1mo, 6mo, 1y, 5y, max（デフォルト: 1y）
  --start       期間開始 YYYY-MM-DD（省略可）
  --end         期間終了 YYYY-MM-DD（省略可）
  --output      出力ファイルパス（未指定時は標準出力）
  --no-bom      BOMを付与しない（デフォルトはBOM付与）
  --codelist    codelist.csv を指定し、列 etf_ticker の全銘柄を一括取得（出力は各CSV）。
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional
import time

import os
import pandas as pd

import yfinance as yf


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Yahoo! Finance OHLC ダウンローダー")
    p.add_argument("--ticker", required=False, default=None, help="ティッカー（例: AAPL, 7203.T など）")
    p.add_argument(
        "--frequency",
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="足の頻度（daily=1d, weekly=1wk, monthly=1mo）",
    )
    p.add_argument("--period", default="1y", help="期間（例: 1mo, 6mo, 1y, 5y, max）")
    p.add_argument("--start", default=None, help="開始日 YYYY-MM-DD または YYYYMMDD（省略可）")
    p.add_argument("--end", default=None, help="終了日 YYYY-MM-DD または YYYYMMDD（省略可）")
    p.add_argument(
        "--output",
        default=None,
        help=(
            "出力ファイルパス（未指定時は download/<sanitized_ticker>_<frequency>.csv に保存。"
            "--stdout 指定時は標準出力）"
        ),
    )
    p.add_argument("--stdout", action="store_true", help="標準出力へ出力（--output未指定時のデフォルト保存を無効化）")
    p.add_argument("--no-bom", action="store_true", help="BOMを付与しない（デフォルトは付与）")
    p.add_argument("--no-adjust", action="store_true", help="未調整の生OHLCを出力（デフォルトは調整後OHLC）")
    p.add_argument("--total-return-index", dest="total_return_index", action="store_true", help="TRI（配当再投資を仮定、基準100）列を追加")
    p.add_argument("--codelist", default=None, help="codelist.csv のパス。列 etf_ticker の全銘柄を一括取得")
    p.add_argument("--sleep", type=float, default=2.0, help="codelist時、各銘柄取得の間にスリープする秒数（既定: 2.0秒。0で無効）")
    return p.parse_args(argv)


def _normalize_date(s: Optional[str]) -> Optional[str]:
    """日付文字列をyfinanceが解釈しやすい形式(YYYY-MM-DD)に正規化する。

    - YYYYMMDD -> YYYY-MM-DD に変換
    - YYYY/MM/DD -> YYYY-MM-DD に変換
    - それ以外はそのまま返す（不正ならyfinance側で例外）
    """
    if not s:
        return s
    s = s.strip()
    if "/" in s:
        s = s.replace("/", "-")
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    # バリデーション（--codelist 指定時は --ticker 不要。未指定時は --ticker 必須）
    if not args.codelist and not args.ticker:
        print("[ERROR] --ticker もしくは --codelist のいずれかを指定してください", file=sys.stderr)
        return 2

    freq_map = {
        "daily": "1d",
        "weekly": "1wk",
        "monthly": "1mo",
    }
    interval = freq_map[args.frequency]

    # start/endを正規化し、併用時のperiodはNoneにする
    start = _normalize_date(args.start)
    end = _normalize_date(args.end)
    period = None if (start or end) else args.period

    def _sanitize_filename_from_ticker(t: str) -> str:
        """ティッカーから安全なファイル名を生成する。
        - 英数字以外はハイフンに置換
        - 連続するハイフンを1つに圧縮
        - 先頭/末尾のハイフンを削除
        例: '^GSPC' -> 'GSPC', 'BRK.B' -> 'BRK-B', '7203.T' -> '7203-T'
        """
        import re
        s = re.sub(r"[^A-Za-z0-9]+", "-", t)
        s = re.sub(r"-+", "-", s).strip('-')
        return s or "data"

    def fetch_and_write_one(ticker: str, asset_class: Optional[str] = None, category: Optional[str] = None) -> int:
        """単一ティッカーを取得して出力する。成功:0 / 失敗:>0 を返す

        codelist使用時に限り、出力ファイル名に asset_class/category を含める。
        欠損時は 'unknown' を補完する。
        """
        try:
            print(f"[INFO] Fetching: {ticker}", file=sys.stderr)
            t = yf.Ticker(ticker)
            df = t.history(
                period=period,
                interval=interval,
                start=start,
                end=end,
                auto_adjust=(not args.no_adjust),
                actions=True,
                timeout=10,
            )
        except Exception as e:
            print(f"[ERROR] データ取得に失敗しました ({ticker}): {e}", file=sys.stderr)
            return 1

        # 日次/週次/月次はインデックスをYYYY-MM-DDへ正規化（時刻・タイムゾーンを除去）
        if args.frequency in ("daily", "weekly", "monthly") and df is not None and not df.empty:
            try:
                idx = pd.to_datetime(df.index)
                # タイムゾーン情報を落として日付に変換
                if getattr(idx, 'tz', None) is not None:
                    idx = idx.tz_convert(None)
                df.index = idx.date
                df.index.name = "Date"
            except Exception:
                pass

        # TRI（Total Return Index）列の追加（基準=100）
        if df is not None and not df.empty and args.total_return_index:
            try:
                # 調整後価格系列を取得
                if args.no_adjust:
                    # 未調整取得時は 'Adj Close' を優先的に利用（無い場合はClose）
                    adj = df.get('Adj Close', df.get('Close'))
                else:
                    # 調整後取得時は 'Close' が実質Adj Closeと等価
                    adj = df.get('Close')
                if adj is not None and len(adj) > 0:
                    tri = (adj / adj.iloc[0]) * 100.0
                    df['TRI'] = tri
            except Exception:
                # TRI計算はベストエフォート。失敗時は黙ってスキップ
                pass

        # 出力（CSV, デフォルトでBOM付き）
        # --codelist 指定時は --stdout / --output は無効化する
        if args.codelist:
            out_dir = "download"
            try:
                os.makedirs(out_dir, exist_ok=True)
            except Exception:
                pass
            # codelist使用時はファイル名: assetclass_category_ticker_frequency.csv
            # 値が欠ける場合は 'unknown' を補完
            ac_val = (asset_class or "").strip() or "unknown"
            cg_val = (category or "").strip() or "unknown"
            output_path = os.path.join(
                out_dir,
                f"{_sanitize_filename_from_ticker(ac_val)}_{_sanitize_filename_from_ticker(cg_val)}_{_sanitize_filename_from_ticker(ticker)}_{args.frequency}.csv",
            )
            if df is None:
                print(f"[WARN] 空のDataFrameを受け取りました ({ticker})", file=sys.stderr)
                # 空でもヘッダだけ出力
                pd.DataFrame().to_csv(output_path, encoding=("utf-8" if args.no_bom else "utf-8-sig"))
                print(f"[OK] Wrote: {output_path}", file=sys.stderr)
                return 0
            else:
                df.to_csv(output_path, encoding=("utf-8" if args.no_bom else "utf-8-sig"))
                print(f"[OK] Wrote: {output_path}", file=sys.stderr)
                return 0
        else:
            # 既存の単体出力仕様
            if df is None or df.empty:
                print("[WARN] 取得データが空でした", file=sys.stderr)
                # 空でもヘッダだけ出力
                if args.stdout:
                    if not args.no_bom:
                        sys.stdout.write("\ufeff")
                    (df if df is not None else pd.DataFrame()).to_csv(sys.stdout)
                else:
                    if args.output:
                        output_path = args.output
                        out_dir = os.path.dirname(output_path)
                        if out_dir:
                            os.makedirs(out_dir, exist_ok=True)
                    else:
                        out_dir = "download"
                        os.makedirs(out_dir, exist_ok=True)
                        # 既定のファイル名はティッカー_頻度.csv（例: AAPL_daily.csv）
                        output_path = os.path.join(
                            out_dir,
                            f"{_sanitize_filename_from_ticker(args.ticker)}_{args.frequency}.csv",
                        )
                    (df if df is not None else pd.DataFrame()).to_csv(output_path, encoding=("utf-8" if args.no_bom else "utf-8-sig"))
                return 0

            # 非空の通常出力
            if args.stdout:
                if not args.no_bom:
                    sys.stdout.write("\ufeff")
                df.to_csv(sys.stdout)
            else:
                if args.output:
                    output_path = args.output
                    out_dir = os.path.dirname(output_path)
                    if out_dir:
                        os.makedirs(out_dir, exist_ok=True)
                else:
                    out_dir = "download"
                    os.makedirs(out_dir, exist_ok=True)
                    # 既定のファイル名はティッカー_頻度.csv（例: AAPL_daily.csv）
                    output_path = os.path.join(
                        out_dir,
                        f"{_sanitize_filename_from_ticker(args.ticker)}_{args.frequency}.csv",
                    )
                df.to_csv(output_path, encoding=("utf-8" if args.no_bom else "utf-8-sig"))
            return 0

    # マルチ or 単一の分岐
    if args.codelist:
        # --stdout / --output が指定されていたら無効化を通知
        if args.stdout:
            print("[WARN] --codelist 指定時は --stdout は無効です（個別ファイルに出力します）", file=sys.stderr)
        if args.output:
            print("[WARN] --codelist 指定時は --output は無効です（個別ファイルに出力します）", file=sys.stderr)

        # CSVを読み込み、列 etf_ticker / category / asset_class を抽出
        try:
            df_codes = pd.read_csv(args.codelist, dtype=str, encoding="utf-8-sig")
        except Exception as e:
            print(f"[ERROR] codelistの読み込みに失敗しました: {e}", file=sys.stderr)
            return 2
        cols = [str(c).strip().lower() for c in df_codes.columns]
        df_codes.columns = cols
        if "etf_ticker" not in df_codes.columns:
            print("[ERROR] codelistに 'etf_ticker' 列が見つかりません", file=sys.stderr)
            return 2
        # 行順を維持しつつ、同一ティッカーは最初の分類を採用（以降で異なる分類が来たら警告）
        mapping: dict[str, tuple[Optional[str], Optional[str]]] = {}
        order: list[str] = []
        for _, row in df_codes.iterrows():
            tk = str(row.get("etf_ticker", "") or "").strip()
            if not tk or tk.lower() == "nan":
                continue
            cat = row.get("category")
            ac = row.get("asset_class")
            # 値はそのままの大文字小文字を保持
            cat_s = None if (cat is None or str(cat).strip().lower() == "nan" or str(cat).strip() == "") else str(cat)
            ac_s = None if (ac is None or str(ac).strip().lower() == "nan" or str(ac).strip() == "") else str(ac)
            if tk not in mapping:
                mapping[tk] = (ac_s, cat_s)
                order.append(tk)
            else:
                prev_ac, prev_cat = mapping[tk]
                # 異なる分類が来た場合に警告（最初のものを採用）
                if (ac_s is not None and prev_ac is not None and str(ac_s) != str(prev_ac)) or (
                    cat_s is not None and prev_cat is not None and str(cat_s) != str(prev_cat)
                ):
                    print(
                        f"[WARN] 同一ティッカーに異なる分類を検出: {tk} (既存: asset_class={prev_ac}, category={prev_cat}; 新: asset_class={ac_s}, category={cat_s}) — 最初の分類を採用します",
                        file=sys.stderr,
                    )

        if not order:
            print("[WARN] codelistの 'etf_ticker' に有効なティッカーが見つかりませんでした", file=sys.stderr)
            return 0

        total = len(order)
        errs = 0
        for i, tk in enumerate(order):
            ac_s, cat_s = mapping[tk]
            rc = fetch_and_write_one(tk, ac_s, cat_s)
            if rc != 0:
                errs += 1
            # 次のリクエストまでスリープ（最後の1件後は任意だが、体感速度のため省略）
            if i < len(order) - 1 and (args.sleep or 0) > 0:
                try:
                    time.sleep(float(args.sleep))
                except Exception:
                    pass
        print(f"[INFO] 完了 {total - errs}/{total} 件", file=sys.stderr)
        return 0 if errs == 0 else 1
    else:
        # 単一ティッカー
        if args.ticker is None:
            print("[ERROR] --ticker を指定してください", file=sys.stderr)
            return 2
        return fetch_and_write_one(args.ticker)


if __name__ == "__main__":
    raise SystemExit(main())
