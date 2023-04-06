import json
import sys
import random
import logging
import argparse
from pathlib import Path

from llama_cpp import Llama
import telebot

parser = argparse.ArgumentParser(description='Example argument parser')
parser.add_argument('token', help='Telegram bot token')
parser.add_argument('-m', '--model', default="ggml-model-q4_0.bin", help='Path to the LLaMa model')
parser.add_argument('--max-token', default=128, type=int, help='The maximum number of tokens to generate')

args = parser.parse_args()

bot = telebot.TeleBot(args.token)
model = Path(args.model).resolve()

llama = Llama(model_path=str(model), seed=random.randint(1, sys.maxsize))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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


def generate_text(user_prompt, max_tokens=args.max_token, stream=False):
    prompt = f"### Human: {user_prompt}\n### Assistant:"
    logger.info(f"Generation for text: {user_prompt}")

    if stream and max_tokens > 4096:
        logger.warning("This is likely to exceed 4096 characters, which would not fit into one stream message")

    json_obj = llama.create_completion(prompt, max_tokens=max_tokens, top_p=0.1, top_k=40, temperature=0.7,
                                        stream=stream, stop=["### Human:"])
    return json_obj


@bot.message_handler(commands=['start'])
def start_command(message):
    bot.reply_to(message, "Hello.")


@bot.message_handler(commands=['nostream'])
def stream_command(message):
    user_prompt = message.text
    bot.reply_to(message, "Please wait a moment")
    bot.send_chat_action(chat_id=message.chat.id, action='typing')
    try:
        json_obj = generate_text(user_prompt, max_tokens=256, stream=False)
        output = json_obj['choices'][0]["text"]

        logger.debug(json.dumps(json_obj, indent=2))
        text_to_user = output

        send_by_chunks(bot, message, text_to_user)
    except OSError as e:
        bot.reply_to(message, f"OSError: {e}")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")


@bot.message_handler(func=lambda message: True)
def handle_message(message):
    """ Streamed generation """
    user_prompt = message.text
    try:
        message_id = bot.reply_to(message, "Waiting for text...").message_id
        bot.send_chat_action(chat_id=message.chat.id, action='typing')

        stream = generate_text(user_prompt, stream=True)
        output = ""
        for j in stream:
            logger.debug(json.dumps(j, indent=2))
            # if len(output) > 4000:
            #     message_id = bot.reply_to(message, "Next part")
            #     output = ""

            try:
                if output != j["choices"][0]["text"]:
                    output += j["choices"][0]["text"]
                    bot.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=output)
            except telebot.apihelper.ApiTelegramException as e:
                pass
        logger.info(output)
        bot.edit_message_text(chat_id=message.chat.id, message_id=message_id, text=output)
    except OSError as e:
        bot.reply_to(message, f"OSError: {e}")


bot.infinity_polling()
