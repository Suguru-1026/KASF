# KRM Stage12 — Region Integration & Structural Classification

**Document ID:** KRM-S12-DESIGN  
**Version:** Draft 0.5  
**Date:** 2026-11-16  
**Status:** KRM scope and Stage12 v1 design baseline decided; implementation and empirical validation not started  
**Supersedes:** Draft 0.4 for current KRM scope and Stage12 design baseline  
**Language:** Japanese project context / English technical identifiers

---

## 0. この文書の役割

本書は、KRM Stage12の設計を一つにまとめた現行正本である。Draft 0.3までに分散していた決定、暫定値、未決定事項を整理し、Draft 0.4では実装開始時に設計者の推測が入り込まないよう、未決定だったアルゴリズム上の選択も初期仕様として決定した。

### 0.1 ステータス表記

- **DECIDED**：Stage12の設計上の採用決定。変更する場合は仕様改訂を行う。
- **BASELINE**：v1実装で採用する初期値・初期ルール。実験後に改訂できるが、実装間で勝手に変更してはならない。
- **TUNABLE**：設定で変更可能なパラメータ。既定値と実効値を必ず記録する。
- **DEFERRED**：Stage12 v1では扱わないと決定した事項。未決定のまま実装に持ち込むのではなく、対象外として境界を固定したもの。
- **NON-GOAL**：Stage12が目的としないこと。

「設計決定」と「性能が実証済みであること」は別である。本書のアルゴリズム・閾値は実装の基準を定めるものであり、実データに対する精度や最適性を証明するものではない。評価結果に基づいて変更する場合はDraft 0.5以降で理由と変更点を記録する。

### 0.2 KRM全体の専門領域（プロジェクト決定）

**DECIDED：KRMは、音声信号およびその派生表現から、単一または複数の信号処理・解析処理によって分離、抽出、識別できる成分を専門に扱う分析システムとする。**

KRMが扱う「成分」は、必ずしも独立した物理音源や、KASF内部の単一保存単位を意味しない。時間・周波数・振幅・位相・チャンネル・統計的特徴・原音との対応関係など、定義された解析条件の下で識別可能になる**分析上の成分（analysis component）**を指す。

KRMの主な専門対象：

- 原音と再構成音の間で欠落・弱化した成分（omission / attenuation-related components）。
- 再構成音側に余分に現れる成分や、再構成によって形成された可能性のあるアーティファクト成分（excess / artifact-related components）。
- 原音と再構成音の双方に対応物があるが、振幅・位相・周波数・時間構造などが変化した成分（transformed / mismatch components）。
- 1つまたは複数の処理を組み合わせることで初めて分離・識別できる複合的な成分。
- 必要に応じて、符号化内部表現や追加メタデータと照合可能な成分。ただし、その内部情報へのアクセスをKRMの必須条件にはしない。

**対象範囲を決める条件は「KASF内部に保存されていないこと」ではなく、「定義された処理によって対象成分を分離・抽出・識別できること」である。**したがって、KASF内部に保存されている成分であっても、最終再構成音に含まれる不自然な成分（例：ミュージカルノイズ様の構造）が処理によって識別可能ならKRMの分析対象になり得る。

一方、KRMはv1時点で次を保証しない：

- あらゆる音源や聴覚的現象を完全分離できること。
- 分離された成分が独立した物理音源であること。
- すべての分離結果が相互排他的、直交、または加算的であること。
- 分離された成分だけから発生原因や聴感上の悪影響を断定できること。

分離は解析上の表現・マスクとして実施してよく、元PCMを破壊的に切り分けることを必須にしない。分離成分は重複してよく、元信号への再合成が保証されるのは、明示的な分解・再構成条件と誤差検証を満たした場合に限る。分離結果には処理履歴・入力由来・条件・信頼度または不確実性を付与する。

専用アーキテクチャ（例：特定アーティファクト専用検出器、特定帯域・時間構造専用分離器）は将来追加可能な拡張とし、KRM全体の専門領域を特定のアーキテクチャや単一アルゴリズムに固定しない。

## 1. プロジェクトの前提と不変条件

### 1.1 KASF・KASR・KRMの関係

- **KASF**：音声表現・再構成システム。
- **KASR (Kino Audio Structure Residue)**：Source PCMとKASF再構成音の差分に現れる残差構造を研究する対象。
- **KRM**：KASRを解析するシステム。KASFの表現方式自体を勝手に変更しない。

基本関係：

\[
R[n,c] = X[n,c] - B[n,c], \qquad X[n,c] = B[n,c] + R[n,c]
\]

- `X`：正本となるSource PCM。
- `B`：適用する合成・正規化・位置合わせ・量子化を終えたKASF Reader出力。
- `R`：Raw Residual PCM。

### 1.2 Raw Residual PCMの不変性

**DECIDED：Raw Residual PCMは不変データとする。**

- Stage12は読み取りのみを行い、解析マスク・領域・特徴量・分類・レポートを派生データとして作る。
- Raw Residual PCMに対するフィルタ、正規化、量子化、上書き、再符号化は禁止。
- 解析メタデータの削除・再生成は、残差PCMの完全復元性に影響してはならない。
- 時間・周波数ブリッジは接続関係を表すメタデータであり、実在する信号セルとしてRaw Residual PCMへ書き戻してはならない。

### 1.3 データ由来の注意

過去のKRM実験に使われた`B`には、Reader相当の診断的再構成が含まれる。すべての`B`が完全な公式KASF Generator/Readerスタックから独立に書き出された最終PCMであることは、常に確認済みとは限らない。また、KASF v1ヘッダーだけではSource WAVとの厳密な対応を暗号学的に保証できない。

