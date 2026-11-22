# Pickup Assistant

商品を検索し、選んだ支払方法で**注文確認画面まで**自動で進めるツール。お気に入りに入れた商品が購入可能になったら、1分ごとの監視と毎晩21時（JST）の確認で検知し、自動購入の結果を通知する。

- `backend/`: FastAPI（Python）。API・監視ユースケース・ワーカー
- `frontend/`: React + Vite + TypeScript（nginx で配信）
- `compose.yaml`: ローカル起動用（`dynamodb` / `backend` / `worker` / `frontend`）

## ローカルで起動する

### 必要なもの
- Docker（Docker Compose v2）

Node や Python をローカルに入れる必要はない（ビルドも Docker の中で行う）。

### 1. 設定ファイル `.env` を作る

```bash
cp .env.example .env
```

`.env` の `CREDENTIALS_KEY` に、サイトのパスワードを暗号化する鍵を設定する（**必須**）。鍵は次のどちらかで作る。

```bash
openssl rand -base64 32 | tr '+/' '-_'
# または
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

> `.env` はコミットしない（`.gitignore` 済み）。鍵を失くしたり変えたりすると、保存済みのアカウントは復号できなくなる（アカウントを再登録すれば復旧できる）。

### 2. 起動する

```bash
docker compose up --build
```

初回はイメージのビルドに数分かかる。バックグラウンドで動かすときは `-d` を付ける。

起動したら、ブラウザで **http://127.0.0.1:8080** を開く（このPCからのみアクセスできる）。

### 3. 使い方

1. 「商品を探す」タブの **アカウント** カードで、サイトのメールアドレスとパスワードを入れて追加する（ログインできることを確認して、暗号化して保存する）。
2. **オプション** カードで、実行モード・支払方法・検索方式を選ぶ。
3. 商品を **コード**（商品 ID。`815572` や `product/815572`）または **部分一致** で探し、「この商品を選ぶ」。
4. **ご注文内容** カードの「確認画面まで進める」を押す。サイトが混雑しているときは、自動で再試行し、複数のセッションで通過を試みる。
5. ☆ を押すとお気に入りに登録される。購入可能になると自動で注文確定まで進む（同意の表示あり）。結果は「自動購入」タブに通知される。

### 4. 止める・初期化する

```bash
docker compose down        # 停止（保存したアカウント・お気に入りは残る）
docker compose down -v     # 停止して、保存したデータ（DynamoDB のボリューム）も消す
```

鍵（`CREDENTIALS_KEY`）を変えたときは、`down -v` でデータを消してから起動する。

### ログを見る

```bash
docker compose logs -f backend
docker compose logs -f worker     # 1分ごとの監視・21時の確認
```

## 設定（環境変数。`.env` で上書きする）

| 名前 | 既定 | 内容 |
|---|---|---|
| `CREDENTIALS_KEY` | なし（必須） | サイトのパスワードを暗号化する鍵 |
| `ALLOW_ORDER_SUBMIT` | `false` | `true` のときだけ、注文確定と自動購入を許可する |
| `PREVIEW_PARALLELISM` | `3`（上限5） | 確認画面まで進めるときの同時セッション数 |
| `PREVIEW_DEADLINE_SECONDS` | `60`（上限120） | 確認画面までの制限時間（秒） |
| `TICK_DEADLINE_SECONDS` | `20` | 1分ごとの監視で購入するときの制限時間（秒） |

## 注意

- **注文確定は既定で無効**（`ALLOW_ORDER_SUBMIT=false`）。有効にすると、自動購入が実際に「購入する」を送る。取り消しにくい操作なので、内容を理解したうえで有効にする。
- サイトは、注文確定のボタンに reCAPTCHA を使っている。このツールは reCAPTCHA を回避しないため、**注文確定は現状では受理されない**見込み（結果は「受理されず」と通知される）。確認画面までは進める。
- サイトのパスワードは、サーバー側で暗号化して保存する。**このアプリには認証が無い**ため、公開しない（画面は `127.0.0.1` のみで待ち受ける）。
- 自動アクセスは、サイトの利用規約と負荷に配慮して使う。同時セッションと再試行には上限がある。

## 開発

テストは実サイトにアクセスしない（記録済みの HTML を使う）。

```bash
# backend
cd backend
uv run ruff format . && uv run ruff check . && uv run mypy . && uv run pytest

# DynamoDB Local でもリポジトリの契約テストを実行する（localhost を使う。127.0.0.1 は不可）
docker run -d --name ddb-test -p 8001:8000 amazon/dynamodb-local -jar DynamoDBLocal.jar -inMemory
DYNAMODB_ENDPOINT=http://localhost:8001 uv run pytest
docker rm -f ddb-test

# frontend（Biome・型・テストを Docker で実行）
docker build --target check ./frontend
```

- 構成のルールと作業の進め方は `CLAUDE.md`、設計書は `docs/design/`（`.gitignore` で git の対象外）を参照。
- `backend` の構成は、オニオン（`domain` / `application` / `infrastructure` / `presentation`）。
