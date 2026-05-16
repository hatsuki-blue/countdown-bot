"""
Discord カウントダウンBot (スラッシュコマンド版)
/add でカテゴリ内にカウントダウンチャンネルを作成・自動更新する
"""

import discord
from discord import app_commands
from discord.ext import tasks
from datetime import datetime, timedelta
import json
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CATEGORY_ID = int(os.getenv("CATEGORY_ID", "0"))
ANNOUNCE_CHANNEL_ID = int(os.getenv("ANNOUNCE_CHANNEL_ID", "0"))
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "9"))
DATA_FILE = os.path.join(os.path.dirname(__file__), "countdowns.json")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


# --- データ管理 ---

def load_countdowns() -> list[dict]:
    """保存済みカウントダウン一覧を読み込む"""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_countdowns(data: list[dict]):
    """カウントダウン一覧を保存する"""
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# --- ユーティリティ ---

def get_now():
    """現在のローカル時刻を取得"""
    return datetime.utcnow() + timedelta(hours=TIMEZONE_OFFSET)


def get_remaining_days(target_date: str) -> int:
    """目標日付までの残り日数を計算する"""
    now = get_now()
    target = datetime.strptime(target_date, "%Y-%m-%d")
    return (target.date() - now.date()).days


def build_channel_name(name: str, days: int) -> str:
    """残り日数からチャンネル名を生成する"""
    if days > 0:
        return f"{name}：残り{days}日"
    elif days == 0:
        return f"🎉{name}：当日🎉"
    else:
        return f"{name}：{abs(days)}日経過"


def parse_target_date(date_str: str) -> str:
    """様々な形式の日付文字列を YYYY-MM-DD 形式に変換する"""
    date_str = date_str.replace('/', '-').replace('.', '-')
    now = get_now()

    parts = date_str.split('-')
    try:
        # YYYY-MM-DD or YY-MM-DD
        if len(parts) == 3:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            if year < 100:
                year += 2000
            dt = datetime(year, month, day)
            return dt.strftime("%Y-%m-%d")
        
        # MM-DD or M-D
        elif len(parts) == 2:
            month, day = int(parts[0]), int(parts[1])
            year = now.year
            dt = datetime(year, month, day)
            
            # 今年ですでに過ぎている日付の場合は来年にする
            if dt.date() < now.date():
                dt = dt.replace(year=year + 1)
                
            return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass
        
    raise ValueError("Invalid date format")



# --- チャンネル更新 ---

async def auto_sort_channels(force: bool = False) -> bool:
    """必要に応じてカテゴリ内のチャンネルを残り日数が少ない順に並び替える"""
    countdowns = load_countdowns()
    if not countdowns:
        return False
        
    # 残り日数が少ない順にソート
    countdowns.sort(key=lambda cd: get_remaining_days(cd["target_date"]))
    save_countdowns(countdowns)
    
    category = client.get_channel(CATEGORY_ID)
    if not category:
        return False
        
    # 現在のカテゴリ内のテキストチャンネルを取得
    current_channels = category.text_channels
    if not current_channels:
        return False
        
    # カウントダウン対象のチャンネルIDリスト（現在の並び順）
    current_order = [c.id for c in current_channels]
    
    # 理想の並び順（カウントダウン対象のチャンネルIDのみ抽出）
    ideal_order = [cd["channel_id"] for cd in countdowns]
    
    # current_order の中で、ideal_order に含まれるものを抽出して相対的な順番を確認
    current_relative_order = [cid for cid in current_order if cid in ideal_order]
    
    # 既に理想の順番ならAPIを叩かずに終了（強制フラグがなければ）
    if not force and current_relative_order == ideal_order:
        return False

    # 順番が違う場合のみソートを実行
    try:
        # カウントダウン用のチャンネルが現在占有している最小のポジションを取得
        cd_channels = [c for c in current_channels if c.id in ideal_order]
        if not cd_channels:
            return False
            
        base_pos = min(c.position for c in cd_channels)
        
        payload = []
        for i, cd in enumerate(countdowns):
            payload.append({
                "id": str(cd["channel_id"]),
                "position": base_pos + i  # 重複しないように厳密な連番を付与
            })
                
        # Discordの内部APIを使用して1回のリクエストで全チャンネルの位置を更新（レートリミット対策）
        route = discord.http.Route('PATCH', '/guilds/{guild_id}/channels', guild_id=category.guild.id)
        await client.http.request(route, json=payload)
        
        print("✅ チャンネルを自動ソートしました")
        return True
    except Exception as e:
        print(f"❌ 自動ソート中にエラーが発生しました: {e}")
        return False