そのため各実行は、入力ファイル名・SHA-256・再構成方式・位置合わせ・サンプルレート・チャンネル数・上流バージョンを記録する。診断配列由来の結果を、公式Reader出力全般に対する確定的な結論として扱わない。

### 1.4 既存実験値

過去の解析でよく使われた参照グリッド：

- sample rate：44,100 Hz
- STFT size：2,048 samples
- hop：512 samples
- frame interval：およそ11.61 ms
- bin spacing：およそ21.53 Hz

これは現行実験データの条件であり、KRMの普遍定数ではない。実際の値は必ず入力マニフェストから取得する。

### 1.5 KASF本体処理とKRM処理の境界

**DECIDED：基本のシステム境界は、KASF Readerが所定の最終PCM出力を確定した後に置く。** KASFは符号化・内部表現・復号・合成・KASF側の正規化等を担当し、KRMは受け取った信号ビューを対象に残差生成・成分分離・成分分析を担当する。

基本データフロー：

```text
KASF SIDE
Source PCM (X) -> KASF Encoder / Representation -> KASF Reader -> Final PCM (B)
                                                        |
                                                        v
                                        KASF-KRM Read-only Interface
                                                        |
KRM SIDE                                                v
Input Adapter -> Provenance / Alignment Validation -> Analysis Views
                                                     |       |       |
                                                     X       B       optional C
                                                     |
                                      Residual Builder (R = X - B)
                                                     |
                                  Component Extraction / Separation
                                                     |
                                  Component Analysis / Specialized Modules
```

- `X`と`B`は、残差比較モードにおける基本入力である。`R = X - B`はKRM側のResidual Builderが作る。
- `C`はKASF内部表現・コンポーネント対応表・符号化メタデータ等の任意サイド情報を表す。初期KRMの必須入力にはしない。後から提供可能になった場合、KRM Adapterを通じて追加できる。
- KRMはKASF内部の処理関数を直接呼び出したり、KASFの符号化データ・設定・出力PCMを書き換えたりしない。
- KRMは`X`、`B`、`R`、および許可された任意サイド情報から解析用ビューを作成し、1つまたは複数の処理を組み合わせて成分を分離・抽出する。
- KASFとの接続はAdapterで吸収する。KRM Coreは特定のKASFファイル形式やReader実装に依存しない。
- 入力データの時間軸・サンプルレート・チャンネル・量子化形式が一致しない場合、Adapterは黙って切り詰め・補間・再サンプリングを行わない。変換は明示的なポリシーとログを伴う。

この境界により、KASFの内部仕様が変わっても、KRM Adapterが契約を満たせばKRM Coreを維持できる。将来、KASF内部コンポーネント情報`C`を渡す拡張を追加しても、KRMの基本処理はそれに依存しない。

## 2. Stage12の目的・範囲

### 2.1 目的

Stage11のS0/S1/S2/S3時間周波数セルを受け取り、活動セルを領域にまとめ、許可条件の下で領域を統合し、領域特徴量と構造ラベルを生成する。

- Stage11：残差活動がどこにあり、活動量の大まかな段階が何か。
- Stage12：それらの活動がどのような連結構造を作り、どのような形状・時間・周波数的特徴を持つか。

### 2.1.1 KRM全体に対するStage12の位置付け

Stage12はKRM全体の専門領域そのものを定義するものではなく、KRMが扱う分析成分のうち、主として時間・周波数セル上で表現された成分候補を領域化・統合・特徴化・構造分類する処理段階である。

Stage12 v1の標準入力はStage11のS0/S1/S2/S3セルマップであり、現行の基準経路ではRaw Residual PCM由来の時間周波数解析結果を使う。ただしKRM全体の対象はResidual PCMだけに限定されない。将来、`X`や`B`から別の処理によって抽出した成分候補を分析する専用モジュールが追加された場合、それらは別のKRM分析経路として接続できる。Stage12の既存仕様を、そのような専用モジュールの存在条件にしない。

### 2.2 処理段階

| ID | 名称 | 役割 |
|---|---|---|
| 12-A | Region Extraction | S2/S3セルからフレーム内の初期領域を抽出 |
| 12-B1 | Direct Connection | 直接接続する初期領域を統合 |
| 12-B2 | Temporal Bridging | 時間方向の短い空白を条件付きで橋渡し |
| 12-B3 | Frequency Bridging | 周波数方向の短い空白を条件付きで橋渡し |
| 12-B4 | S1 Bridging | S1セル経路を条件付きで橋渡し |
| 12-B5 | Validation | 統合エッジ・統合成分の検証 |
| 12-C | Feature Extraction | 領域特徴量計算 |
| 12-D | Structural Classification | 複数ラベルの構造適合度を計算 |

### 2.3 対象外

Stage12は、KASFの改変、Raw Residual PCMの変更、聴感上の可聴／不可聴の断定、残差の物理的原因の断定（量子化ノイズ等）、弱い領域の一律削除を行わない。Transient / Diffuse / Tonalは構造ラベルであり、相互排他的な物理現象や原因分類ではない。

## 3. 決定事項一覧

