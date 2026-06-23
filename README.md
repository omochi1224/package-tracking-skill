# package-tracking skill

日本の主要配送業者（ヤマト運輸・佐川急便・日本郵便・アスクル）の荷物追跡を
AI エージェントから行うための [Claude Code Skill](https://docs.claude.com/en/docs/claude-code/skills) です。

各社の公開追跡ページを取得・解析して配送状況と履歴を返します。API キーや認証は不要です。

## 構成

```
SKILL.md            スキル定義（フロントマター + 使い方）
scripts/track.py    追跡 CLI（単体で実行可能、JSON 出力）
requirements.txt    依存パッケージ（requests, beautifulsoup4）
```

## インストール

スキルとして使うには `~/.claude/skills/package-tracking/` 等へ配置します。

```bash
pip install -r requirements.txt
```

## 使い方

```bash
# 自動判別
python3 scripts/track.py 442676947510

# キャリア指定
python3 scripts/track.py 4426-7694-7510 --carrier yamato
python3 scripts/track.py LP009985404IN  --carrier japanpost
```

結果は JSON で出力されます。フィールドの意味とまとめ方は [SKILL.md](./SKILL.md) を参照してください。

## 対応キャリア

| キャリア | `--carrier` | 番号フォーマット |
|---|---|---|
| ヤマト運輸 | `yamato` | 12桁の数字 |
| 佐川急便 | `sagawa` | 12桁の数字 |
| 日本郵便 | `japanpost` | 12桁の数字 / 国際追跡番号（例 `LP009985404IN`） |
| アスクル | `askul` | 数字 |

## 注意事項

- 公開ページのスクレイピングのため、各社のページ構造変更により解析が失敗する場合があります。
- 過度なリクエストは避けてください（各社の利用規約に従ってください）。

## 免責事項 / Disclaimer

- 本ソフトウェアは個人が開発した非公式ツールです。ヤマト運輸・佐川急便・日本郵便・
  アスクルをはじめとする各配送業者、および開発者の所属組織・勤務先とは
  **一切関係がなく、提携・後援・承認を受けたものではありません**。
  記載の各社名・サービス名は各社の商標です。
- 本ソフトウェアは「現状のまま（AS IS）」提供されます。配送状況の正確性・
  完全性・最新性は保証されません。各社の公開ページの仕様変更等により、
  予告なく動作しなくなる場合があります。正確な情報は必ず各配送業者の
  公式サイトでご確認ください。
- 本ソフトウェアの利用または利用不能によって生じたいかなる損害についても、
  開発者は一切の責任を負いません。利用は自己責任でお願いします。

## ライセンス

MIT（詳細は [LICENSE](./LICENSE) を参照。LICENSE には無保証条項が含まれます）
