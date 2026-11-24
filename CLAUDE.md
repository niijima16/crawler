# crawler

クロールの研究、自動テスト、CI/CD の方式検討を行うプロジェクト。
構成: `backend/`（Python）、`frontend/`。ローカルは Docker Compose で動かす。

## 行動原則（必ず守る）

[andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) を元にしたルール。

1. **考えてから書く** — 前提を明示する。不明点は推測せず質問する。解釈が複数あれば並べて選んでもらう。もっと単純な方法があれば提案する。
2. **シンプル第一** — 要求を満たす最小のコードにする。頼まれていない機能・設定項目・汎用化は入れない。一度しか使わないものは抽象化しない。起こり得ないケースのエラー処理は書かない。
3. **外科的な変更** — 必要な箇所だけ触る。隣接コードの「ついで改善」、壊れていないもののリファクタ、既存スタイルの変更はしない。自分の変更で不要になった import や関数は消し、既存のデッドコードは指摘だけして残す。
4. **ゴール駆動** — 作業を検証できるゴール（テスト）に変え、通るまで繰り返す。

判定基準: 変更したすべての行が要求に直接たどれること。

## 作業の進め方

- コード実装は `/lean-implement` で進める（規模判定 → 設計 → 人の承認 → モック承認 → プランモード → TDD 実装 → セルフレビュー）。typo など自明な修正は直接行ってよい。
- `/lean-implement` は最後に `/second-review` を自動で呼び、Blocker / Major の修正と再レビューを **最大3回** まで繰り返す。上限に達した、同じ指摘が続く、指摘が減らない、要議論、のいずれかで止まって人に報告する。
- 役割分担: `/second-review` は指摘を返すだけでコードを変更しない（/simplify の観点も指摘として返す）。修正は `/lean-implement` が行う。
- 単独で二次レビューだけ行うときは `/second-review [比較元ref]`。
- **`/lean-implement` で実装したときは、実装 → セルフレビューと修正 → 二次レビュー（/simplify 観点を含む、最大3回）まで終わるまで完了報告をしない。** 会話が長くなって手順を見失った場合は、`.claude/skills/lean-implement/SKILL.md` の Step 8〜10 を読み直して実行する。
- 設計書: `docs/design/YYYYMMDD-<slug>.md`（テンプレート: `.claude/skills/lean-implement/templates/design.md`）
- モック: `docs/design/<slug>/mock/`（本番コードに混ぜない）
- 人の承認が必要な場面では、「承認」と明確に返ってくるまで次に進まない。

## アーキテクチャ（backend: オニオン）

依存は外側から内側への一方向のみ。

| レイヤー | 置くもの | 依存してよい先 |
|---|---|---|
| domain | エンティティ・値オブジェクト・ドメインサービス（URL正規化、robots 遵守、レート制限などのクロール方針） | 標準ライブラリ、pydantic v2 |
| application | ユースケース、ポート（Protocol/ABC）の定義 | domain |
| infrastructure | HTTP クライアント、HTML パーサー、DB/ストレージ、ブラウザ自動化（ポートの実装） | application, domain |
| presentation | API ルーター（FastAPI）、スケジューラのエントリポイント | application, domain |

- domain に外部ライブラリ（ORM、HTTP クライアント、Web フレームワーク等）を import しない。例外は pydantic v2（値オブジェクトの `BaseModel`。dataclass は使わない）。
- ビジネスルールを infrastructure / presentation に書かない。
- レイヤー境界のポートは実装が1つでもよい。レイヤー内部の単一実装の抽象は作らない。

パッケージのルートは `backend/spider/`（`domain/` `application/` `infrastructure/` `presentation/`）、テストは `backend/test/`。FastAPI アプリの組み立て（infrastructure の注入）は `backend/spider/main.py` だけで行う（`uv run uvicorn spider.main:app`）。
API はすべて `/api` 配下（`GET /api/healthz` がヘルスチェック）。フロントは `frontend/`（React + Vite + TypeScript、`src/components/` のカード式 UI）で、通信は同一オリジンの `/api`。

## 起動（Docker Compose）

