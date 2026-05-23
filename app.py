import streamlit as st
import yfinance as yf
import pandas as pd
import io
import re
import traceback

st.set_page_config(page_title="実質配当利回り計算", layout="centered")

st.markdown("### 💰 実質配当利回り計算")
st.caption("楽天証券の保有銘柄CSVから取得価格ベースの利回りを算出")


# ---------- CSV読み込み（診断ログ付き） ----------
def load_rakuten_csv(file_bytes):
    """楽天証券CSVを読み込む。失敗時は (None, エラーメッセージ, ヒント) を返す。"""
    # 1) エンコーディング判定
    text = None
    used_enc = None
    for enc in ['utf-8-sig', 'utf-8', 'cp932', 'shift_jis']:
        try:
            text = file_bytes.decode(enc)
            used_enc = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return None, "どのエンコーディングでも読めませんでした", None

    lines = text.splitlines()
    st.info(f"📄 読み込み成功: エンコーディング={used_enc}, 行数={len(lines)}")

    # 2) ヘッダー行探索
    header_idx = None
    for i, line in enumerate(lines):
        stripped = line.lstrip().lstrip('"')
        if stripped.startswith('銘柄コード'):
            header_idx = i
            break

    if header_idx is None:
        head_preview = "\n".join(lines[:15])
        return None, "「銘柄コード」で始まる行が見つかりません", head_preview

    st.info(f"📍 ヘッダー検出: {header_idx + 1}行目")

    # 3) ヘッダー行以降をパース（Pythonエンジンで寛容に）
    data_text = '\n'.join(lines[header_idx:])
    try:
        df = pd.read_csv(io.StringIO(data_text), engine='python', on_bad_lines='skip')
    except Exception as e:
        return None, f"pd.read_csv 失敗: {e}", data_text[:500]

    if len(df) == 0:
        return None, "データ行が0件です", None

    # 4) 銘柄コード列から4桁の数字を抽出できる行だけ残す
    #    （末尾の合計行を除外。pandasがコードをfloat化する問題にも対応）
    code_col = df.columns[0]
    extracted = df[code_col].astype(str).str.extract(r'(\d{4})', expand=False)
    mask = extracted.notna()
    df = df[mask].copy()
    df[code_col] = extracted[mask].values  # 4桁コードに正規化
    df = df.reset_index(drop=True)

    if len(df) == 0:
        return None, "4桁の銘柄コードを持つ行がありません", None

    return df, None, None


def extract_code(cell):
    if pd.isna(cell):
        return None
    m = re.search(r'(\d{4})', str(cell))
    return m.group(1) if m else None


def to_number(cell):
    if pd.isna(cell):
        return None
    s = re.sub(r'[^\d.\-]', '', str(cell))
    try:
        return float(s)
    except ValueError:
        return None


@st.cache_data(ttl=3600)
def fetch_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        div = 0.0
        for key in ['dividendRate', 'trailingAnnualDividendRate']:
            v = info.get(key)
            if v and v > 0:
                div = float(v)
                break
        if div == 0:
            divs = stock.dividends
            if len(divs) > 0:
                cutoff = pd.Timestamp.now(tz=divs.index.tz) - pd.Timedelta(days=365)
                div = float(divs[divs.index >= cutoff].sum())
        hist = stock.history(period="5d")
        price = float(hist['Close'].iloc[-1]) if len(hist) > 0 else None
        name = info.get('shortName') or info.get('longName') or ''
        return div, price, name
    except Exception:
        return 0.0, None, ''


# ---------- メイン ----------
uploaded = st.file_uploader(
    "楽天証券「保有商品一覧」CSV",
    type=['csv'],
    help="楽天証券 → 保有商品一覧 → CSV出力で取得"
)

if uploaded is not None:
    try:
        df, err, hint = load_rakuten_csv(uploaded.read())
    except Exception as e:
        st.error(f"想定外のエラー: {e}")
        st.code(traceback.format_exc())
        st.stop()

    if df is None:
        st.error(f"❌ {err}")
        if hint:
            with st.expander("ファイルの先頭部分（デバッグ用）"):
                st.code(hint)
        st.stop()

    st.success(f"✅ {len(df)}銘柄を読み込みました")

    with st.expander("CSV プレビュー（先頭5行）"):
        st.dataframe(df.head())

    st.markdown("#### カラム指定")
    cols = df.columns.tolist()

    def guess(keywords, default=0):
        for i, c in enumerate(cols):
            if any(k in c for k in keywords):
                return i
        return default

    col_code = st.selectbox("銘柄コード列", cols, index=guess(['銘柄コード']))
    col_qty = st.selectbox("保有数量列", cols, index=guess(['保有数量', '数量']))
    col_avg = st.selectbox("平均取得単価列", cols, index=guess(['平均取得価額', '平均取得', '取得単価']))

    if st.button('実質配当利回りを計算', type='primary'):
        rows = []
        progress = st.progress(0)
        status = st.empty()
        n = len(df)

        for i, row in df.iterrows():
            code = extract_code(row[col_code])
            qty = to_number(row[col_qty])
            avg = to_number(row[col_avg])

            status.text(f"取得中: {code} ({i + 1}/{n})")
            progress.progress((i + 1) / n)

            if not code or not qty or qty <= 0 or not avg or avg <= 0:
                continue

            ticker = f"{code}.T"
            div_per_share, price, name = fetch_stock_data(ticker)

            yoc = (div_per_share / avg * 100) if avg > 0 else 0
            cur_yield = (div_per_share / price * 100) if price else 0
            annual_div = div_per_share * qty
            delta = yoc - cur_yield

            rows.append({
                'コード': code,
                '銘柄': name or str(row[col_code]),
                '数量': qty,
                '取得単価': avg,
                '現在値': price,
                '1株配当': div_per_share,
                '年間配当': annual_div,
                '現在利回り%': cur_yield,
                '実質利回り%': yoc,
                'YoC-現在利回り': delta,
            })

        status.text("完了 ✅")

        if not rows:
            st.warning("有効なデータがありませんでした")
            st.stop()

        total_cost = sum(r['取得単価'] * r['数量'] for r in rows)
        total_div = sum(r['年間配当'] for r in rows)
        port_yoc = (total_div / total_cost * 100) if total_cost > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("銘柄数", len(rows))
        c2.metric("年間予想配当", f"¥{total_div:,.0f}")
        c3.metric("PF実質利回り", f"{port_yoc:.2f}%")

        result = pd.DataFrame(rows).sort_values('実質利回り%', ascending=False).reset_index(drop=True)

        st.dataframe(
            result.style.format({
                '数量': '{:,.4f}',
                '取得単価': '{:,.2f}',
                '現在値': '{:,.2f}',
                '1株配当': '{:,.2f}',
                '年間配当': '{:,.2f}',
                '現在利回り%': '{:.2f}',
                '実質利回り%': '{:.2f}',
                'YoC-現在利回り': '{:+.2f}',
            }),
            use_container_width=True,
            height=600,
        )

        st.download_button(
            "結果をCSVでダウンロード",
            result.to_csv(index=False).encode('utf-8-sig'),
            file_name="yield_on_cost.csv",
            mime="text/csv",
        )
else:
    st.info("👆 楽天証券の保有商品一覧CSVをアップロードしてください")
