# 電磁ブレーキ学習模型 v2

**磁力のない手動プラスチック模型です。** 電磁石として作動する実機や高速ロータ用部品ではありません。モーター駆動・通電には使わないでください。

## 印刷ファイルの場所

別PCから、この非公開リポジトリにアクセスできるGitHubアカウントでサインインして取得してください。以下はすべて実ファイルです。**印刷だけなら約1.1MBのZIPを取得・展開し、片方の3MFをBambu Studioで開いてください。**

| ファイル／フォルダー | 中身・個数 | 候補材料 |
|---|---|---|
| [print-prep/p1s-brake-print-prep.zip](print-prep/p1s-brake-print-prep.zip) | 印刷準備一式。3MF2種、元STL6種、手順、配置上面図、デジタル確認記録 | 本体PLA／板ばねPETG |
| [print-prep/01-body-PLA-candidate.3mf](print-prep/01-body-PLA-candidate.3mf) | 台座・コイル役リング・ハブ・円盤・キャップ各1個、計5部品 | 本体PLA |
| [print-prep/02-springs-PETG-candidate.3mf](print-prep/02-springs-PETG-candidate.3mf) | 板ばね4枚（使用3枚＋予備1枚） | 板ばねPETG推奨 |
| [model-v2/stl/print/](model-v2/stl/print/) | 元の印刷用STL6種類。ZIP内にも同じ6種を収録 | 本体PLA／板ばねPETG |
| [print-prep/START-HERE.txt](print-prep/START-HERE.txt) | P1Sの設定候補と初回試作の確認手順 | 実際の材料プリセットを選択 |

**3MFは形状と配置のみ（geometry-only）です。設定入りBambu Studioプロジェクトではなく、プリンター・材料・工程設定もG-codeも含みません。実インポート・実スライス・実印刷は未確認です。** 標準0.4mmノズルを想定していますが、手元のノズル径・材料・ビルドプレートは未確認です。

### 別PCで取得する

1. GitHubにサインインして、このprivate repoのREADMEを開きます。
2. 上の**印刷用ZIPリンク**を開き、**Download raw file／ダウンロードアイコン**で保存します。
3. ZIPを展開し、`START-HERE.txt` を読んでからBambu Studioで片方の3MFを開きます。

ファイル単位なら上の3MF／STLリンクから **Download raw** で取得できます。リポジトリ全体を取得するなら **Code → Download ZIP** を選び、展開してください。

Gitで取得する場合は、このprivate repoへのアクセス権を持つアカウントで認証して、次のどちらかを実行します。

```sh
git clone https://github.com/ktanino10/electromagnetic-brake-lab.git
# または、GitHub CLIでログイン済みの場合
gh repo clone ktanino10/electromagnetic-brake-lab
```

### STLのファイル別印刷個数

| STL（`model-v2/stl/print/`） | 部品 | 用意する数 |
|---|---|---|
| [01_base_grey.stl](model-v2/stl/print/01_base_grey.stl) | 台座 | 1個 |
| [02_coil_ring_orange.stl](model-v2/stl/print/02_coil_ring_orange.stl) | コイル役リング | 1個 |
| [03_hub_violet.stl](model-v2/stl/print/03_hub_violet.stl) | ハブ | 1個 |
| [04_armature_blue.stl](model-v2/stl/print/04_armature_blue.stl) | 円盤 | 1個 |
| [05_leaf_spring_green_print4.stl](model-v2/stl/print/05_leaf_spring_green_print4.stl) | 板ばね | 4枚（使用3＋予備1） |
| [06_retaining_cap_grey.stl](model-v2/stl/print/06_retaining_cap_grey.stl) | 抜け止めキャップ | 1個 |

`05_leaf_spring_green_print4.stl` は**1枚だけの形状**です。STLから準備する場合は4個複製してください。

## P1Sの準備と最初の試作

標準0.4mmノズル、`0.20mm Standard`を初期候補とします。本体はPLA・壁3周・インフィル20%、板ばねはPETG・平置き・中実100%を候補にします。厚さ0.8mmの板ばねが、初層0.20mm＋通常層0.20mmで4層になるか実スライスで確認してください。温度とプレートは実際の材料・機器のプリセットを選びます。

配置はmm／100%、Z=0、P1Sの256mm造形領域内、左手前18×28mmの除外領域外、部品間外接矩形すき間5mm以上をデジタル確認しています。形状の変更はありません。ブリムやスカートの広がり、逐次印刷のヘッドクリアランスは含みません。通常の「層ごと」の印刷を使い、本体と板ばねは分けてください。

最初は3MFのコピーから**ハブ1個**と**板ばね1枚**だけを残して小さく試作します。M3ボルト／ナットの入り方、板ばねの小さなたわみと層間剥離を確認し、無理に押し込まず、締め過ぎないでください。小穴、裏のナット穴の天井のブリッジ、除去不能なサポートがないことを実スライスで確認してください。軸の回転、ナット保持、円盤の戻り、摩擦、耐久性は現物未確認です。

## 金属部品（購入・在庫未確認）

| 部品 | 仕様 | 数 |
|---|---|---|
| 六角穴付きボルト | M3×6、ISO 4762相当、並目ピッチ0.5mm | 6本 |
| 六角穴付きボルト | M3×25、ISO 4762相当、並目ピッチ0.5mm | 1本 |
| 六角ナット | M3、ISO 4032相当、二面幅5.5mm・厚さ2.4mm | 7個 |
| 平座金 | M3、ISO 7089相当、内径3.2／外径7／厚さ0.5mm | 7枚 |
| 六角レンチ | 2.5mm | 1本 |

**未印刷・未購入・物理未検証・実スライス未確認**です。プリンターへの送信／印刷開始、実機操作は行っていません。
