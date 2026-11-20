# KRM Time-Domain CSC / CDL Research — Draft 0.2

このパッケージはKRM / KASF本体から独立した、波形を直接扱う研究エンジンです。周波数データへの変換、KASF v1の成分数、既存FastGenの設計は制約にしません。

## インストール

```bash
python -m pip install -e ".[research]"
```

NumPyは研究用のoptional dependencyです。既存の`krm_proto`の標準ライブラリだけで動く構成は維持しています。

## 基本CSC実験

```bash
python benchmarks/run_research.py
python benchmarks/run_research.py --wav source.wav --samples 4096
```

## 辞書学習実験

```bash
python benchmarks/run_dictionary_learning.py --wav source.wav
```

複数WAVを比較する場合は`--wav`を繰り返します。主な設定は`--segment-samples`、`--train-count`、`--validation-count`、`--atom-length`、`--atoms`、`--outer-iterations`、`--coding-iterations`です。結果はJSONへ保存されます。

ステレオ入力は各チャンネルを別々の訓練例として扱い、共通の辞書を学習します。左右チャンネル間の相関を同時に最適化するJoint Stereo Modelではありません。訓練・検証の時間窓は固定seedで分割され、検証窓を辞書初期化・学習には使いません。

## 現在のアルゴリズム

- 有限長・full-overlap線形畳み込み（zero extension）。周期的な端点接続はしない。
- Atomごとに長さ`N + L_k - 1`の係数マップ。
- 前向き演算子と厳密に対応する随伴演算子。
- Monotone backtracking FISTA / proximal gradient。
- FISTAの近似収束判定にproximal-gradient mapping（KKT固定点残差）を追加。
- 直接時間領域ADMM + 行列フリーConjugate Gradients。
- 波形パッチからの固定辞書初期化。
- 交互最適化型Convolutional Dictionary Learning（CDL）。
- Unit-sphere制約下の射影勾配辞書更新とArmijo backtracking。
- FISTAのwarm start、同じ信号長に対するLipschitz推定のキャッシュ。

## CDLの目的関数

```text
min_{D, a_s} 0.5 * sum_s || A_D(a_s) - x_s ||_2^2
              + lambda * sum_s,k ||a_s,k||_1
subject to ||d_k||_2 = 1
```

係数推定は辞書を固定した凸CBPDN問題としてFISTAで解き、次に係数を固定してAtomを更新します。辞書更新は各Atomの接ベクトル方向へ射影した勾配を使い、単位球面へ再射影した候補のうち、Armijo条件を満たすものだけ受理します。各外側反復の目的関数は非増加であることを検査します。

これは双線形・非凸な交互最適化です。単調な目的関数減少は大域最適解、物理的に正しい音源分離、唯一のAtom構成を保証しません。結果は初期辞書・lambda・訓練データ・反復数に依存します。

## 周波数変換について

`krm_td_csc`の参照演算子、FISTA、ADMM、辞書更新はFFT / STFT / DCTを使いません。FFTを内部計算の高速化に使う将来の別バックエンドは検討可能ですが、時間領域モデルの定義・端点条件・出力表現と混同しません。

## 検証

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
python -m compileall -q krm_proto krm_td_csc tests benchmarks
```

Draft 0.8では全66テストを実行します。CDL固有の検査には辞書勾配の有限差分比較、単位ノルム制約、目的関数非増加、異なる信号長のバッチ処理、warm start検証、決定性検査が含まれます。

## 現在の制約

- Atom学習は射影勾配＋Armijoの参照方式。大域最適性や一意性は保証しない。
- 係数最適化は指定反復数で打ち切られる場合がある。`coding_converged`と`optimality_residual`を必ず確認する。
- 直接畳み込みは短区間研究用。長時間音源にはブロック分割、slice-based / LoBCoD、ネイティブカーネル等の研究が必要。
- ステレオは共有辞書＋独立Activation Mapまで。Joint Sparsityや左右の位相・時間関係の拘束は未実装。
- λ正則化型CBPDNまで。誤差予算εを直接指定する制約型モデルは未実装。
- Matching Pursuit / OMP、オンライン辞書学習、Atom再初期化、辞書冗長性制御は未実装。
- KASF / KRC / KRM-IFとは未統合。現段階では独立の波形研究エンジン。

詳細は`docs/CONVOLUTIONAL-DICTIONARY-LEARNING-DRAFT-0.2.md`と`benchmarks/REPORT-DRAFT-0.8.md`を参照。