| ID | 決定 | 状態 |
|---|---|---|
| D-01 | 領域統合は接続ベース＋限定的橋渡しのハイブリッド方式 | DECIDED |
| D-02 | 統合順序はB1直接接続→B2時間→B3周波数→B4 S1→B5検証 | DECIDED |
| D-03 | 元領域ID・形状・特徴量・所属セル・統合履歴を完全保持 | DECIDED |
| D-04 | 全体ロールバックと部分ロールバックの両方に対応 | DECIDED |
| D-05 | 元領域は不変とし、統合領域を新規派生レコードとして生成 | DECIDED |
| D-06 | 統合イベント・実行履歴は追記型で保持 | DECIDED |
| D-07 | 構造分類はTransient / Diffuse / Tonal / Unclassified | DECIDED |
| D-08 | 分類はマルチラベルとし、重複適合を許容 | DECIDED |
| D-09 | 実測セル・S1橋渡しセル・仮想コネクタを別レイヤーで保持 | DECIDED |
| D-10 | 座標の正本は整数frame/bin、秒/Hzは入力マニフェストから換算 | DECIDED |
| D-11 | 直接接続は4近傍。斜め角だけの接触は直接接続としない | DECIDED |
| D-12 | 形状の正本はセル集合。保存はフレーム単位RLEを標準とする | DECIDED |
| D-13 | 複数解像度は別レイヤー。解像度をまたいだ直接統合はしない | DECIDED |
| D-14 | v1の自動パラメータ調整は無効。固定ベースラインから開始 | DECIDED |
| D-15 | Stage12 v1ではチャンネルごとに独立処理し、左右統合しない | DECIDED |
| D-16 | 入出力はJSON/JSONL/CSV/PNG。バイナリ形状形式はv1で採用しない | DECIDED |
| D-17 | KRMの専門領域は、単一または複数の処理で分離・抽出・識別できる音声成分の構造分析 | DECIDED |
| D-18 | KRMの対象を「KASFに未保存の成分」だけに限定しない。再構成音側の成分も対象に含める | DECIDED |
| D-19 | KRM v1の基本境界はKASF Reader最終PCM出力後。KRMはAdapter経由でX/B等を受け取る | DECIDED |
| D-20 | KASF内部情報Cは任意サイド情報とし、KRMの初期必須入力にしない | DECIDED |
| D-21 | 分離成分は分析上の成分とし、物理的独立性・直交性・加算的完全分解を前提にしない | DECIDED |
| D-22 | 将来の専用分離・検出アーキテクチャはKRMの拡張モジュールとして追加可能 | DECIDED |

## 4. 座標系・時間周波数グリッド

### 4.1 正本座標

**DECIDED：セルの識別には整数座標を使う。**

1セルのキーは`(channel_id, resolution_id, frame_index, bin_index)`。Stage12 v1の統合処理は同一チャンネル・同一解像度内のみで行う。

- `frame_index`：0始まりの整数。
- `bin_index`：0始まりの整数。rFFTの場合はDCからNyquist側へ昇順。
- 区間表記：すべて半開区間`[start, end)`。endは含まない。
- time/frequencyは検索・表示・レポート用の物理座標であり、セル同一性の正本ではない。

### 4.2 物理座標

入力マニフェストで以下を必須にする。

- sample rate、FFT size、hop size、window名と定義、center/padding規則
- frame timestamp convention（window start / center / end）
- frequency-bin convention（rFFTか、DC/Nyquistの扱い）
- frame/binの実際の有効範囲

標準STFTの中心時刻は、入力側のframe offsetを`o` samplesとして、`t_f=(f*hop+o)/sample_rate`で求める。各frameの時間セル幅は`hop/sample_rate`。周波数中心は標準rFFTなら`f_k=k*sample_rate/fft_size`、周波数セル幅は`sample_rate/fft_size`。窓関数の分解能とbin間隔を同一概念として扱わない。

### 4.3 端点・欠損

領域のframe/bin範囲は半開区間。範囲外、NaN、欠損、無効セルは`INVALID`として保持し、S0（低活動）に置き換えない。無効セルを橋渡し経路として使用しない。

## 5. Stage12-A — Region Extraction

### 5.1 入力契約

Stage12-Aは正規化されたStage11セルマップを受け取る。上流形式が異なる場合はAdapterで下記形式へ変換し、変換ログを残す。

- 入力マニフェスト：入力ID/hash、チャンネル、サンプルレート、STFT設定、Stage11バージョン、閾値設定
- セル状態：`S0 / S1 / S2 / S3 / INVALID`
- セル活動量：可能なら残差パワーまたはdB-over-local-floor
- frame/bin対応表とセル有効マスク

Stage11の実ファイル形式はAdapter側で検査する。ファイル形式の違いをStage12本体の推測で吸収してはならない。

### 5.2 S0〜S3の扱い

- S0：near-silent。数学的な完全無音を意味しない。
- S1：低活動。通常の領域seedには使わないが、B4の候補セルとして保存する。
- S2：活動セル。
- S3：高活動セル。
- INVALID：データがなく判定不能。無音扱いも橋渡しも禁止。

### 5.3 初期領域の生成ルール

**BASELINE：フレーム単位の連続bin-run抽出。**

1. チャンネル・解像度を分けて処理する。
2. 各frameについて、S2/S3の連続bin列を抽出する。
3. 連続bin列1本を初期領域（Original Region）1個とする。
4. S1/S0/INVALIDはrunを分断する。S1は別マスクへ保持する。
5. frameをまたぐ接続は12-Aでは行わず、12-B1で処理する。

この方式により、同一frame内の周波数方向の連続性は初期runに含まれ、時間方向の隣接はB1で明示的に処理できる。

## 6. Stage12-B — ハイブリッド階層統合

### 6.1 共通ルール

- 入力領域を変更せず、統合出力は新しいIDを持つ派生領域とする。
- 各passの開始時に入力スナップショットを固定する。
- 同一pass内の候補はそのスナップショットから一括評価する。
- 候補の並び順に依存しない決定的な規則を使用する。
- 直接観測されたセルと橋渡しメタデータを混ぜない。
- すべての採用・棄却候補をMerge Eventとして記録する。

### 6.2 12-B1 — Direct Connection

**DECIDED：4近傍接続。**

隣接frameのrun A/Bは、bin範囲が少なくとも1bin重なる場合に接続する。bin範囲が隣り合うだけで重ならない場合は、同一frame内での周波数接続とはみなさず、B3等の条件で評価する。斜め角だけで触れるセル（8近傍のみの接触）は接続しない。

