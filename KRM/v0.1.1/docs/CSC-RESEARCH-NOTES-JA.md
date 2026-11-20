# 時間領域CSC研究ノート — Draft 0.1

## 0. 研究方針

この研究では、音声を周波数成分へ変換することを前提にしない。最終的にKASFの周波数情報へ翻訳できる可能性は残すが、現時点では設計制約にしない。

目標は、入力PCM波形を高精度に表現するモデルと、その係数・辞書を効率よく求めるアルゴリズムを調べること。ここでいう「高精度」は、復元波形の誤差、過渡音の保持、境界挙動、モデルの再現性、計算量を分けて評価する。

## 1. CSCの基本モデル

入力波形を、短い波形パターン（Atom）と、その出現位置・係数を表すActivation Mapの畳み込み和として近似する。

```text
x[n] ≈ Σ_k (d_k * a_k)[n]
```

- `x`: 入力波形
- `d_k`: 学習または設計された時間領域Waveform Atom
- `a_k`: Atomの出現位置と符号付き強度を表す係数列
- `*`: 線形畳み込み

Atomは正弦波、周波数ビン、STFTテンプレートである必要はない。短い打撃波形、音のアタック、減衰を含む波形、楽器の短い音色断片など、任意の有限長波形を扱える。

CSCの利点は、同じAtomを時間上の異なる位置に再利用できることと、パッチを個別に独立符号化するのではなく、信号全体の再構成誤差を同時に最小化できること。反面、辞書Atom同士の類似度が高いと、複数のActivation Mapが似た再構成を作り、係数の一意性や解釈可能性が落ちる。

## 2. 係数推定の目的関数

基準モデルはConvolutional Basis Pursuit Denoising（CBPDN）。

```text
min_a  0.5 * ||A(a) - x||_2^2 + λ * Σ_k ||a_k||_1
```

第一項は波形再構成誤差、第二項はActivation Mapの疎性を促すペナルティ。λを小さくすると一般に波形誤差を減らしやすいが係数が増え、大きくすると係数が疎になる代わりに残差が増える。

この目的関数は、元の発音イベントや楽器音を必ず正しく発見する保証ではない。今回の合成試験では16個の既知イベントに対し、L1解で閾値以上となった係数は95個だった。波形近似が良くてもイベント境界や元の発生回数がそのまま回復するとは限らない。

## 3. 境界条件はモデルの一部

Draft 0.1の参照実装は、周期境界の循環畳み込みではなく、ゼロ拡張した有限長の線形畳み込みを使う。

長さNの観測信号と長さL_kのAtomについて、Activation Mapの長さをAtomごとに `N + L_k - 1` とする。これにより、観測区間の先頭より前から始まって一部だけ観測区間に重なるAtomと、末尾より後へはみ出すAtomの両方を表現する。出力は各全畳み込みの中央部分 `[L_k-1 : L_k-1+N]` を取り出す。

前向き演算子Aと随伴A*は内積恒等式 `<A(a), r> = <a, A*(r)>` と有限差分勾配検査で照合する。最適化器では、前向き演算子だけ正しくても不十分で、随伴が一致していなければ勾配方向が誤る。

FFTを用いる高速CSC実装では周期境界の影響が問題となり得るため、FFTを使うかどうかとは別に境界モデルを明示する必要がある。FFTは将来、数値計算を高速化する内部バックエンドとして検討できるが、今回の参照実装は数学的な演算と境界を明確にするため、FFT/STFT/DCTを呼び出さない。

## 4. Draft 0.1の最適化器

### Monotone backtracking FISTA

L1正則化付きの凸目的関数を、勾配ステップとSoft Thresholdingで解く。べき乗法でLipschitz定数を見積もり、BacktrackingでMajorization条件を満たすステップ幅を選択する。目的関数が増加した場合はMomentumをリセットする。

利点：実装・検査が比較的簡単で、各反復が前向き・随伴畳み込み演算で構成される。

課題：反復ごとの演算が重く、現在の直接時間領域演算は長時間音源にはスケールしない。実音声短区間の試験では、300反復で収束判定に到達しなかった。

### Direct-time-domain ADMM + Conjugate Gradients

変数を分割し、L1項をSoft Thresholdingで処理する。線形系 `(A*A + ρI)a = A*x + ρ(z-u)` は、行列を明示的に構築せず、行列フリーの共役勾配法で解く。

利点：制約・正則化項を増やす設計へ拡張しやすい。

課題：各Outer Iterationで共役勾配反復が必要。現在は小規模参照実装であり、大規模データ用の実装ではない。

### 次に比較する候補

- Matching Pursuit / Orthogonal Matching Pursuit：疎なAtom配置の逐次探索基準。
- FISTA / PGM：目的関数を揃えた凸最適化比較。
- ADMM + CG：制約・辞書学習へ拡張する候補。
- Error-constrained CBPDN：λの代わりに許容誤差 ε を指定し、`min ||a||_1 subject to ||A(a)-x||_2 ≤ ε` を解く。

## 5. マルチスケール化と辞書学習の注意

Atom長を複数用意すれば、短時間の過渡構造と長い波形パターンを同時に扱える可能性がある。ただし、複数スケールを並べるだけで性能が向上するわけではない。