async def update_all_countdowns():
    """全カウントダウンチャンネルを更新する"""
    countdowns = load_countdowns()
    if not countdowns:
        return

    needs_save = False

    for cd in countdowns:
        channel = client.get_channel(cd["channel_id"])
        if channel is None:
            print(f"⚠️ チャンネルが見つかりません (ID: {cd['channel_id']}, 名前: {cd['name']})")
            continue

        days = get_remaining_days(cd["target_date"])
        new_name = build_channel_name(cd["name"], days)

        # 当日のお知らせ処理
        if days == 0 and not cd.get("announced", False):
            if ANNOUNCE_CHANNEL_ID != 0:
                announce_channel = client.get_channel(ANNOUNCE_CHANNEL_ID)
                if announce_channel:
                    try:
                        await announce_channel.send(f"🎉 **本日は「{cd['name']}」の当日です！** 🎉\n> 📅 目標日: {cd['target_date']}")
                        cd["announced"] = True
                        needs_save = True
                        print(f"✅ お知らせ送信: {cd['name']}")
                    except Exception as e:
                        print(f"❌ お知らせ送信失敗 ({cd['name']}): {e}")
                else:
                    print("⚠️ お知らせ用のチャンネルが見つかりません。ANNOUNCE_CHANNEL_IDを確認してください。")

        if channel.name == new_name:
            continue

        try:
            await channel.edit(name=new_name)
            print(f"✅ 更新: {new_name}")
        except discord.errors.Forbidden:
            print(f"❌ 権限不足: {cd['name']}")
        except discord.errors.HTTPException as e:
            print(f"❌ 更新失敗 ({cd['name']}): {e}")

    if needs_save:
        save_countdowns(countdowns)

    # 更新後に自動ソートも行う
    await auto_sort_channels()


# --- イベント ---

@client.event
async def on_ready():
    print(f"✅ ログイン完了: {client.user}")
    print(f"📁 カテゴリID: {CATEGORY_ID}")

    # スラッシュコマンドを同期
    await tree.sync()
    print("✅ スラッシュコマンドを同期しました")

    countdowns = load_countdowns()
    print(f"📅 登録済みカウントダウン: {len(countdowns)}件")

    await update_all_countdowns()

    if not countdown_task.is_running():
        countdown_task.start()


@tasks.loop(minutes=30)
async def countdown_task():
    """30分ごとにチャンネル名を更新する"""
    await update_all_countdowns()


# --- スラッシュコマンド ---

@tree.command(name="add", description="カウントダウンを追加してチャンネルを作成する")
@app_commands.describe(
    name="カウントダウンの名前（例: 文化祭）",
    date="目標日付（例: 12/31, 6/4, 2026/12/31）"
)
async def add_countdown(interaction: discord.Interaction, name: str, date: str):
    # 日付バリデーションとパース
    try:
        parsed_date = parse_target_date(date)
    except ValueError:
        await interaction.response.send_message(
            "❌ 日付形式が正しくありません。`MM/DD` または `YYYY/MM/DD` 形式で指定してください。（例: 12/31, 6/4, 2026/12/31）",
            ephemeral=True
        )
        return

    # 以降は YYYY-MM-DD 形式の parsed_date を使用
    date = parsed_date

    # カテゴリ取得
    category = client.get_channel(CATEGORY_ID)
    if category is None or not isinstance(category, discord.CategoryChannel):
        await interaction.response.send_message(
            "❌ カテゴリが見つかりません。`.env` の `CATEGORY_ID` を確認してください。",
            ephemeral=True
        )
        return

    # 重複チェック
    countdowns = load_countdowns()
    for cd in countdowns:
        if cd["name"] == name:
            await interaction.response.send_message(
                f"❌ `{name}` は既に登録されています。先に `/remove` で削除してください。",
                ephemeral=True
            )
            return

    # 応答を遅延（チャンネル作成に時間がかかる場合がある）
    await interaction.response.defer()

    # チャンネル作成
    days = get_remaining_days(date)
    channel_name = build_channel_name(name, days)

    try:
        channel = await category.create_text_channel(name=channel_name)
    except discord.errors.Forbidden:
        await interaction.followup.send("❌ チャンネルを作成する権限がありません。")
        return
    except discord.errors.HTTPException as e:
        await interaction.followup.send(f"❌ チャンネル作成に失敗しました: {e}")
        return

    # 保存
    countdowns.append({
        "name": name,
        "target_date": date,
        "channel_id": channel.id
    })
    save_countdowns(countdowns)

    embed = discord.Embed(
        title="✅ カウントダウン追加",
        color=0x57F287
    )
    embed.add_field(name="名前", value=name, inline=True)
    embed.add_field(name="目標日付", value=date, inline=True)
    embed.add_field(name="チャンネル", value=channel.mention, inline=True)
    await interaction.followup.send(embed=embed)
    
    # 新規追加時も自動ソート
    await auto_sort_channels()