候補グラフの連結成分を統合単位とする。入力順序を変えても結果が一致するよう、IDと座標を正規化して出力する。B1は欠損セルやS0/S1を飛び越えて接続しない。

### 6.3 12-B2 — Temporal Bridging

時間ギャップ`g_t`は、Aの最終観測frameとBの開始frameの間に存在する欠落frame数とする。

`g_t = start_frame(B) - end_frame_exclusive(A)`

ただしAが`[start,end)`の場合、A最終frameは`end-1`であり、B開始frameとの差から空白frame数を計算する。実装ではこの半開区間定義に統一する。

**BASELINE条件：**

1. `1 <= g_t <= max_time_gap_frames`。
2. A/Bの境界frameのbin supportを1binずつ拡張した集合について、Support Overlap Coefficientが0.50以上。
3. 境界frameの中央値活動量差が12 dB以下。
4. INVALIDセルを経路に含まない。
5. B3で必要な周波数方向の独立した空白を同時に飛び越えない。
6. B5の成分検証を通過する。

Support Overlap Coefficient：

\[
SOC(A,B)=\frac{|A'\cap B'|}{\min(|A'|,|B'|)}
\]

`A'`と`B'`は境界frameのbin集合を許容1binだけ膨張させた集合。空集合なら0。これは橋渡し適合度であり、確率ではない。

**v1の制限：**周波数が時間とともに大きく移動するchirpを、ギャップ越しに外挿して自動接続しない。境界support条件を満たさないchirpは分割状態で保持する。見逃しより誤統合回避を優先する。

### 6.4 12-B3 — Frequency Bridging

周波数ギャップ`g_f`は、A/Bのbin範囲の間にある未活動bin数とする。周波数bin indexで算出し、v1の判定単位はbin数とする。Hz換算値は報告へ併記する。

**BASELINE条件：**

1. `1 <= g_f <= max_frequency_gap_bins`。
2. A/Bの時間supportが重なり、Temporal Support Overlap Coefficientが0.50以上。
3. 追加の時間ギャップを同時に飛び越えない。
4. 境界活動量差が12 dB以下。
5. INVALIDを含まない。
6. B5の成分検証を通過する。

\[
TSOC(A,B)=\frac{|T_A\cap T_B|}{\min(|T_A|,|T_B|)}
\]

`T_A/T_B`はその領域が実際に活動セルを持つframe index集合。空集合なら0。v1ではlinear FFT binを使用し、log-frequency距離やCQT等との混在は行わない。

### 6.5 12-B4 — S1 Bridging

S1セルは観測された低活動データであり、仮想コネクタとは別に保持する。S1経路を使用できるのは、別々の2領域を接続する短い経路に限る。

**BASELINE条件：**

1. 経路は4近傍のS1セルのみで構成される。
2. 経路の両端は、異なる2つの現行領域の境界に接続する。
3. 同一領域への自己接続、3領域以上への分岐、閉ループは認めない。
4. 経路のtime spanは最大2 frame、frequency spanは最大2 bin、S1 cell数は最大4。
5. 各S1セルは有効データであり、局所floorからの超過がStage11定義のS1範囲にある。
6. S1活動強度は`delta_db = 10*log10(P_cell/P_local_floor)`で記録する。bridge score用の正規化値は`u=clip((delta_db-6)/6,0,1)`とし、経路中央値`median(u) >= 1/3`を要求する。これは中央値で概ね8 dB以上に相当する。
7. 端点領域間の境界活動量差は12 dB以下。
8. B5の成分検証を通過する。

複数のS1経路が競合する場合は、(a) path cell数が少ない、(b) median(u)が高い、(c) region IDの辞書順が小さい、の順で決定する。同じS1セルを複数の採用経路に重複使用しない。採用されなかった経路は棄却イベントに記録する。

### 6.6 12-B5 — Validationと競合解決

検証は候補エッジ単位と、候補エッジを適用した後の連結成分単位で行う。

#### 6.6.1 候補エッジ評価

各候補は、ギャップ上限、support overlap、活動量差、INVALID不使用、橋渡し種別などの必須条件をすべて満たさなければならない。加点合計で必須条件違反を相殺してはならない。

候補scoreは優先順位付けにのみ使用する。確率とは呼ばない。

- B2/B3：`bridge_score = 0.5*support_overlap + 0.5*exp(-abs(median_delta_db)/12)`
- B4：`bridge_score = 0.5*median(u) + 0.5*(1 - (path_cells-1)/4)`

0〜1にclipする。初期採用下限は`bridge_score >= 0.60`。この下限は合成試験で調整するTUNABLE値である。

#### 6.6.2 成分単位の過剰統合防止

同一pass内の候補エッジをbridge score降順、gap昇順、source region ID昇順で整列し、決定的union-findで適用する。候補を追加した結果、成分の成長制限を超える場合はその候補エッジだけを棄却する。既に確定した直接接続（B1）をbridge段階が分割することはしない。

同点時の順序は`stage_id → gap → canonical source IDs`で固定する。入力配列の順序やhash mapの列挙順に依存してはならない。

#### 6.6.3 成長率の定義

- `bbox_area_growth = merged_bbox_cell_area / union_of_parent_bbox_cell_area`
- `duration_growth = merged_time_span_frames / max(parent_time_span_frames)`
- `bandwidth_growth = merged_bin_span / max(parent_bin_span)`

分母が0の場合は候補を棄却し、エラーコードを記録する。親bboxのunion areaはセル単位で矩形unionを数える。形状セル数（observed cell count）とbbox面積を混同しない。

