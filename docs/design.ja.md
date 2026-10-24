# 設計メモ（remotion-ffmpeg-skill）

## 狙い

Remotion 公式のスキル（remotion-dev/skills）は「Remotion のコードを正しく書かせる」までを扱う。
このスキルはその前後を受け持つ。

1. **測る**：ffmpeg-skill で素材の長さ・フレームレート・解像度・シーンの切れ目・無音・音の山を実測する
2. **描く**：Remotion の構成（コンポジション）は、その実測値だけを材料に動く
3. **確かめて納品する**：書き出した映像を、ffmpeg-skill でフレーム数まで照合し、コマ一覧を作り、納品形式に変換して規格検査する

## 決めごと

- **このスキルは ffmpeg / ffprobe を直接呼ばない。** 測定・検査・納品はすべて ffmpeg-skill のスクリプト（`--json`）を通す。ffmpeg-skill の保証（元ファイルを上書きしない、測った値で計画する、など）をそのまま引き継ぐため。
- **数値は推測しない。** 構成の長さ・大きさ・フレームレートは `calculateMetadata` で時間軸データ（timeline.json）から決める。時間軸データを手で書き換えず、測り直す。
- **フレーム番号の丸めは Python と TypeScript で一致させる。** どちらも「四捨五入（0.5 は切り上げ）」。Python の `round()` は偶数丸めなので使わない（3.15 秒 × 30fps = 94.5 で食い違った実例あり）。
- **字幕の文字は書かれたとおりに描く。** 収まらないときも文章は変えず、文字サイズの調整を提案する。
- **書き出しの検証に失敗したら失敗として扱う。** 終了コードを 0 以外にし、どの項目が合わなかったかを返す。

## 構成

```
scripts/
  _common.py     共通処理（引数の作法、ffmpeg-skill の場所探しと呼び出し、時間軸データの検証、Remotion 用の準備）
  _captions.py   SRT / WebVTT / JSON 字幕の読み込み
  analyze.py     測る → timeline.json
  init.py        Remotion プロジェクトの雛形を作る
  still.py       指定コマを PNG で書き出す（本番前の確認）
  render.py      書き出し → 照合（フレーム数・fps・解像度・音声）→ コマ一覧
  deliver.py     ffmpeg-skill の納品テンプレート → 規格検査
  pipeline.py    測る → 描く → 納品 を一括で（各段階で検証）
  doctor.py      環境診断
templates/remotion-project/
  src/timeline.ts           時間軸データの型・既定の見た目・長さの計算
  src/Root.tsx              3 つの構成の登録
  src/compositions/         Captioned / Jumpcut / PeakPulse
  src/lib/SourceVideo.tsx   素材映像（無いときは仮の背景）
references/timeline.md      時間軸データと見た目の設定の仕様
tests/                      単体テスト・実素材での統合テスト（RFS_PROJECT 指定で実描画も）
```

## 確認済み・未確認

- 確認済み（2026-10-24、Linux・Node 22・Remotion 4.0.538・ffmpeg-skill 2.12.0）：3 構成の実描画、フレーム数の一致、YouTube / Reels の納品と規格検査、縦型（9:16）、日本語字幕（フォント自動）、音声のみの素材、重ね合わせモード、33 件のテスト。
- 描画速度（2 コアの Linux）：フルHD 30fps の 30 秒で約 170 秒。重ね合わせモードも約 174 秒で速くはならない（透過 PNG と ProRes 4444 の書き出しが重いため）。編集ソフト用の透過素材が要るとき用と位置づけた。
- 未確認：macOS / Windows での実行。

## 0.2.0 で決めたこと

- **素材は公開フォルダにハードリンク（無理ならコピー）。** シンボリックリンクだと Remotion のファイルサーバーが 404 を返す。Remotion の CLI は Mac / Linux では公開フォルダ全体をリンクで渡すので、描画のたびにコピーはされない（Windows では毎回コピーされる）。
- **納品先の比率で描く。** Reels 等のテンプレートは 9:16 に「切り抜き」で合わせるため、16:9 で描いてから納品すると字幕の端が切れる。`pipeline.py --platform` は ffmpeg-skill のテンプレートから比率を読んで、その比率で描く。
- **日本語フォントは ffmpeg-skill の環境診断が見つけたものを使う。** プロジェクトに取り込んで、最初のコマの前に読み込みを待つ（読み込めなければ描画を止める）。
- **日本語の改行は文節単位**（`word-break: auto-phrase`）、行の長さは揃える（`text-wrap: balance`）。

## 今後

- ffmpeg-skill と同じ「機械が読める契約」と MCP サーバー
- 拍（ビート）の時刻に合わせた構成
- 字幕のある区間だけを描いて重ねる方式（長尺の高速化の本命）
- テロップ・タイトル類の構成追加、複数素材
