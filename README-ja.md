# iaas-sim

学習・設計検証・アーキテクチャ検証を目的とした小規模な IaaS 制御プレーンシミュレータです。意図的に小さく保った vSphere ベースの構成で、VirtualMachine、Snapshot、InstanceType、永続的な Operation リソースを提供します。

## 目的

- vSphere 互換バックエンドを前提にした小規模クラウド制御プレーンの骨格を検証する
- 明示的で決定的、かつ認知負荷の低い設計を保つ
- Docker Compose で意図したアーキテクチャを確認できるローカル環境を提供する
- Operational Health、Swagger UI、OpenAPI、placeholder console を確認できるようにする

## 主要技術

- Python 3.14
- FastAPI と Uvicorn
- pyVmomi と vcsim バックエンド
- SQLite による制御プレーン状態の永続化
- Svelte + TypeScript + Vite
- Dex（将来の OIDC 連携向け）
- OpenTelemetry + Grafana/otel-lgtm
- Docker Compose

## 現在の機能

- VirtualMachine と Snapshot に制御プレーン UUIDv7 ID を付与し、opaque なバックエンド ID へ対応付け
- 制御プレーンが所有する InstanceType リソース
- リソースの ID 対応と永続的な Operation リソースを SQLite に保存
- Operation で追跡する非同期の VirtualMachine `START`/`STOP` と Snapshot 作成・削除
- `POST /v1/virtualMachines` による blank VM 作成。非同期 CREATE Operation の成功後に VM を利用可能にする

`VirtualMachine.power_state` は希望状態ではなく、バックエンドから観測した状態です。コマンドの受理と完了は区別します。同期的な検証・送信失敗は HTTP エラーとなり、受理されたコマンドは `202 Accepted` を返した後、永続的な Operation に成功または非同期失敗が記録されます。

## アーキテクチャと Result workflow

本プロジェクトの基本設計は Functional Core + Imperative Shell と Hexagonal Architecture であり、strict な Python typing を適用します。ドメインのルールとデータは pure かつ immutable に保ち、Application 層は Port を介して処理をオーケストレーションし、インフラストラクチャは Adapter に分離します。期待される失敗は typed Result で表現します。

Expression はコードベース全体を純粋関数型にするためではなく、実務上の可読性と型付き Result を両立するためのライブラリとして採用します。Result 処理の実装移行は次の変更で行い、複数の失敗しうる処理では effect builder を使うことで、Result の short-circuit semantics を保ちながら、手動の unwrap を繰り返さない上から下へ読みやすい direct-style の workflow を目指します。

## Codespaces

1. GitHub Codespaces でこのリポジトリを開く
2. 次を実行する
   ```bash
   make up
   ```
3. 次の URL を開く
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

## 現在の制約

- アプリケーションと vcsim の接続は、意図された実行経路である Docker Compose network 内の `vcsim` ホスト名経由 HTTPS で検証する
- host 側の `127.0.0.1` アクセスは付随的なローカル port publishing であり、アプリケーション経路の completion criterion とはしない
- IAM、metering、queue、retry policy、その他の広範な cloud domain は対象外
- CI では strict な Python typing と architecture import rules を検証する