**BASELINE上限：**bbox area growth 3.0、duration growth 4.0、bandwidth growth 3.0。初期領域のB1直接接続にはこのgap-growth制限を適用せず、integrity検査だけを行う。B2〜B4に適用する。

成長制限を超える候補は棄却し、ソース領域はそれぞれ独立のまま残す。候補連結成分を丸ごと削除してはならない。

## 7. 統合パラメータ

### 7.1 v1ベースライン

| パラメータ | v1既定値 | 状態 |
|---|---:|---|
| `max_time_gap_frames` | 2 | BASELINE / TUNABLE |
| `time_gap_hard_limit_frames` | 8 | BASELINE safety cap |
| `max_frequency_gap_bins` | 2 | BASELINE / TUNABLE |
| `frequency_gap_hard_limit_bins` | 8 | BASELINE safety cap |
| `temporal_support_overlap_min` | 0.50 | BASELINE / TUNABLE |
| `frequency_temporal_overlap_min` | 0.50 | BASELINE / TUNABLE |
| `boundary_median_delta_db_max` | 12.0 dB | BASELINE / TUNABLE |
| `temporal_bridge_frequency_tolerance_bins` | 1 | BASELINE |
| `s1_bridge_enabled` | true | DECIDED direction |
| `s1_max_bridge_frames` | 2 | BASELINE |
| `s1_max_bridge_bins` | 2 | BASELINE |
| `s1_max_bridge_cells` | 4 | BASELINE |
| `s1_min_median_normalized_activity` | 0.333333 | BASELINE |
| `bridge_score_min` | 0.60 | BASELINE / TUNABLE |
| `max_area_growth_ratio` | 3.0 | BASELINE / TUNABLE |
| `max_duration_growth_ratio` | 4.0 | BASELINE / TUNABLE |
| `max_bandwidth_growth_ratio` | 3.0 | BASELINE / TUNABLE |
| `direct_connectivity` | 4 | DECIDED |
| `adaptive_time_gap` | false | DECIDED for v1 |
| `adaptive_frequency_gap` | false | DECIDED for v1 |
| `preserve_original_regions` | true | DECIDED |
| `preserve_merge_tree` | true | DECIDED |
| `record_parameter_changes` | true | DECIDED |

### 7.2 自動調整

**DECIDED：Stage12 v1では自動パラメータ調整をOFFにする。**

理由：領域密度や局所ノイズ床に応じた自動調整の方向性は決められるが、調整式・窓長・変化幅・ヒステリシス・検証データが未成熟なままONにすると、同じ入力でも説明不能な条件差が生じるため。

v1では固定ベースラインを使用し、すべての実効値とconfig hashを保存する。将来のv1.xで自動調整を導入する場合は、別のcontroller versionと独立した合成評価を必須とする。

### 7.3 パラメータ制限

通常gap値はhard limitを超えて設定できない。設定値が上限を超えた場合は黙ってclipせず、設定エラーとして実行前に停止する。安全上限自体を変更する場合は仕様バージョン変更を要する。

## 8. 領域形状とデータモデル

### 8.1 形状の正本

**DECIDED：意味上の正本はframe/binセル集合。保存形式はフレーム単位Run-Length Encoding (RLE)。**

1つのrunは`[frame_index, bin_start, bin_end_exclusive)`。同一frame内で隣接するbin runは統合し、昇順に並べる。展開すると元のセル集合へ完全復元できなければならない。

- bounding box：派生キャッシュ。正本ではない。
- polygon/contour：表示用派生データのみ。正本にしない。
- hole/irregular shape：RLEセル集合で保持し、塗りつぶして消してはならない。
- observed S2/S3 cells、observed S1 bridge cells、inferred connector geometry：別々に保存。

### 8.2 3層データモデル

1. **Original Region**：12-Aの不変出力。
2. **Merged Region**：統合処理が作る派生領域。
3. **Merge Event**：試行・採用・棄却・取消を記録するイベント。

#### Original Region例

```json
{
  "region_id": "OR-000001",
  "channel_id": 0,
  "resolution_id": "stft-2048-512",
  "frame_index": 0,
  "bin_start": 12,
  "bin_end_exclusive": 18,
  "cell_count": 6,
  "input_manifest_hash": "..."
}
```

#### Merged Region例

```json
{
  "region_id": "MR-000001",
  "generation": 1,
  "parent_region_ids": ["OR-000001", "OR-000002"],
  "member_original_ids": ["OR-000001", "OR-000002"],
  "observed_active_shape_ref": "shape://MR-000001/active",
  "observed_s1_shape_ref": null,
  "inferred_connector_refs": ["bridge://ME-000001"],
  "integration_stage": "12-B1",
  "status": "active",
  "run_id": "..."
}
```

#### Merge Event例

```json
{
  "event_id": "ME-000001",
  "run_id": "...",
  "stage": "12-B2",
  "input_region_ids": ["MR-000001", "MR-000002"],
  "output_region_id": "MR-000003",
  "status": "accepted",
  "reason_code": "temporal_bridge_passed",
  "parameters_snapshot_ref": "config://...",
  "bridge_score": 0.72,
  "validation_metrics": {},
  "created_from_snapshot": "..."
}
```

### 8.3 所属・履歴の不変条件

- すべてのMerged Regionは1つ以上のOriginal Regionへ遡れる。
- `member_original_ids`は親のmember集合のunionと一致し、重複を除去する。
- 親子関係はDAG（有向非巡回グラフ）であり、cycleは禁止。
- 同一runのactive outputで、同じOriginal active cellを複数のactive merged regionへ重複所属させない。
- 同一S1 cellを複数のaccepted bridgeで重複利用しない。
- すべてのeventのinput/output IDは同一run内で解決可能である。

## 9. 複数解像度・チャンネル方針

### 9.1 複数解像度