@tree.command(name="remove", description="カウントダウンを削除してチャンネルも削除する")
@app_commands.describe(name="削除するカウントダウンの名前")
async def remove_countdown(interaction: discord.Interaction, name: str):
    countdowns = load_countdowns()
    target = None
    for cd in countdowns:
        if cd["name"] == name:
            target = cd
            break

    if target is None:
        await interaction.response.send_message(
            f"❌ `{name}` は登録されていません。",
            ephemeral=True
        )
        return

    await interaction.response.defer()

    # チャンネル削除
    channel = client.get_channel(target["channel_id"])
    if channel:
        try:
            await channel.delete(reason=f"カウントダウン削除: {name}")
        except discord.errors.Forbidden:
            pass
        except discord.errors.HTTPException:
            pass

    countdowns = [cd for cd in countdowns if cd["name"] != name]
    save_countdowns(countdowns)

    await interaction.followup.send(f"✅ カウントダウン `{name}` を削除しました。")


@tree.command(name="list", description="登録中のカウントダウン一覧を表示する")
async def list_countdowns(interaction: discord.Interaction):
    countdowns = load_countdowns()

    if not countdowns:
        await interaction.response.send_message("📭 カウントダウンは登録されていません。")
        return

    # 残り日数が少ない順にソート
    countdowns.sort(key=lambda cd: get_remaining_days(cd["target_date"]))

    embed = discord.Embed(
        title="📅 カウントダウン一覧",
        color=0x5865F2
    )

    for cd in countdowns:
        days = get_remaining_days(cd["target_date"])
        status = build_channel_name(cd["name"], days)
        channel = client.get_channel(cd["channel_id"])
        ch_text = channel.mention if channel else "（チャンネル不明）"
        embed.add_field(
            name=cd["name"],
            value=f"📆 {cd['target_date']}\n⏳ {status}\n📢 {ch_text}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@tree.command(name="update", description="全カウントダウンチャンネル名を強制更新する")
async def force_update(interaction: discord.Interaction):
    await interaction.response.defer()
    await update_all_countdowns()
    await interaction.followup.send("✅ 全カウントダウンチャンネルを更新しました。")


@tree.command(name="sort", description="チャンネルの並び順を残り日数が少ない順に整理する")
async def sort_channels(interaction: discord.Interaction):
    await interaction.response.defer()
    
    # コマンドで呼ばれた場合は強制的にAPIを叩いてDiscordの表示バグを直す
    result = await auto_sort_channels(force=True)
    if result:
        await interaction.followup.send("✅ チャンネルとリストを残り日数が少ない順にソートしました！")
    else:
        await interaction.followup.send("✅ ソート処理を実行しました（すでに正しい状態か、登録がありません）。")


# --- エラーハンドリング ---

@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ このコマンドは管理者のみ使用できます。",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ エラーが発生しました: {error}",
            ephemeral=True
        )


if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN が設定されていません。.env ファイルを確認してください。")
        exit(1)
    if CATEGORY_ID == 0:
        print("❌ CATEGORY_ID が設定されていません。.env ファイルを確認してください。")
        exit(1)

    client.run(TOKEN)
