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
- 実装後の二次レビューは `/second-review [比較元ref]`。
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

## テスト

- red → green → refactor。テストを先に書き、失敗を確認してから実装する。
- コミットする場合は「テスト追加」と「実装」を分けると red 先行を確認しやすい。
- テストは実サイトにアクセスしない。記録済みレスポンスやフィクスチャを使う。時刻・乱数は固定する。
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

- フロントのフォーマット・Lint は Biome に統一する。ESLint / Prettier は追加しない。
- `biome check --write --unsafe` は使わない（挙動が変わる修正を含むため）。

## 注意

- 基盤（ドメインモデル、DB スキーマ、共通ユーティリティ、依存関係、Dockerfile / compose、CI）を変更するときは、設計書に理由と影響範囲を書く。
- 秘密情報（API キー、パスワード、`.env`）をコミットしない。
