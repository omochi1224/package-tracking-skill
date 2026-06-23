---
name: package-tracking
description: 日本の配送業者（ヤマト運輸・佐川急便・日本郵便・アスクル）の荷物を追跡番号から追跡する。Use when the user gives a tracking number or asks "荷物 / 配送 / 追跡 / where is my package" for a Japanese carrier and wants current delivery status or history.
---

# Package Tracking (日本の配送業者)

追跡番号から、日本の主要配送業者の配送状況・履歴を取得するスキル。
対応キャリア: ヤマト運輸 / 佐川急便 / 日本郵便（国内・国際）/ アスクル。

各社の公開追跡ページを取得して解析する。API キーや認証は不要。

## いつ使うか

- ユーザーが追跡番号（例: `442676947510`、`4426-7694-7510`、`LP009985404IN`）を提示したとき
- 「荷物どこ？」「配送状況」「届いた？」など配送状況を尋ねられたとき

## 使い方

`scripts/track.py` を実行する。結果は JSON で stdout に出力される。

```bash
# 自動判別（推奨）— 全キャリアを順に試す
python3 scripts/track.py 442676947510

# キャリアを明示（速い・確実）
python3 scripts/track.py 4426-7694-7510 --carrier yamato
python3 scripts/track.py 681012345678   --carrier sagawa
python3 scripts/track.py LP009985404IN  --carrier japanpost
python3 scripts/track.py 121047704455   --carrier askul
```

`--carrier` の値: `auto`（既定）/ `yamato` / `sagawa` / `japanpost` / `askul`

### キャリアの見分け方（指定する場合の目安）

| キャリア | `--carrier` | 番号フォーマット |
|---|---|---|
| ヤマト運輸 | `yamato` | 12桁の数字 |
| 佐川急便 | `sagawa` | 12桁の数字 |
| 日本郵便 | `japanpost` | 12桁の数字、または国際追跡番号（英2字+数字9桁+英2字 例 `LP009985404IN`） |
| アスクル | `askul` | 数字 |

数字12桁はヤマト・佐川・日本郵便・アスクルで重複するため、ユーザーがキャリアを
明言していなければ `auto`（自動判別）を使う。`LP009985404IN` のような国際番号は
`japanpost` 確定。

## 出力フォーマット

成功時（JSON）:

```json
{
  "carrier": "yamato",
  "carrier_jp": "ヤマト運輸",
  "tracking_number": "442676947510",
  "item_type": "クロネコヤマトの宅急便",
  "is_delivered": true,
  "current_status": { "status": "お届け済み", "date": "2026-03-30T14:30:00+09:00", "name": "本人" },
  "complete_text": "お届け済み",
  "history": [
    { "status": "荷物受付", "date": "2026-03-29T10:00:00+09:00", "name": "〇〇営業所" },
    { "status": "お届け済み", "date": "2026-03-30T14:30:00+09:00", "name": "本人" }
  ],
  "detected_carrier": "ヤマト運輸"
}
```

失敗時（JSON、終了コード 1）:

```json
{ "error": "tracking_failed", "message": "お問い合わせ番号が見つかりません。" }
```

依存パッケージ未導入時（終了コード 2）: `error` が `missing_dependency` になる。

## 結果のまとめ方（ユーザーへの回答）

JSON をそのまま貼らず、要点を日本語で要約する:

1. **現在の状況**: `current_status.status` と `is_delivered`（配達完了か否か）を最初に。
2. **キャリア / 品名**: `carrier_jp`、あれば `item_type`。
3. **最終更新**: `current_status.date`（JST, ISO 8601）。
4. ユーザーが履歴を求めたら `history` を時系列（古い→新しい）で簡潔に列挙。
5. `error` が返ったら、`message` をそのまま伝え、番号の確認や時間をおいた再試行を促す。

## セットアップ

依存: `requests`, `beautifulsoup4`。未導入なら:

```bash
pip install -r requirements.txt
```

## 注意

- 公開ページのスクレイピングのため、各社のページ構造変更で解析が失敗することがある。
  その場合は `tracking_failed` / 解析失敗のメッセージが返る。
- 反映が遅れて「該当なし」になることがある。発送直後は時間をおいて再試行する。
- このスキルは公開前提。認証情報・個人情報は一切含めない（User-Agent も汎用文字列）。
