# 拡散用メモ（remotion-ffmpeg-skill）

投稿・登録は kajisho5 のアカウントで行う前提。文面はそのまま貼れる形にしてある。
登録先の受付条件（星の数の下限、書式など）は各リポジトリの CONTRIBUTING を必ず読んでから出すこと（未確認）。

## 登録先の候補

| 登録先 | 種類 | 出し方 |
|---|---|---|
| Remotion 公式「List of resources」 https://www.remotion.dev/docs/resources | Remotion の公式ドキュメント内のコミュニティ資料一覧 | remotion-dev/remotion の docs に PR（掲載基準は未確認） |
| hesreallyhim/awesome-claude-code https://github.com/hesreallyhim/awesome-claude-code | Claude Code 関連のまとめ | リポジトリの案内に従って提出 |
| ComposioHQ/awesome-claude-skills https://github.com/ComposioHQ/awesome-claude-skills | Claude Skills のまとめ | PR |
| BehiSecc/awesome-claude-skills https://github.com/BehiSecc/awesome-claude-skills | Claude Skills のまとめ | PR |

## まとめリスト用の1行（英語）

```
- [remotion-ffmpeg-skill](https://github.com/kajisho5/remotion-ffmpeg-skill) - Motion graphics on real footage: ffmpeg-skill measures (silences, scenes, beats, highlights), Remotion draws captions, jump cuts, karaoke, titles and beat montages, every render verified frame-for-frame and delivered for YouTube/Reels/TikTok. Contract + MCP server, local, no API keys.
```

## X 投稿（日本語）

```
Remotion で動画を作る AI 用スキルを公開しました。

ffmpeg-skill で素材を「測って」→ Remotion で「描いて」→ 書き出しをフレーム数まで「照合」して納品形式に変換。

・無音を自動カット＋ズーム
・単語ごとに光るカラオケ字幕
・拍に合わせたモンタージュ
・縦型リール対応、日本語字幕も豆腐にならない

npx remotion-ffmpeg-skill
https://github.com/kajisho5/remotion-ffmpeg-skill
```

## X 投稿（英語）

```
I made an Agent Skill that lets Claude Code / Cursor / Codex do Remotion on real footage — without guessing numbers.

ffmpeg-skill measures (silences, scene cuts, beats) → Remotion draws → every render is checked frame-for-frame, then delivered for YouTube / Reels / TikTok.

Jump cuts, karaoke captions, beat montages, 9:16.

npx remotion-ffmpeg-skill
https://github.com/kajisho5/remotion-ffmpeg-skill
```

## Show HN（英語、必要なら）

```
Show HN: remotion-ffmpeg-skill – Remotion motion graphics for AI agents, driven by FFmpeg measurements

Coding agents can write Remotion code, but they guess: composition length, fps, where the silences are,
when the beat lands. This skill measures the footage first with ffmpeg-skill, feeds the numbers to seven
Remotion compositions (captions, jump cuts, audio-reactive, karaoke, titles, highlights, beat montage), verifies each
render frame-for-frame against the measurements, and delivers through FFmpeg platform templates with
loudness and compliance checks. It ships a machine-readable contract, an MCP server and agent evals.
Python stdlib + Node, runs locally.
```

## 載せるときの注意
- デモ GIF は架空素材（テストパターン）。実在の人物・案件の映像は使わない。
- Remotion は 4 人以上の会社では有料ライセンスが要る旨を、聞かれたら必ず添える（README に記載済み）。
- 「Remotion 公式ではない」ことを明記する（README に記載済み）。
