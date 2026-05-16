# 📅 Discord カウントダウンBot

コマンドで名前と日付を指定すると、指定カテゴリ内にカウントダウンチャンネルを自動作成・更新するBotです。

## セットアップ

### 1. Discord Bot の作成

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. 「New Application」でアプリを作成
3. 左メニュー「Bot」→「Add Bot」
4. 「TOKEN」をコピー（後で `.env` に設定）
5. 「Privileged Gateway Intents」で **MESSAGE CONTENT INTENT** を有効化

### 2. Bot をサーバーに招待

1. 左メニュー「OAuth2」→「URL Generator」
2. SCOPES: `bot`
3. BOT PERMISSIONS: `Manage Channels`（チャンネル作成・名前変更に必要）
4. 生成されたURLをブラウザで開いて招待

### 3. 環境構築

```bash
pip install -r requirements.txt
cp .env.example .env
```

### 4. `.env` ファイルを編集

```env
DISCORD_TOKEN=取得したBotトークン
CATEGORY_ID=カウントダウン用カテゴリのID
TIMEZONE_OFFSET=9
```

> **カテゴリIDの取得方法**: Discord設定 → 詳細設定 → 開発者モードON → カテゴリを右クリック → 「IDをコピー」

### 5. Bot の起動

```bash
python bot.py
```

## 使い方

### カウントダウンを追加

```
!add イベント名 2026-12-31
```

指定カテゴリ内に `残り○日-イベント名` というチャンネルが自動作成されます。

### カウントダウンを削除

```
!remove イベント名
```

チャンネルも一緒に削除されます。

## コマンド一覧

| コマンド | 説明 | 権限 |
|---|---|---|
| `!add 名前 日付` | カウントダウンを追加（チャンネル自動作成） | 管理者 |
| `!remove 名前` | カウントダウンを削除（チャンネルも削除） | 管理者 |
| `!list` | 登録中のカウントダウン一覧を表示 | 全員 |
| `!update` | 全チャンネル名を強制更新 | 管理者 |

## チャンネル名の表示

| 状況 | チャンネル名の例 |
|---|---|
| 目標日まで残りがある | `残り30日-イベント名` |
| 当日 | `🎉当日-イベント名🎉` |
| 過ぎた場合 | `3日経過-イベント名` |

## 注意事項

- **レートリミット**: チャンネル名の変更はDiscord APIの制限があるため、更新間隔は30分に設定しています
- カウントダウンデータは `countdowns.json` に永続化されます
- 複数のカウントダウンを同時に管理できます
