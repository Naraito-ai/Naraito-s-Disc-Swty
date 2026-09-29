import asyncio
import traceback
import sys
from database import db
from cogs.nba_battle import BuildTeamView
import discord

async def run_tests():
    await db.initialize()
    print("Database initialized.")
    user_ids = []
    try:
        rows = await db.fetch("SELECT DISTINCT user_id FROM user_nba_cards")
        user_ids = [r["user_id"] if isinstance(r, dict) else r[0] for r in rows]
    except Exception as e:
        print("Error fetching user_ids:", e)

    # Also include author ID and new user
    if 719932313919684670 not in user_ids and "719932313919684670" not in user_ids:
        user_ids.append(719932313919684670)
    user_ids.append(999999999999)

    print(f"Testing {len(user_ids)} users: {user_ids}")
    for uid in user_ids:
        print(f"--- Testing user_id {uid} ---")
        try:
            cards = await db.get_user_nba_cards(uid)
            print(f"User {uid} has {len(cards)} cards.")
            dt = await db.get_dream_team(uid)
            print(f"User {uid} dream_team row exists: {bool(dt)}")
            view = BuildTeamView(uid, cards)
            await view.initialize()
            print(f"BuildTeamView initialized. Picks: {list(view.picks.keys())}")
            u = discord.Object(id=int(uid))
            u.display_name = f"User_{uid}"
            emb = view.build_builder_embed(u)
            print(f"Embed built successfully: {emb.title.encode('ascii', 'ignore')}")
            print(f"Components count: {len(view.children)}")
            for pos in ["PG", "SG", "SF", "PF", "C"]:
                view.current_pos = pos
                view._update_components()
                for idx, c in enumerate(view.children):
                    if isinstance(c, discord.ui.Select):
                        vals = [opt.value for opt in c.options]
                        if len(vals) != len(set(vals)):
                            print(f"ERROR: Duplicate select option values in pos {pos} select #{idx}: {vals}")
                        default_count = sum(1 for opt in c.options if opt.default)
                        if default_count > 1:
                            print(f"ERROR: Multiple default=True options in pos {pos} select #{idx}: {default_count}")
                        for opt in c.options:
                            if len(opt.label) > 100:
                                print(f"ERROR: Label too long: {opt.label}")
                            if opt.description and len(opt.description) > 100:
                                print(f"ERROR: Description too long: {opt.description}")
            print(f"✅ User {uid} all 5 positions verified with 0 errors!")
        except Exception:
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_tests())