**DECIDED：各resolutionは独立したレイヤーとして処理する。**

異なるFFT size/hopのframe/bin cellを直接同一セルとして統合してはならない。将来の比較時は物理時間・周波数領域へ写像し、time-frequency rectangleの重なりでcross-resolution associationを作る。ただしStage12 v1ではそのassociationを別metadataとして保存するだけで、merged regionを作る根拠にはしない。

### 9.2 ステレオ

**DECIDED：Stage12 v1ではチャンネルごとに独立処理する。**

Ch0/Ch1の領域統合・特徴量・分類を混ぜない。左右対応の相関や共通構造は後段の別モジュール候補とし、Stage12の統合処理へ含めない。

## 10. Rollback・Replay

### 10.1 原則

**DECIDED：全体・部分の両方に対応。履歴は追記型。**

rollbackで原領域や既存イベントを物理削除・上書きしない。取消イベントを追加し、active statusを再評価する。再計算結果は新しいevent/output IDまたは新run IDで保存する。

### 10.2 全体rollback

指定runの派生結果をinactiveにし、12-A snapshotを有効な基点として戻す。入力Source/Residual/Stage11データは変更しない。

### 10.3 部分rollback

指定eventと、その出力に依存するすべてのdescendant event/outputを無効化し、最も近い有効snapshotから下流を再実行する。依存しないbranchは維持可能。

### 10.4 再現性検証

同一入力・同一config・同一software versionでclean runしたactive resultと、rollback/replay後のactive resultが一致すること。run ID・時刻等のvolatile metadataを除いたcanonical result hashを比較する。履歴には元実行と修正実行の両方を残す。

## 11. Stage12-C — Feature Extraction

### 11.1 基本定義

特徴量は実測S2/S3セルを主対象とし、S1 bridge cellとinferred connectorは別集計とする。missing/INVALIDはS0として数えない。

- `N_t`：bbox内のframe数。
- `N_f`：bbox内のbin数。
- `N_obs`：S2/S3 observed cell数。
- `A_bbox=N_t*N_f`。
- `density=N_obs/A_bbox`。
- `active_frames`：S2/S3セルが1つ以上あるframe集合。
- `active_bins`：S2/S3セルが1つ以上あるbin集合。

### 11.2 必須特徴量と数式

| Feature | 定義 |
|---|---|
| duration | `N_t * hop / sample_rate`。物理的な端時刻はframe conventionから併記 |
| bandwidth | `N_f * sample_rate / fft_size`。bin端境界で補正したHz範囲も併記 |
| frequency centroid | power-weighted mean frequency。重み総和0ならnull |
| mean cell RMS | `sqrt(mean(P_cell))`。Pは各観測セルのlinear power |
| median cell RMS | `sqrt(median(P_cell))` |
| peak cell RMS | `sqrt(max(P_cell))` |
| observed cell count | `N_obs` |
| S1 bridge cell count | bridgeに実際に使用したS1 cell数 |
| connector count | 推定コネクタ数。observed cell数には加えない |
| occupancy density | `N_obs/A_bbox` |
| temporal continuity | 隣接frameのbin集合について、全隣接ペアのintersection総数 / union総数 |
| frequency continuity | 隣接binのframe集合について、全隣接ペアのintersection総数 / union総数 |
| aspect ratio | `N_t / max(1,N_f)`（grid-cell aspect ratioとして記録） |
| centroid variation | frameごとのpower-weighted centroidの標準偏差。該当frame不足ならnull |
| intensity variation | frame RMS列のcoefficient of variation `std/mean`。mean=0ならnull |
| feature completeness | `valid_data_cells / A_bbox`。S0/S1/S2/S3は有効、INVALIDは無効。併せて`invalid_fraction=invalid_cells/A_bbox`を報告 |

連続性の分母が0の場合は0ではなくnullとし、feature completenessとともに扱う。`valid_data_cells`はbbox内でS0/S1/S2/S3のいずれかに判定されたセル数、`invalid_cells`はINVALIDセル数とする。したがって`feature_completeness + invalid_fraction = 1`（bbox内に全セルが存在する場合）。全特徴量にunit、formula version、validity flagを付ける。

## 12. Stage12-D — Structural Classification

### 12.1 ラベル意味

- **Transient Residue**：短時間・時間方向に集中した残差構造。
- **Diffuse Residue**：周波数または時間方向に広がり、局在した狭帯域構造が支配的でない残差。
- **Tonal Residue**：相対帯域幅が狭く、周波数重心が安定または緩やかに変化する残差。
- **Unclassified Residue**：特徴不足、無効データ過多、またはいずれの分類も基準未満。

これらは構造ラベルであり、物理的原因・聴感上の重要度・良否を断定しない。

### 12.2 v1スコア規則

スコアは0〜1のheuristic fit scoreであり、確率ではない。下記は解釈可能性を優先した初期ルール。

- `D`：duration (seconds)
- `W`：bandwidth (Hz)
- `fc`：frequency centroid (Hz)
- `df`：bin spacing (Hz)
- `sigma_fc`：centroid variation (Hz)
- `Ct`：temporal continuity [0,1]
- `rho`：occupancy density [0,1]

補助値：

\[
relBW = \frac{W}{\max(|f_c|,df)},\quad
narrow = e^{-relBW/0.08},\quad
stable = e^{-\sigma_{f_c}/\max(W,df)}
\]

初期スコア：

\[
S_T = e^{-D/0.15}\,(0.5+0.5(1-C_t))
\]

\[
S_{Ton} = (narrow\cdot stable\cdot(0.5+0.5C_t))^{1/3}
\]

\[
broad = 1-e^{-relBW/0.20},\quad
long = 1-e^{-D/0.25}
\]

