# KASF v3.0 — Rev.0.2.2

## 概要

本パッケージの製品バージョンは **KASF v3.0 Rev.0.2.2** です。Rev.0.9.20系の3 Worker構成・時間方向ガードを基盤とし、KASE-2.1 / JARSのハードニングおよびJARS協調候補処理を含む開発ビルドです。Rev.0.9.x表記は過去機能の導入履歴を示し、現行製品バージョンではありません。KASF v1の保存形式とReader v1.2の読み取り・合成経路は維持し、エンコーダー内部の既存VP/QR/Reader評価アルゴリズムや探索回数は原則変更していません。

## バージョンと保存ファイル

- 製品バージョン：`KASF v3.0 Rev.0.2.2`
- 保存ファイル名タグ：`v3-R0-2-2`
- KASF出力・KCPチェックポイント・JSONレポート等のダウンロード名に上記タグを付与します。
- KASFの内部保存形式は引き続き **KASF v1**、Readerは **Reader v1.2** です。これは製品バージョンとは別の互換性識別子であり、変更していません。
- KCPの内部形式識別子 `KASF-KCP-1` も維持し、旧KCPの読み込み互換性を保ちます。新規チェックポイントのメタデータには製品バージョンと保存タグを追加します。
- OPFSの既存ディレクトリ名 `KASF_Rev099` は、過去の中断データを引き続き参照できるよう変更していません。

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

- `KASF-v3.0-Rev0.2.2.html`：Rev0.9.20単体実行用HTML（Worker/WASMコードを内包）
- `KASF-2.0-Evolution-Rev0.9.19-Three-Worker.html`：直前リビジョン比較用HTML
- `tests/test-three-worker-merge.cjs`：本文トリム・連結・チャンネル順序のテスト
- `tests/test-three-worker-edgecases.cjs`：Mono分割、サンプルレート変換、フレーム時間、5ch順序復元、位相接続のテスト
- `src/`、`build/`、`tools/`：Rev0.9.18から継承したWASM関連ソースと検証資材
- `KASF-2.0-Evolution-Rev0.9.18-Short-Approx-Resynthesis.html`：既存回帰テスト用の直前ベースライン
- `comparison/`：過去リビジョン比較用HTML

テスト実行例：

```bash
node tests/test-three-worker-merge.cjs KASF-v3.0-Rev0.2.2.html
node tests/test-three-worker-edgecases.cjs KASF-v3.0-Rev0.2.2.html
node tests/test-html-script-syntax.cjs KASF-v3.0-Rev0.2.2.html
```


## 継承機能履歴：Rev0.9.20 — Temporal Phase / Musical-Noise Guards

- **Phase Jump Guard**: stable, non-attack tracks only. It bounds large circular phase innovations in the live PLL/PPR tracking path. Conservative mode triggers above 0.88 rad and limits the innovation to 0.62 rad; Balanced triggers above 0.62 rad and limits it to 0.40 rad. Attack frames and unstable frequency/amplitude transitions bypass this clamp.
- **Final isolated phase-spike pass**: inspects three adjacent frames after PPR/GPO. It corrects only a one-frame phase outlier whose phase residual is large on both sides and approximately cancels across the three-frame interval. Attack-adjacent frames are protected. It does not attempt to force persistent phase changes to a constant-phase trajectory.
- **Musical Noise Guard**: computes one-to-one frequency/amplitude continuity across adjacent frames. Weak, isolated, non-harmonic components are softly attenuated; no components are deleted. Conservative mode caps attenuation at 18% and targets only components without adjacent-frame support. Balanced mode caps attenuation at 30% and may also target one-sided short tracks. Attack-adjacent, abrupt-rise/transient, file-edge and harmonic-related components are protected. Components with adjacent-frame support are protected in Conservative mode.
- Both controls expose OFF / Conservative / Balanced. Conservative is the default; OFF is a comparison path. The feature works on encoded components before KASF packing and does not change the KASF v1 format or Reader v1.2.
- These are heuristic safeguards, not a complete perceptual denoiser. Their effect on real music must be judged by listening and objective A/B comparisons; no quality improvement is claimed without those tests.
- Conservative phase-innovation limit: trigger above 0.88 rad, cap at 0.62 rad. Balanced: trigger above 0.62 rad, cap at 0.40 rad. These values apply only to established tracks with small frequency/amplitude changes; attack and unstable tracks bypass the limiter.
- Musical Noise Guard screens components at or above 120 Hz that are very weak relative to the frame peak (and below the small absolute-amplitude ceiling), then uses adjacent-frame matching to estimate persistence. Conservative only attenuates unsupported isolated components; Balanced may also attenuate one-sided short tracks. The 18% / 30% values are maximum per-component attenuation, not global gain changes.

Test:

```bash
node tests/test-temporal-guards.cjs KASF-v3.0-Rev0.2.2.html
```

## WASM source rebuild / 2026-11-20 maintenance

`src/kasf_wasm.cpp` is the source for the embedded standalone WASM binary. The build scripts now target the primary `KASF-v3.0-Rev0.2.2.html` rather than the historical Rev0.9.16 comparison HTML.

- Clang validation: `bash build-validate.sh`
- Emscripten production build: `bash build-emscripten.sh`
- Embed-only verification: `python3 tools/embed_wasm.py build/kasf-core-clang-validation.wasm KASF-v3.0-Rev0.2.2.html --check`
- Pipeline regression: `node tests/test-wasm-build-pipeline.cjs`

Both build scripts accept `KASF_HTML` and `KASF_WASM_OUT` overrides. The embed utility validates the WASM header, requires exactly one embed marker, writes atomically, and supports non-mutating byte verification. See `WASM_BUILD_PIPELINE.md` and `WASM_BUILD_PIPELINE_TEST_RESULTS.md` for details. The 2026-11-20 Clang output is byte-identical to the existing 17,706-byte embedded payload. Emscripten itself was unavailable in that validation environment, so its production build remains unexecuted.

## v3.0 Rev.0.2.2 — Experimental JARS cooperative development (2026-11-20)

The `jars` experiment mode now collects residual-spectrum, HPSS and Kalman gap cues into one cooperative proposal set. Every candidate is re-rendered and re-evaluated against the current quantized Reader output before it can be committed; later candidates therefore see earlier accepted changes. Standalone `hpss` and `kalman` modes remain available. This is still an explicit experimental mode, not a standard/default feature. See `JARS_COOPERATIVE_INTEGRATION_NOTES.md` for scope, test coverage, and unperformed real-audio/device checks.

Regression test:

```bash
node tests/test-jars-cooperative.cjs KASF-v3.0-Rev0.2.2.html
```
