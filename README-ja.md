# iaas-sim

学習、設計検証、アーキテクチャ実験のための小規模な IaaS 制御プレーンシミュレータです。vSphere simulator をバックエンドに使用しつつ、制御プレーンの識別子、永続化、アーキテクチャ境界を明示しています。

## 現在の機能

完全に実行可能な制御プレーンは、引き続き `backend/` の Python 3.14 実装です。FastAPI/Uvicorn HTTP API、pyVmomi による `vcsim` 連携、SQLite に永続化される状態、制御プレーンが発行する UUIDv7 を備えています。実装済み Resource は `VirtualMachine`、`Snapshot`、`InstanceType`、永続的な `Operation` であり、VM power と Snapshot の非同期 command、blank VM 作成を含みます。

`VirtualMachine.power_state` は希望状態ではなく、バックエンドから観測した状態です。コマンドの受付は完了を意味しません。受け付けた非同期コマンドには `202 Accepted` を返し、完了または失敗まで永続的な `Operation` Resource で追跡します。

移行先 backend は Kotlin/JVM、Ktor、Maven を使用します。Phase K0 と K1 で実行可能 skeleton、immutable な VirtualMachine Domain model、純粋な power-command validation、型付けされた expected-failure 基盤を構築しました。Phase K2 では VirtualMachine read を追加しました。Phase K3 では非同期 START/STOP command、SQLite に永続化する Operation、terminal state を永続化する GET polling、live `vcsim` Task integration を追加しました。VirtualMachine identity mapping は引き続き一時的な process-local memory です。

## Kotlin への段階的移行

移行は big-bang rewrite ではなく段階的に進めます。Python backend を executable behavior / architecture reference として維持し、後続 Phase で vertical slice ごとに Kotlin へ移します。

- **K0（完了）:** 実行可能な Kotlin/Ktor/Maven skeleton
- **K1（完了）:** Kotlin-native Domain と expected-failure 基盤
- **K2（完了）:** VirtualMachine read vertical slice
- **K3（完了）:** VirtualMachine command / Operation vertical slice
- **K4（次）:** 次の incremental vertical slice

## アーキテクチャと expected failure

言語に依存しない project architecture は Functional Core + Imperative Shell と Hexagonal Architecture を組み合わせます。不変かつ純粋な Domain rule を Application 層が Port 経由でオーケストレーションし、infrastructure は Adapter に留め、期待される失敗を型で表現します。

現在の Python reference にある project-local な `Result`、`result_workflow`、`ResultUnwrapper` は expected-failure propagation に特化した実装手法です。汎用 FP framework でも Kotlin 移行先の要件でもありません。Kotlin では、成功と型付けされた expected failure を例外や投機的な combinator なしで表現する、独自の最小限な sealed type `Outcome<T, E>` を使用します。

## 主要技術

- 現在の制御プレーン: Python 3.14、FastAPI、Uvicorn、pyVmomi、SQLite
- 移行先 backend 基盤: Kotlin 2.4.10/JVM、Ktor 3.5.2、Maven 3.9.16、JDK 21
- Svelte、TypeScript、Vite
- `vcsim`、OpenTelemetry、Grafana/otel-lgtm を含む Docker Compose

## 2つの backend の実行

Kotlin backend の通常操作には Make を使用します。

```bash
make kotlin-run
make kotlin-test
make kotlin-verify
```

`make kotlin-run` は `vcsim` と Kotlin server を起動します。http://localhost:8080/health と http://localhost:8080/v1/virtualMachines を確認できます。health は liveness のみで、list/get response は live simulator の観測状態を読み、command endpoint は永続化した Operation とともに 202 Accepted を返し、GET Operation は request ごとに RUNNING backend Task を1回 poll します。下位レベルでは `cd backend-kotlin && ./mvnw ...` を使用でき、system Maven installation は不要です。

`make up` は引き続き現在の Python application を Docker Compose で起動します。health endpoint は http://localhost:8000/health、API documentation は http://localhost:8000/docs、UI は http://localhost:8000/ui です。停止には `make down` を使用します。

## ローカルコマンド

```bash
make kotlin-run
make kotlin-test
make kotlin-verify
make up
make down
make reset
make logs
make verify
```

## Codespaces

dev container は Python 3.14、uv、Node.js 24、Docker-in-Docker、JDK 21 を提供します。上記コマンドを使用してください。Python application 用に port 8000、Kotlin skeleton 用に port 8080 を forward します。

## 現在の制限

Python application は Docker Compose 内から `vcsim` へ接続し、K2 では host で動く Kotlin backend のため `vcsim` を host loopback のみに公開します。Kotlin は health、VirtualMachine list/get read、非同期 START/STOP submission、SQLite に永続化した Operation lookup と live VMware Task polling を実装しています。terminal Operation state は永続化されますが、VirtualMachine public identity mapping は一時的な process-local memory であり、再起動時に失われます。認証、認可、observability は未移植です。IAM、metering、queue、retry policy、より広範な cloud-domain behavior は未実装です。`make verify` は Python、Kotlin、frontend、architecture、smoke、Compose の check を実行します。