\[
S_D = (broad\cdot(0.5+0.5\rho)\cdot(0.5+0.5long))^{1/3}
\]

すべて0〜1にclipする。Transient計算で単一frame領域の`Ct`が未定義の場合に限り、classification専用の代替値`Ct=0`を使い、`fallback_used=true`を記録する。Tonal計算で`centroid variation`が未定義（有効active frameが2未満）の場合は、安定性を推測せず`score=null`とする。その他、null特徴量がスコア計算に必要な場合も、そのラベルを無理に計算せず`score=null`とする。

**BASELINE label threshold：0.60。** 0.60以上のラベルをすべて付与する。複数該当を許容する。いずれも閾値未満、またはfeature completeness <0.80ならUnclassifiedにする。Unclassifiedは4つ目の確率クラスではなくabstention status。

confidence/probabilityはv1では出力しない。閾値と式は合成signalのground truthで評価し、必要なら後版で改訂する。

## 13. 入出力形式・バージョン

**DECIDED：v1の論理データ形式はUTF-8 JSON / JSONL / CSV / PNG。**

| データ | 標準形式 | 方針 |
|---|---|---|
| run manifest / config | JSON | 1 runに1つ。schema version必須 |
| original regions | JSONL | 1 region / line。RLE shapeを含むか参照 |
| merged regions | JSONL | 1 region / line。親子IDとshape refs |
| merge events | JSONL | 1 event / line。accepted/rejected/revertedを保存 |
| feature table | CSV | 1 region / row。null表現を明記 |
| classification | JSONL | 1 region / line。式version・score semanticsを保存 |
| reports/metrics | JSON | machine-readable summary |
| figures | PNG | 可視化専用。正本データではない |

バイナリshape containerはStage12 v1では採用しない。必要になった場合はJSONL RLEと完全往復できる別仕様を制定する。ファイル順、region順、JSON key順、数値出力精度をcanonicalization規則で固定し、hashが再現可能であること。

## 14. Resource・実行環境

**BASELINE resource profile：**追加working memory 512 MiB以下、1 worker、channel単位・frame chunk単位処理。これはStage12 v1の設計目標であり、まだ実測達成を意味しない。

- 全時間周波数float tensorの複製を避ける。
- まず1 channel / 1 resolutionで処理する。
- mask・RLE・union-find等の必要最小限の構造を保持する。
- chunk境界の領域ID・接続状態を引き継ぎ、境界跨ぎの領域を分断しない。
- メモリ上限到達時は閾値や解析結果を変更せず、安全停止してcheckpointを残す。
- 初期段階ではwall-clock timeの合格値は固定しない。処理時間・ピークメモリを常に測定し、複数データで基準を作る。

想定計算量：セル走査・RLE抽出はO(N_cells)、候補edge構築は索引を用いて平均O(N_regions+E)、union-findは概ねO(E α(N))。実装データ構造と実測で再評価する。

## 15. 検証計画・受入基準

### 15.1 必須synthetic test

| Test | 主な確認 |
|---|---|
| Digital silence | 活動領域・統合が0 |
| Stationary noise | 無制限な領域成長が起きない |
| Persistent tone | 狭帯域持続・Tonalスコア |
| Short impulse/burst | Transientスコア・短時間形状 |
| Chirp | 境界supportと分割動作 |
| Intermittent tone | B2 temporal bridge |
| Nearby distinct tones | False Merge抑制 |
| S1-separated weak signal | B4 bridgeのprecision/recall |
| Broadband burst | Diffuse/Transientの重複 |
| Hole/ring shape | hole保持・bbox density |
| L-shape/diagonal cells | 4近傍接続・RLE復元 |
| A-B-C bridge chain | 成分成長制限・決定性 |
| Competing S1 paths | tie-breakの再現性 |
| Rollback/replay | clean runとの一致 |
| Repeat run | deterministic hash |
| Invalid/missing cells | silenceへの誤変換がないこと |

### 15.2 受入基準

以下はStage12 v1の初期gate。synthetic suiteのデータ数・SNR・seed・ground-truth生成条件を固定して評価する。

**Hard invariants（100%必須）**

- Raw Residual PCM hashが解析前後で一致。
- Original Regionと履歴が欠落・上書きされない。
- RLE encode/decodeがcell集合として完全一致。
- 同一入力/config/software versionのcanonical outputs hashが一致。
- 全体rollback後と部分rollback/replay後のactive outputがclean rerunと一致。
- INVALIDをS0/S1/S2/S3へ暗黙変換しない。
- 仮想connectorがobserved cell数・energyを増やさない。

**Initial performance gates（調整対象）**

- デジタル無音：false active region = 0。
- 直接接続：4近傍ground truthのexact component agreement = 100%。
- 非接続として定義したadversarial pair：false merge = 0。
- bridge全体：precision >= 0.95、recall >= 0.80を初期目標とする。B2/B3/B4別々にも報告。
- region matching：IoU >= 0.50のone-to-one matchingでprecision/recallを算出。
- False Merge Rate：誤ったground-truth objectを一つにしたaccepted merge数 / accepted bridge merge数。overall <= 0.01、adversarial subset = 0を目標。
- classification：ラベル別F1を報告し、synthetic macro-F1 >= 0.80を初期目標とする。未達の場合は分類器を不合格または暫定扱いとし、閾値を隠れて変更しない。
- peak additional working memory <= 512 MiB。
- 処理時間は測定・記録必須だが初版では固定上限を設けない。

これらは初期受入gateであり、現時点で達成済みの結果ではない。実際の評価レポートで未達・条件不足を明示する。

### 15.3 指標の定義

Ground-truth region matchingはIoUによるone-to-one matchingとし、1つのpredicted regionを複数truth regionに重複matchさせない。Region Precision/Recall、cell coverage、bridge precision/recall、False Merge / False Splitを別々に報告する。分母の単位（cell / region / bridge event / sample）を必ず表記する。

