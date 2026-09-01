# iaas-sim

学習・設計検証・アーキテクチャ検証を目的とした小規模なIaaSクラウドシミュレータです。Phase 1では本番向けクラウド機能を実装せず、最小の骨格と起動確認を重視します。

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
- **責務の分離**：
  - ドメイン検証は純粋：観測状態に対するコマンド検証、副作用なし
  - アプリケーション層：ドメイン検証 + バックエンド送信を合成
  - バックエンド Task MOR（vSphere）は Adapter 内部。公開 Operation ID としては公開されません
- **失敗セマンティクス**：
  - 同期的失敗（検証・送信失敗）: HTTP 4xx/5xx レスポンス
  - 非同期的失敗（タスク実行失敗）: `Operation.state = FAILED`

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

- Phase 1では、アプリケーションと vSphere simulator の接続経路を Docker Compose network 内の `vcsim` ホスト名経由 HTTPS として検証する
- host の `127.0.0.1` アクセスは、実際のアプリケーション経路ではないため completion criteria として扱わない
- Phase 1では IAM、VM lifecycle、metering、full cloud domain の実装は行わない
- Phase 1は architecture skeleton、インフラ起動、静的検証を中心に行う
- CI では Type Check、lint、import rules、pytest などを必須で検証する
