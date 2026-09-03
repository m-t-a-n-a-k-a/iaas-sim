# iaas-sim

学習、設計検証、アーキテクチャ実験のための小規模な IaaS 制御プレーンシミュレータです。vSphere simulator をバックエンドに使用しつつ、制御プレーンの識別子、永続化、アーキテクチャ境界を明示しています。

## 現在の機能

- FastAPI と Uvicorn で提供する Python 3.14 制御プレーン
- pyVmomi による `vcsim` バックエンド連携
- SQLite に永続化される制御プレーン状態と、制御プレーンが発行する UUIDv7 識別子
- `VirtualMachine`、`Snapshot`、`InstanceType`、永続的な `Operation` Resource
- VirtualMachine の非同期 START / STOP と Snapshot の非同期作成 / 削除
- `POST /v1/virtualMachines` による blank VM 作成。CREATE Operation は事前に割り当てられた将来の VirtualMachine UUIDv7 を対象とし、バックエンド識別子との mapping が確定してから VM を公開
- OpenTelemetry と Grafana/otel-lgtm を含む Docker Compose 開発環境

`VirtualMachine.power_state` は希望状態ではなく、バックエンドから観測した状態です。コマンドの受付は完了を意味しません。受け付けた非同期コマンドには `202 Accepted` を返し、完了または失敗まで永続的な `Operation` Resource で追跡します。

## アーキテクチャと Result workflow

Functional Core + Imperative Shell と Hexagonal Architecture を組み合わせています。不変かつ純粋な Domain rule を Application 層が Port 経由でオーケストレーションし、infrastructure は Adapter に留めます。期待される失敗は strict Python typing のもとで typed `Result` として扱います。

複数段階の失敗しうる Application 処理では、小さな project-local Result workflow helper を利用できます。`result_workflow` は外部境界を typed `Result` のまま保ち、`ResultUnwrapper` は途中値の具体的な型を維持しながら `Err` を short-circuit させるため、処理を上から下へ直接読めます。これは汎用 FP framework ではなく、Result propagation に特化した小さな control-flow utility です。

## 主要技術

- Python 3.14、FastAPI、Uvicorn、pyVmomi、SQLite
- Svelte、TypeScript、Vite
- `vcsim` を含む Docker Compose
- OpenTelemetry、Grafana/otel-lgtm

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
4. 次のコマンドで環境を停止する
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

## 現在の制限

意図されたアプリケーション経路は Docker Compose network 内で `vcsim` に HTTPS 接続するものであり、host 側の `127.0.0.1` は付随的な port-publishing 経路にすぎません。IAM、metering、queue、retry policy、より広範な cloud-domain behavior は未実装です。strict typing、test、lint、architecture import rule は `make verify` で検証します。
