import hashlib
import io
import os
import traceback
from datetime import timedelta

import aiohttp
import discord
import pytesseract
from Levenshtein import distance
from PIL import Image
from discord.ext import commands

import db

SCAM_WORDS = "withdraw claim reward casino crypto mrbeast promo special cryptocurrency vip bonus redeem receive coin deleted wallet celebrate register transferred promotion chance money winner successful block explorer deposit".split()
TRIGGER_LEVEL = 0.75
HASH_FILE = os.path.join(os.path.dirname(os.path.abspath(os.getenv("DB_PATH", "bot.db"))), "scam_hashes.txt")


def load_hashes():
    try:
        with open(HASH_FILE) as f: return set(f.read().splitlines())
    except FileNotFoundError: return set()


def save_hashes(new):
    with open(HASH_FILE, "a") as f:
        for h in new: f.write(h + "\n")


async def run_ocr(message, images):
    known_hashes = load_hashes()
    image_hashes, matches, all_text = [], {}, ""

    async with aiohttp.ClientSession() as session:
        for i, att in enumerate(images):
            async with session.get(att.url) as resp:
                data = await resp.read()
            h = hashlib.sha256(data).hexdigest()
            image_hashes.append(h)

            if h in known_hashes:
                embed = discord.Embed(title="Recognized Scam Hash", color=0xd42c03)
                embed.description = f"Deleted message in {message.channel.mention} by {message.author.mention}"
                return True, embed

            try: text = pytesseract.image_to_string(Image.open(io.BytesIO(data))).strip()
            except pytesseract.TesseractError: continue
            except OSError:
                print("[scam] tesseract-ocr not installed")
                return False, None
            if not text: continue

            all_text += text + " "
            matches = {}
            for sw in SCAM_WORDS:
                c = sum(1 for w in all_text.lower().split() if distance(w, sw) <= 2)
                if c: matches[sw] = c

            total_hits = sum(matches.values())
            confidence = 1 - 1 / (1 + len(matches) ** 2 / len(SCAM_WORDS) * (1 + total_hits / 10))

            if confidence >= TRIGGER_LEVEL:
                for remaining in images[i + 1:]:
                    async with session.get(remaining.url) as resp:
                        rdata = await resp.read()
                    image_hashes.append(hashlib.sha256(rdata).hexdigest())
                save_hashes([h for h in image_hashes if h not in known_hashes])

                match_list = ", ".join(f"{w} (x{c})" for w, c in matches.items())
                embed = discord.Embed(title="Scam Message Detected", color=0xf7b200)
                embed.description = f"Deleted message in {message.channel.mention} by {message.author.mention}"
                embed.add_field(name="Confidence", value=f"{confidence:.1%} after {i + 1} image{'s' if i else ''}", inline=True)
                embed.add_field(name="Matches", value=match_list, inline=False)
                return True, embed

    return False, None


class ScamDetection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _log_channel(self, guild_id):
        settings = db.get_guild_settings(guild_id)
        channel_id = (settings and settings["log_channel"]) or int(os.getenv("LOG_CHANNEL_ID", 0))
        return self.bot.get_channel(channel_id) if channel_id else None

    @commands.Cog.listener()
    async def on_message(self, message):
        try:
            if message.author.bot: return
            images = [a for a in message.attachments if a.content_type and a.content_type.startswith("image/")]
            if not images: return

            is_scam, embed = await run_ocr(message, images)
            if not is_scam: return

            try:
                await message.author.timeout(timedelta(seconds=60), reason="Blocking scam")
                await message.delete()
            except: pass

            processing_time = int((discord.utils.utcnow() - message.created_at).total_seconds() * 1000)
            embed.set_footer(text=f"Processing time: {processing_time}ms")

            log_channel = self._log_channel(message.guild.id)
            if log_channel:
                await log_channel.send(embed=embed)
        except Exception:
            print(f"[scam] error:\n{traceback.format_exc()}")


async def setup(bot):
    await bot.add_cog(ScamDetection(bot))