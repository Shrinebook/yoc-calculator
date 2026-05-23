# yoc-calculator
実質配当利回りを計算

# 実質配当利回り計算アプリ

楽天証券の「保有商品一覧」CSVをアップロードして、取得価格ベースの配当利回り（YoC: Yield on Cost）を算出するStreamlitアプリ。

## 計算項目

- 1株あたり年間配当（yfinance から取得）
- **実質配当利回り** = 年間配当 ÷ 平均取得単価 × 100
- 現在利回り（参考）
- YoC と 現在利回り の差分（増配・株価上昇でどれだけ育ったか）
- ポートフォリオ全体の年間予想配当・PF実質利回り

## 使い方

1. 楽天証券にログイン → 「保有商品一覧」 → CSV出力
2. アプリにCSVをアップロード
3. 銘柄コード / 保有数量 / 平均取得単価 の列を指定（自動推定あり）
4. 「実質配当利回りを計算」ボタンを押す

## ローカル実行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud でデプロイ

1. このリポジトリを GitHub にプッシュ
2. https://share.streamlit.io にログイン
3. 「New app」→ リポジトリと `app.py` を指定 → Deploy

無料枠で常時公開可能。スマホブラウザからもアクセスできる。

## 注意

- 配当データは yfinance（Yahoo Finance）から取得。`dividendRate`（予想）優先、なければ実績ベース
- 一部の銘柄は配当情報が取れないことあり（その場合は 0 表示）
- 取得結果は1時間キャッシュ
