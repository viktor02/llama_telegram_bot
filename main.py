import json
import sys
import random
import logging
import argparse
import time
from pathlib import Path

from llama_cpp import Llama
import telebot
from telebot import types

from db import ChatHistoryDB

parser = argparse.ArgumentParser(description='Example argument parser')
parser.add_argument('token', help='Telegram bot token')
parser.add_argument('-m', '--model', default="ggml-model-q4_0.bin", help='Path to the LLaMa model')
parser.add_argument('--max-token', default=128, type=int, help='The maximum number of tokens to generate')

args = parser.parse_args()

bot = telebot.TeleBot(args.token)
model = Path(args.model).resolve()
seed = random.randint(1, sys.maxsize)
llama = Llama(model_path=str(model), seed=seed)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"Seed: {seed}")

historyDb = ChatHistoryDB("chat.db")


def send_by_chunks(bot, message, text, **kwargs):
    if len(text) <= 4096:
        bot.reply_to(message, text, **kwargs)
    else:
        chunks = []
        while len(text) > 0:
            chunk = text[:4096]
            chunks.append(chunk)
            text = text[4096:]
        for chunk in chunks:
            bot.reply_to(message, chunk, **kwargs)


def get_last_messages(chat_id):
    messages = historyDb.get_chat_messages(chat_id)
    history = ""
    for msg in reversed(messages):
        user_prompt, answer = msg
        history += f"### Human: {user_prompt}\n### Assistant: {answer}\n"
    return history


def generate_text(user_prompt, max_tokens=args.max_token, stream=False, custom_prompt=None, chat_id=None,
                  history=False):
    prompt = f"### Human: {user_prompt}\n### Assistant:"
    if custom_prompt is not None:
        prompt = custom_prompt
    if history is True:
        prompt = get_last_messages(chat_id) + prompt

    logger.info(f"Generation for text: {user_prompt}")

    if stream and max_tokens > 4096:
        logger.warning("This is likely to exceed 4096 characters, which would not fit into one stream message")

    json_obj = llama.create_completion(prompt, max_tokens=max_tokens, top_k=10, top_p=0.75, temperature=0.7,
                                       stream=stream, stop=["### Human:"])
    return json_obj


@bot.message_handler(commands=['history'])
def start(message):
    keyboard = types.InlineKeyboardMarkup()
    button = types.InlineKeyboardButton(text="Delete history", callback_data="remove_history")
    keyboard.add(button)
    history = get_last_messages(message.chat.id)
    if history == "":
        history = "You have no history with the bot"
    bot.send_message(message.chat.id, text=history, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data == 'remove_history')
def send_message_callback(call):
    historyDb.delete_all_history(call.message.chat.id)
    bot.send_message(call.message.chat.id, "History deleted succesfully")


@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, "Hello.")


@bot.message_handler(commands=['raw'])
def stream_command(message):
    user_prompt = message.text.replace("/raw ", '', 1)

    bot.reply_to(message, "Please wait a moment")
    bot.send_chat_action(chat_id=message.chat.id, action='typing')
    try:
        json_obj = generate_text(user_prompt, max_tokens=256, stream=False, custom_prompt=user_prompt)
        output = json_obj['choices'][0]["text"]

        logger.debug(json.dumps(json_obj, indent=2))
        text_to_user = output

        send_by_chunks(bot, message, text_to_user)
    except OSError as e:
        bot.reply_to(message, f"OSError: {e}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")


@bot.message_handler(commands=['nostream'])
def stream_command(message):
    user_prompt = message.text.replace("/nostream ", '', 1)
    bot.reply_to(message, "Please wait a moment")
    bot.send_chat_action(chat_id=message.chat.id, action='typing')
    try:
        json_obj = generate_text(user_prompt, max_tokens=256, stream=False)
        output = json_obj['choices'][0]["text"]

        logger.debug(json.dumps(json_obj, indent=2))
        text_to_user = output

        send_by_chunks(bot, message, text_to_user)
        historyDb.insert_message(message.chat.id, user_prompt, output)
    except OSError as e:
        bot.reply_to(message, f"OSError: {e}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """ Streamed generation """
    user_prompt = message.text
    restricted_chars = ["", " ", "\n"]
    try:
        msg = bot.reply_to(message, "Please wait a moment")
        bot.send_chat_action(chat_id=message.chat.id, action='typing')

        stream = generate_text(user_prompt, stream=True, chat_id=message.chat.id, history=True)
        output_buffer = ""

        last_send_time = time.time()
        send_interval = 2  # Every 2 seconds send message
        for json_obj in stream:
            logger.info(json.dumps(json_obj, indent=2))
            output_buffer += json_obj['choices'][0]["text"]
            if time.time() - last_send_time > send_interval or json_obj['choices'][0]["text"] in restricted_chars:
                # fixed the 429 error from telegram - too fast editing
                bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=output_buffer)
                last_send_time = time.time()
            if len(output_buffer) > 4000:
                # send a new message and clean buffer
                msg = bot.reply_to(message, "Next part")
                output_buffer = ""
        try:
            msg = bot.edit_message_text(chat_id=message.chat.id, message_id=msg.message_id, text=output_buffer)
        except telebot.apihelper.ApiTelegramException:
            pass
        historyDb.insert_message(message.chat.id, user_prompt, output_buffer)
        logger.info(output_buffer)

    except OSError as e:
        bot.reply_to(message, f"OSError: {e}")


bot.infinity_polling()