現行の辞書初期化は、入力波形からパッチを抜き出し、L2正規化し、相互相関が高すぎない候補を優先して選ぶだけである。これは**初期辞書の選択**であり、Activation Mapと一緒にAtomを更新するConvolutional Dictionary Learning（CDL）ではない。

同一のフィルタ係数数に揃えた短い実音声区間の探索試験では、現行のマルチスケール初期辞書が単一スケール辞書より低いSNRになった。しかし、試験は4,096サンプルだけで、辞書は同じ区間から初期化し、最適化は300反復で未収束だった。したがって、これは「現在の簡易初期化器ではマルチスケールの利点を確認できなかった」という結果であって、マルチスケールCSCそのものが劣る証拠ではない。

次の本格段階は、Activation Map更新とDictionary Atom更新を交互に行うCDL。各Atomの長さ・ノルム・許容形状、複数音源の学習、辞書の冗長性制御を明示的に検討する。

## 6. 音声分野の先行研究から得られる示唆

Jaoらの音楽音源分離研究は、音声混合を時間領域の畳み込み辞書フィルタの和として直接近似している。これはCSCが画像処理だけの考え方ではなく、音声の波形モデルとして研究されていることを示す。一方、その研究では辞書規模や補助情報の有無が結果に影響しており、CSCを採用すれば自動的に高精度になるわけではない。

別のピアノ転写研究では、個々の音高の録音波形を辞書Atomとして使う。これはタスクに合った高品質辞書の有効性を示す一方、音量や発音長が変わっても同じ音高の波形が大きく変わらないという仮定を含む。汎用的な音楽表現に拡張するには、音量・発音・音色の変化を辞書側でどう表すかが課題になる。

## 7. 今回の計測結果

### 既知辞書の合成信号

- 512 samples
- Atom長：12 / 24 / 48 / 24
- 既知の発生イベント：16
- λ = 0.002

FISTAは1,096反復で収束判定に到達し、SNR 39.831 dB、相対L2誤差0.010196。ADMM+CGは129 Outer Iteration（CG合計1,892反復）で収束判定に到達し、SNR 39.516 dB、相対L2誤差0.010573。目的関数の最終値は近く、今回の小規模ケースでは両方式が近い解を得た。

### 実音声の短区間

- 2本のWAVから最初の4,096サンプルのみ使用
- 2ch音源は今回の単一チャンネル試験に限りモノラル平均
- 16/32/64 sample Atomを各2個、合計224 Filter Parametersのマルチスケール辞書
- 32 sample Atomを7個、合計224 Filter Parametersの単一スケール辞書
- 両方ともFISTA 300反復で未収束

マルチスケール辞書のSNRは19.372 dB / 20.004 dB、単一スケール辞書は23.953 dB / 23.623 dBだった。この条件では単一スケールが上だったが、CDL未実装・短いin-sample試験・未収束という制約があるため、一般的結論にはできない。

## 8. 現在の制約と次の研究

- 単一チャンネルのみ。ステレオはまだ共同最適化していない。
- Atomは固定。辞書学習はまだない。
- L1ペナルティのみ。誤差予算を直接指定するモデルは未実装。
- 直接時間領域畳み込みの参照実装であり、長時間処理には最適化されていない。
- 実音声評価は短区間のみ。訓練・検証・テストを分離した汎化試験は未実施。
- KASF、KRC、KRM-IFとは未統合。出力はfloat64の近似波形と診断情報。

次の優先事項は、複数音源を使った交互最適化型CDL、その後に誤差制約型CBPDNとステレオ共同疎性を比較すること。Attackに不利になる可能性があるため、Activation Mapの時間平滑化は初期段階で一律に適用しない。

## 9. 主要参考文献

1. B. Wohlberg, “Efficient Algorithms for Convolutional Sparse Representations,” *IEEE Transactions on Image Processing*, 25(1), 301–315, 2016. https://doi.org/10.1109/TIP.2015.2495260
2. B. Wohlberg, “Boundary Handling for Convolutional Sparse Representations,” ICIP 2016, pp. 1833–1837. https://doi.org/10.1109/ICIP.2016.7532675
3. F. Veshki and S. Vorobyov, “Efficient ADMM-Based Algorithms for Convolutional Sparse Coding,” *IEEE Signal Processing Letters*, 29, 389–393, 2022. https://doi.org/10.1109/LSP.2021.3135196
4. P.-K. Jao, L. Su, Y.-H. Yang, and B. Wohlberg, “Monaural Music Source Separation Using Convolutional Sparse Coding,” *IEEE/ACM Transactions on Audio, Speech, and Language Processing*, 24(11), 2158–2170, 2016. https://doi.org/10.1109/TASLP.2016.2598323
5. P.-K. Jao, Y.-H. Yang, and B. Wohlberg, “Informed Monaural Source Separation of Music based on Convolutional Sparse Coding,” ICASSP 2015, pp. 236–240. https://doi.org/10.1109/ICASSP.2015.7177967
6. M. Cogliati et al., “A Convolutional Sparse Coding Approach for Piano Transcription,” source context paper: https://brendt.wohlberg.net/publications/pdf/cogliati-2016-context.pdf
7. SPORCO documentation, convolutional BPDN variants: https://sporco.readthedocs.io/en/latest/invprob/cbpdn.html
8. F. Veshki & S. Vorobyov companion code (multi-scale CDL reference): https://github.com/FarshadGVeshki/Convolutional-Sparse-Coding
