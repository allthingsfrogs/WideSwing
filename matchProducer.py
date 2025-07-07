#!/usr/bin/env python

import logging
import sys
import requests
import json
import asyncio

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

from config import TOKEN, BOT_NAME

# Conversation state
CHOOSE_MATCH = 1
user_tasks = {}

# Fetch upcoming match data
def fetch_match_data():
    response = requests.get("https://vlrggapi.vercel.app/match?q=live_score")
    print(f"Fetching match data: {response.status_code}")
    logging.info(response.text)
    if response.status_code != 200:
        logging.error(f"Failed to fetch match data: {response.status_code}")
        return {"data": []}
    return response.json()

# Commands
# /start
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to WideSwing Bot!\nUse /live to follow a Valorant match.\nUse /stop to cancel tracking."
    )
# /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Use /live to follow a match. Use /stop to stop updates.")

# /stop command
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    task = user_tasks.get(chat_id)

    if task and not task.done():
        task.cancel()
        await update.message.reply_text("🛑 Stopped tracking the match.")
    else:
        await update.message.reply_text("You're not currently tracking any match.")

# /cancel command (ConversationHandler fallback)
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Match selection cancelled. ❌ ")
    return ConversationHandler.END

# /live → ask user to choose a match
async def live_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id in user_tasks:
        await update.message.reply_text("You're already tracking a match. Use /stop to cancel.")
        return ConversationHandler.END

    data = fetch_match_data()
    segments = get_valid_match_segments(data)

    if not segments:
        await update.message.reply_text("⚠️ No valid matches found.")
        return ConversationHandler.END

    context.user_data["match_list"] = segments

    message = "Which match would you like to follow?\n"
    for i, segment in enumerate(segments):
        t1 = segment["team1"]
        t2 = segment["team2"]
        message += f"{i + 1}. {t1} vs {t2}\n"

    await update.message.reply_text(message + "\nReply with the number of the match.")
    return CHOOSE_MATCH

# Extract and validate match segments from VLR API response
def get_valid_match_segments(api_data: dict, max_matches: int = 20) -> list:
    """
    Extracts and validates segments from the VLR API response.
    Returns a list of segment dictionaries with required fields.
    """
    segments = []

    data_container = api_data.get("data", {})
    if not isinstance(data_container, dict):
        logging.warning("Expected 'data' to be a dict, got: %s", type(data_container))
        return segments

    raw_segments = data_container.get("segments", [])
    if not isinstance(raw_segments, list):
        logging.warning("Expected 'segments' to be a list, got: %s", type(raw_segments))
        return segments

    for segment in raw_segments:
        if not isinstance(segment, dict):
            continue
        
        # Filter for VCT matches and ignores smaller/irrelevant events
        if all(k in segment and isinstance(segment[k], str) for k in ("team1", "team2", "match_event")):
            if "VCT" or "Esports World Cup" in segment["match_event"]:  # Case-sensitive match
                segments.append(segment)

        if len(segments) >= max_matches:
            break

    return segments

# User replies with match number
async def choose_match(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    matches = context.user_data.get("match_list", [])

    try:
        choice = int(update.message.text.strip()) - 1
        if choice < 0 or choice >= len(matches):
            raise ValueError
    except ValueError:
        await update.message.reply_text("Invalid choice. Please enter a valid number.")
        return CHOOSE_MATCH

    match_info = matches[choice]
    context.user_data["selected_match"] = match_info
    team1 = match_info["team1"]
    team2 = match_info["team2"]

    await update.message.reply_text(f"🔔 Tracking: {team1} vs {team2}")

    # Start async task
    task = context.application.create_task(live_match_tracker(chat_id, match_info, context))
    logging.info(f"Starting live tracker task for chat_id={chat_id} on match {team1} vs {team2}")
    user_tasks[chat_id] = task
    task.add_done_callback(lambda _: user_tasks.pop(chat_id, None))

    return ConversationHandler.END

# Background match tracker
async def live_match_tracker(chat_id, match_info, context: ContextTypes.DEFAULT_TYPE):
    last_t1_round_ct_score = None
    last_t1_round_t_score = None
    last_t2_round_ct_score = None
    last_t2_round_t_score = None
    last_t1_score = None
    last_t2_score = None   
    team1 = match_info["team1"]
    team2 = match_info["team2"]

    try:
        while True:
            data = fetch_match_data()
            all_segments = data.get("data", {}).get("segments", [])
            current = next((s for s in all_segments if s["team1"] == team1 and s["team2"] == team2), None)
            logging.info(f"Polling live match updates for {team1} vs {team2}")
            
            if current and current.get("time_until_match") == "LIVE":
                # Map Score
                t1_score = current.get("score1")
                t2_score = current.get("score2")
                # Round Scores
                t1_round_ct_score = current.get("team1_round_ct")
                t1_round_t_score = current.get("team1_round_t")
                t2_round_ct_score = current.get("team2_round_ct")
                t2_round_t_score = current.get("team2_round_t")
                map_count = current.get("map_number")
                logging.info(f"Current match state: {team1} {t1_score} - {t2_score} {team2} | Round CT: {t1_round_ct_score} T: {t1_round_t_score} | {team2} CT: {t2_round_ct_score} T: {t2_round_t_score}")

                if last_t1_round_t_score != t1_round_t_score or last_t2_round_ct_score != t2_round_ct_score or last_t1_round_ct_score != t1_round_ct_score or last_t2_round_t_score != t2_round_t_score:
                    last_t1_round_t_score = t1_round_t_score
                    last_t1_round_ct_score = t1_round_ct_score
                    last_t2_round_t_score = t2_round_t_score
                    last_t2_round_ct_score = t2_round_ct_score
                    logging.info(f"Round score update: {team1} CT: {t1_round_ct_score} T: {t1_round_t_score} | {team2} CT: {t2_round_ct_score} T: {t2_round_t_score}")

                    score_str = f" Map: {map_count} \n {team1} {t1_score} - {t2_score} {team2} \n {team1} CT: {last_t1_round_ct_score} T: {last_t1_round_t_score} \n {team2} CT: {last_t2_round_ct_score} T: {last_t2_round_t_score}"
                    await context.bot.send_message(chat_id=chat_id, text=f"🟢 Score Update:\n{score_str}")
            else:
                logging.info("Match not live or no longer found.")

            await asyncio.sleep(30)

    except asyncio.CancelledError:
        await context.bot.send_message(chat_id=chat_id, text="🛑 Stopped live match tracking.")
    except Exception as e:
        logging.error(f"Error in live_match_tracker: {e}", exc_info=True)
        await context.bot.send_message(chat_id=chat_id, text="❌ Tracker stopped due to error.")
    finally:
        # Remove task from user_tasks to avoid stale entries
        user_tasks.pop(chat_id, None)


# Generic message handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please use /live to start tracking or /help for info.")

# Error logger
async def error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logging.warning(f'Update "{update}" caused error "{context.error}"')


# Conversation handler setup
conv_handler = ConversationHandler(
    entry_points=[CommandHandler("live", live_command)],
    states={
        CHOOSE_MATCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, choose_match)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)

# Main app
def main():

    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stop", stop_command))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT, handle_message))
    app.add_error_handler(error)

    logging.info("Bot polling started...")
    app.run_polling(poll_interval=2)

if __name__ == "__main__":
    sys.exit(main())