- `docker compose up --build` で `dynamodb`（DynamoDB Local。データは名前付きボリューム）、`backend`（FastAPI）、`worker`（1分ごとの監視と毎晩21時〔JST〕の確認。同じイメージで `python -m spider.worker`）、`frontend`（nginx。`/api/` を backend へ中継）が起動する。画面は `http://127.0.0.1:8080`（ローカルのみで公開）。
- `CREDENTIALS_KEY`（サイトのパスワードを暗号化する鍵）は、ローカルでは空でよい（空なら `CREDENTIALS_KEY_FILE` に自動生成して、ボリュームに保存する。ローカル専用）。AWS などでは必ず環境変数（や KMS）で指定する。`.env` はコミットしない。DB を初期化するときは `docker compose down -v`（指定した鍵を変えたら必須。古い鍵で暗号化したアカウントは復号できなくなる）。
- 設定は環境変数のみ: `PREVIEW_PARALLELISM`（既定3・上限5）、`PREVIEW_DEADLINE_SECONDS`（既定60・上限120）、`TICK_DEADLINE_SECONDS`（既定20）、`ALLOW_ORDER_SUBMIT`（既定 `false`。注文確定と自動購入を許可するときだけ `true`）、`DYNAMODB_ENDPOINT` / `AWS_REGION` / `TABLE_PREFIX`。
- ストレージ（アカウント・お気に入り・通知・設定）は、ポート（`application/ports.py`）の背後にある DynamoDB 実装（`infrastructure/dynamodb_repos.py`）。書き込みは、ユーザー操作と状態遷移のときだけ（監視の1回ごとの読み取りでは書かない）。購入は `watching → purchasing` の条件付き書き込みに成功した実行だけが行う（二重購入の防止）。AWS では、`check_tick` / `nightly_check` を EventBridge Scheduler → Lambda から呼ぶ想定（ワーカーはその代わり）。
- ローカルに Node は無い前提。フロントのツールは Docker で実行する（下記）。

## テスト

- red → green → refactor。テストを先に書き、失敗を確認してから実装する。
- コミットする場合は「テスト追加」と「実装」を分けると red 先行を確認しやすい。
- テストは実サイトにアクセスしない。記録済みレスポンスやフィクスチャを使う。時刻・乱数は固定する。
- リポジトリの契約テストは、`DYNAMODB_ENDPOINT` を設定すると DynamoDB Local でも実行される（例: `docker run -d -p 8001:8000 amazon/dynamodb-local -jar DynamoDBLocal.jar -inMemory` → `DYNAMODB_ENDPOINT=http://localhost:8001 uv run pytest`。`127.0.0.1` ではなく `localhost` を使う）。設定しなければメモリ上のフェイクだけで実行される。
- モックはレイヤー境界（ポート）だけに使う。

## チェックコマンド

`uv.lock` があれば先頭に `uv run` を付ける。完了報告の前にすべて通すこと。

```bash
# backend
ruff format .
ruff check .
mypy .
pytest

# frontend（frontend/ で実行）
npx biome check --write .   # フォーマット・Lint・import 整列（安全な修正のみ適用）
npx biome ci .              # 書き換えなしで最終確認（CI と同じ判定）
npm run typecheck           # package.json にある場合（Biome は型チェックをしない）
npm test                    # package.json にある場合
```

- フロントのチェックは Docker で実行する（`docker build --target check ./frontend` が Biome・型・テストをまとめて実行）。個別に実行するときは `docker run --rm -v "$PWD/frontend":/app -w /app node:22-alpine npx biome ci .` のようにする。
- フロントのフォーマット・Lint は Biome に統一する。ESLint / Prettier は追加しない。
- `biome check --write --unsafe` は使わない（挙動が変わる修正を含むため）。

## 注意

- 基盤（ドメインモデル、DB スキーマ、共通ユーティリティ、依存関係、Dockerfile / compose、CI）を変更するときは、設計書に理由と影響範囲を書く。
- 秘密情報（API キー、パスワード、`.env`）をコミットしない。
- 実サイトでの注文確定（「購入する」）の検証は、ユーザーの個別の明示的な許可がない限り行わない。
- パスワード・氏名・住所・メール・Cookie をフィクスチャ・ログ・ドキュメントに残さない。
