import streamlit as st
import yfinance as yf
import pandas as pd
import io
import re

st.set_page_config(page_title="実質配当利回り計算", layout="centered")

st.markdown("### 💰 実質配当利回り計算")
st.caption("楽天証券の保有銘柄CSVから取得価格ベースの利回りを算出")


# ---------- ヘルパー関数 ----------
def load_csv(file_bytes):
    """エンコーディングを自動判定してCSV読み込み"""
    for enc in ['cp932', 'utf-8-sig', 'utf-8']:
        try:
            return pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    return None


def extract_code(cell):
    """文字列から4桁の銘柄コードを抽出"""
    if pd.isna(cell):
        return None
    m = re.search(r'(\d{4})', str(cell))
    return m.group(1) if m else None


def to_number(cell):
    """カンマや通貨記号を除去して数値化"""
    if pd.isna(cell):
        return None
    s = re.sub(r'[^\d.\-]', '', str(cell))
    try:
        return float(s)
    except ValueError:
        return None


@st.cache_data(ttl=3600)
def fetch_stock_data(ticker):
    """年間配当(1株)・現在値・銘柄名を取得"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # 年間配当の優先順位: 予想 → 実績 → 過去12ヶ月合計
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

        # 現在値
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
    help="楽天証券にログイン → 保有商品一覧 → CSV出力で取得"
)

if uploaded is not None:
    df = load_csv(uploaded.read())
    if df is None:
        st.error("CSVの読み込みに失敗しました")
        st.stop()

    with st.expander("CSV プレビュー"):
        st.dataframe(df.head())

    st.markdown("#### カラム指定")
    cols = df.columns.tolist()

    def guess(keywords, default=0):
        for i, c in enumerate(cols):
            if any(k in c for k in keywords):
                return i
        return default

    col_code = st.selectbox("銘柄コード列", cols, index=guess(['コード', '銘柄']))
    col_qty = st.selectbox("保有数量列", cols, index=guess(['数量', '株数']))
    col_avg = st.selectbox("平均取得単価列", cols, index=guess(['平均取得', '取得価', '取得単価']))

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

            if not code or not qty or not avg:
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
                '数量': int(qty),
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

        # サマリ
        total_cost = sum(r['取得単価'] * r['数量'] for r in rows)
        total_div = sum(r['年間配当'] for r in rows)
        port_yoc = (total_div / total_cost * 100) if total_cost > 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("銘柄数", len(rows))
        c2.metric("年間予想配当", f"¥{total_div:,.0f}")
        c3.metric("PF実質利回り", f"{port_yoc:.2f}%")

        # ソート可能テーブル
        result = pd.DataFrame(rows).sort_values('実質利回り%', ascending=False).reset_index(drop=True)

        st.dataframe(
            result.style.format({
                '取得単価': '{:,.1f}',
                '現在値': '{:,.1f}',
                '1株配当': '{:,.2f}',
                '年間配当': '{:,.0f}',
                '現在利回り%': '{:.2f}',
                '実質利回り%': '{:.2f}',
                'YoC-現在利回り': '{:+.2f}',
            }),
            use_container_width=True,
            height=600,
        )

        # CSV ダウンロード
        st.download_button(
            "結果をCSVでダウンロード",
            result.to_csv(index=False).encode('utf-8-sig'),
            file_name="yield_on_cost.csv",
            mime="text/csv",
        )
else:
    st.info("👆 楽天証券の保有商品一覧CSVをアップロードしてください")
