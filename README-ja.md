# iaas-sim

学習・設計検証・アーキテクチャ検証を目的とした小規模なIaaSクラウドシミュレータです。現在の Phase 2A では、意図的に小さく保った制御プレーンに VirtualMachine の非同期電源操作を実装しています。

## 目的

- vSphere互換バックエンドを前提にした小規模クラウド制御プレーンの骨格を検証する
- mutable state と状態遷移を抑えた静的・明示的な設計を体験する
- Docker Compose で起動確認できる最小構成を提供する
- Operational Health、Swagger UI、OpenAPI、placeholder console を確認できるようにする

## 主要技術

- Python 3.14
- FastAPI
- Uvicorn
- pyVmomi
- SQLite（将来利用のために選定、現Phaseではビジネスロジックには使わない）
- Svelte + TypeScript + Vite
- Dex（将来OIDC向け）
- OpenTelemetry + Grafana/otel-lgtm
- Docker Compose

## Phase 2A: 非同期電源操作

VirtualMachine の電源操作（開始、停止）は非同期操作として実装されています：

- **観測状態**: `VirtualMachine.power_state` はバックエンド から最後に観測された状態を表します。希望状態ではありません
- **非同期実行**: `POST /v1/virtualMachines/{id}:start` は `202 Accepted` と `Location` ヘッダを返します
- **操作追跡**: 電源操作は `Operation` リソース（UUIDv7 識別子）で追跡されます
  - process-local registry が公開 ID と opaque な backend reference を対応付け、GET 時に
    backend の現在状態を poll して投影します。Phase 2A では永続化しません
- **責務の分離**：
  - ドメイン検証は純粋：観測状態に対するコマンド検証、副作用なし
  - アプリケーション層：ドメイン検証 + バックエンド送信を合成
  - opaque な backend operation reference は Adapter 内部に留め、公開 Operation ID としては公開しません
  - Operation status は immutable な `Running | Succeeded | Failed(failure)` ADT で、target は
    backend-independent な resource reference です
- **失敗セマンティクス**：
  - 同期的失敗（検証・送信失敗）: HTTP 4xx/5xx レスポンス
  - 非同期的失敗（backend operation 実行失敗）: `Operation.state = FAILED`

## Codespaces

1. GitHub Codespaces でこのリポジトリを開く
2. 次を実行する
   ```bash
   make up
   ```
3. 次のURLを開く
   - http://localhost:8000/health
   - http://localhost:8000/docs
   - http://localhost:8000/ui
   - http://localhost:3000（Grafana/otel-lgtm）
4. 停止するには
   ```bash
   make down
   ```

## ローカルコマンド

```bash
make up
make down
make reset
make logs
make verify
```

## 補足

- アプリケーションと vSphere simulator の接続は、意図された実行経路である Docker Compose network 内の `vcsim` ホスト名経由 HTTPS で検証する
- host の `127.0.0.1` アクセスは、実際のアプリケーション経路ではないため completion criteria として扱わない
- Phase 2A の対象は非同期 VM start/stop と非永続 Operation polling のみであり、IAM、metering、永続化、queue、retry、その他の cloud domain は対象外です
- CI では Type Check、lint、import rules、pytest などを必須で検証する
