# KASF 2.0 Evolution — Rev0.9.19 Three-Worker Architecture

## 概要

Rev0.9.19はRev0.9.18を基準に、生成処理のWorker構成を3系統へ再編したリリースです。KASF v1の保存形式とReader v1.2の読み取り・合成経路は維持し、エンコーダー内部の既存VP/QR/Reader評価アルゴリズムや探索回数は原則変更していません。

## Worker構成

- **Worker A**：Stereo時は右チャンネル専用エンコーダー。Mono長区間時は前半区間のエンコーダー。
- **Worker B**：Stereo時は左チャンネル専用エンコーダー。Mono長区間時は後半区間のエンコーダー。
- **Worker C**：Rev0.9.18の共通解析Worker Bを継承。STN、Attack検出・分類、Matrix Pencil、NOMP-GVP、Dual-Window解析、DPSS/SST、Haar/Wavelet等の共通解析を実行し、得られた解析結果をA/Bへ配布。
- **Main Thread**：入力準備、Worker起動・再利用、進捗集約、チャンネル順序復元、Mono分割境界の位相接続、KASFヘッダーと本文の組み立てを担当。

A/Bはそれぞれ独立したエンコーダーWorkerとして起動し、各Worker内でWASMを初期化します。SharedArrayBufferは必須にせず、Worker間の結果受け渡しはMain Threadのメッセージ経由です。

## チャンネル別ルーティング

### Stereo (2ch)

- Aが入力チャンネル1（右）を担当。
- Bが入力チャンネル0（左）を担当。
- Cは従来どおり入力全体から共通解析用の特徴量を作成。
- 単一チャンネル形式で得られたA/Bの本文を、出力時に元の[左, 右]順へ復元。

左右の成分配列を振幅順位だけで対応付けて同一オフセットを適用する方式を避け、チャンネルごとに独立してVP候補を評価します。これは探索の意味を変更するため、Rev0.9.18とのビット同一出力を保証する変更ではありません。

### Mono (1ch)

- 長い親チャンク（1.5秒以上、かつ8フレーム以上）は、出力フレーム境界で前半/後半に分割。
- Aが前半、Bが後半を担当。
- 各サブレンジには350msの解析ガード領域を付与し、境界付近の解析コンテキストを確保。
- PCMサブレンジは親チャンクから切り出し、入力デコードやリサンプリングを重複実行しない。
- ガード領域に対応する重複出力フレームはトリムし、各出力フレームを一度だけ保持。
- A末尾の追跡位相を使ってB先頭のトラックを接続し、その後に本文を連結。
- 短いMonoチャンクはAのみで処理し、不要なBの起動を避ける。

### 3ch以上

現段階では、既存の全チャンネル対応経路を維持し、Aがまとめて処理します。Cの共通解析は設定に応じて従来どおり動作します。サラウンドチャンネルを無理に左右二群へ分けると、現行VPのチャンネル間前提を再検証する必要があるため、今回は安全側に倒しています。

## 互換性と変更範囲

- KASF v1の32-byteヘッダー、既存のフレーム/チャンネル本文、48-bit成分表現を変更しません。
- Reader v1.2の合成コードを変更していません。
- VP候補生成、QR計算式、Loss、探索回数、量子化の仕様は本リリースでは変更していません。
- 最終的な既存Reader基準の評価・採否経路を維持します。
- 新しい差分Reader評価、VP基底生成キャッシュ、新しいMulti-start初期値戦略、KASE候補評価キャッシュはまだ実装していません。

## 既知の制約

- Workerを3つにしたこと自体による実機での速度向上は未計測です。チャンネル並列化の利点はCPUコア数、WASM初期化、メモリ帯域、Workerメッセージ転送の影響を受けます。
- Stereoは左右独立VPになるため、Rev0.9.18と出力ビット同一ではありません。聴感・スペクトル品質の優劣も未評価です。
- Mono分割は長い区間でのみ行い、短区間は従来同様Aだけで処理します。
- 3ch以上は本リリースではチャンネル並列化していません。
- ChromiumでBlob Workerを使った合成WAVのE2E確認は実施済みですが、実ファイルを直接開くfile://環境、Chromebook、実音源での聴感比較は未確認です。

## ファイル

- `KASF-2.0-Evolution-Rev0.9.19-Three-Worker.html`：単体実行用HTML（Worker/WASMコードを内包）
- `tests/test-three-worker-merge.cjs`：本文トリム・連結・チャンネル順序のテスト
- `tests/test-three-worker-edgecases.cjs`：Mono分割、サンプルレート変換、フレーム時間、5ch順序復元、位相接続のテスト
- `src/`、`build/`、`tools/`：Rev0.9.18から継承したWASM関連ソースと検証資材
- `KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html`：既存回帰テスト用の直前ベースライン
- `comparison/`：過去リビジョン比較用HTML

テスト実行例：

```bash
node tests/test-three-worker-merge.cjs KASF-2.0-Evolution-Rev0.9.19-Three-Worker.html
node tests/test-three-worker-edgecases.cjs KASF-2.0-Evolution-Rev0.9.19-Three-Worker.html
node tests/test-html-script-syntax.cjs KASF-2.0-Evolution-Rev0.9.19-Three-Worker.html
```