## 16. 出力ディレクトリ案

```text
KRM_STAGE12/
├── manifest/
│   ├── run_manifest.json
│   └── input_manifest.json
├── config/
│   └── effective_config.json
├── source/
│   └── original_regions.jsonl
├── regions/
│   ├── merged_regions.jsonl
│   └── region_shapes_rle.jsonl
├── history/
│   ├── merge_events.jsonl
│   ├── execution_history.jsonl
│   └── rollback_history.jsonl
├── features/
│   └── region_features.csv
├── classification/
│   └── classification_results.jsonl
├── validation/
│   ├── synthetic_tests.json
│   └── validation_report.json
├── figures/
├── reports/
└── SHA256SUMS.txt
```

Raw Residual PCMは別管理し、Stage12分析bundleへ無条件に複製しない。

## 17. Draft 0.3でOPENだった16項目の最終決定

| 旧ID | Draft 0.4での決定 | 理由 |
|---|---|---|
| O-01 座標系 | 整数frame/bin正本、物理座標併記、半開区間 | 端点誤差・off-by-oneを防ぎ、再現性を上げる |
| O-02 直接接続 | 4近傍 | 斜め接触だけの誤統合を防ぐ。recallよりprecision優先 |
| O-03 形状形式 | セル集合が意味上の正本、frame単位RLE保存 | 穴・不規則形状を完全保持し、復元可能 |
| O-04 複数解像度 | resolution別レイヤー。cross-resolutionはassociationのみ | 異なるbin/frameを同一視しない |
| O-05 時間bridge | 境界support SOC >=0.50、1bin tolerance、delta <=12dB | 小ギャップの同一帯域継続だけを保守的に接続 |
| O-06 周波数bridge | 時間support TSOC >=0.50、時間gapなし、linear bin | 同じ時間に共存する近接帯域だけを接続 |
| O-07 S1適格性 | 4近傍、別2領域間、2frame×2bin以下、最大4cell、median normalized activity >=1/3 | S1の鎖状誤統合・同一regionの自己接続を抑制 |
| O-08 成長率 | bbox union比3.0、duration比4.0、bandwidth比3.0をB2-B4に適用 | 実面積とbbox面積を分け、式の分母を固定 |
| O-09 自動調整 | v1ではOFF | 未検証controllerによる再現性低下を防止 |
| O-10 大成分処理 | candidate edgeをscore順に制約付きunion-find。超過edgeだけ棄却 | valid branchを保ち、連結成分全体を捨てない |
| O-11 特徴量 | Section 11の数式へ固定 | density/continuity等の解釈を実装間で一致させる |
| O-12 分類 | Section 12のheuristic multi-label式、threshold 0.60 | 説明可能な初期規則。probabilityとは呼ばない |
| O-13 serialization | UTF-8 JSON/JSONL/CSV/PNG、schema version付き | prototype段階の可読性・検証容易性を優先 |
| O-14 resource | 512MiB working memory、1 worker、chunk処理 | 低スペック環境も視野に入れた保守的profile |
| O-15 channel | v1はチャンネル独立 | 左右の異なる残差構造を無理に混ぜない |
| O-16 acceptance | Section 15のhard invariants/performance gates | 実装完了の判定基準を明示 |

## 18. 実装準備状態

**Stage12 v1の設計上の未決定項目：なし（Draft 0.5のbaselineに限る）。KRM全体の専門領域とKASF/KRM境界も本版で定義した。**

Stage12 v1の構造・座標・接続・bridge条件・形状表現・rollback・feature式・classification式・serialization・resource profile・acceptance gateを定義した。

ただし、次はまだ未実施であり、設計完了と混同しないこと。

- Stage11実データとのAdapter接続・schema適合試験
- Python実装
- synthetic test実行
- memory/processing-time実測
- 実残差データへの適用
- 閾値・分類式の性能検証

したがって本書の状態は **DESIGN BASELINE COMPLETE / IMPLEMENTATION NOT STARTED / EMPIRICAL VALIDATION NOT STARTED** とする。

## 19. 実装の推奨順序

1. Stage11 adapterとinput manifest validator
2. RLE encode/decodeとcell-mask invariant tests
3. 12-A frame-local run extraction
4. 12-B1 4-neighbour linking
5. B2/B3 bridge candidate generationとscore
6. B4 S1 path searchとconflict resolution
7. B5 constrained union-findとmerge event log
8. immutable lineage / full & partial rollback / replay
9. feature extraction
10. heuristic multi-label classification
11. synthetic suite・acceptance report・resource benchmark
12. real residual diagnostic datasetでの評価（provenance caveat付き）

実装中に仕様不足が見つかった場合、独断でアルゴリズムを足さず、仕様改訂として記録する。

## 20. Revision history

| Version | Date | Summary |
|---|---|---|
| Draft 0.1 | 2026-11-16 | Stage12の初期アーキテクチャ |
| Draft 0.2 | 2026-11-16 | Hybrid integration、parameter controller、hierarchy/rollback案 |
| Draft 0.3 | 2026-11-16 | 決定・暫定値・OPEN事項を整理した詳細設計 |
| Draft 0.4 | 2026-11-16 | 旧OPEN 16項目を一括決定。座標、接続、bridge、S1、shape、features、classifier、serialization、resource、acceptanceをv1 baselineとして固定 |
| Draft 0.5 | 2026-11-16 | KRM全体の専門領域を「処理によって分離・抽出・識別できる成分の分析」と定義。KASF/KRM境界、任意内部情報C、Stage12の位置付けを明記 |

---

**End of document — KRM Stage12 Design Specification Draft 0.5**
