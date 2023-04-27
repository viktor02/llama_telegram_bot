import json
import sys
import random
import logging
import argparse
import time
from pathlib import Path
import queue
import threading

from llama_cpp import Llama
import telebot
from telebot import types

from db import ChatHistoryDB

parser = argparse.ArgumentParser(description='LLaMa telegram bot')
parser.add_argument('token', help='Telegram bot token')
parser.add_argument('-m', '--model', default="ggml-model-q4_0.bin", help='Path to the LLaMa model')
parser.add_argument('-t', '--threads', default=4, type=int, help='Number of threads to use')
parser.add_argument('--max-token', default=128, type=int, help='The maximum number of tokens to generate')
parser.add_argument('--enable-history', action='store_true', help='Simulate memory in a chatbot')
parser.add_argument('--skip-init-prompt', action='store_true', help='Skip the initial prompt (faster startup)')
parser.add_argument('--debug', action='store_true', help='Enable debug logging')

args = parser.parse_args()

bot = telebot.TeleBot(args.token)
model = Path(args.model).resolve()
seed = random.randint(1, sys.maxsize)
llama = Llama(model_path=str(model), n_ctx=512, seed=seed, n_threads=args.threads, verbose=args.debug)
historyDb = ChatHistoryDB("chat.db")
job_queue = queue.Queue()

log_level = logging.DEBUG if args.debug else logging.INFO
log_format = '%(asctime)s [%(levelname)s] %(message)s'
date_format = '%Y-%m-%d %H:%M:%S'

logging.basicConfig(level=log_level, format=log_format, datefmt=date_format)
logger = logging.getLogger(__name__)

init_prompt = "Below is an instruction that describes a task. Write a short response that appropriately completes the " \
              "request."
q_prompt = "### Instruction:"
a_prompt = "### Response:"


def process_job(job):
    def generate_text(user_prompt, max_tokens=args.max_token, stream=False, custom_prompt=False, chat_id=None,
                      history=args.enable_history):
        if args.skip_init_prompt:
            prompt = f"{q_prompt} {user_prompt}\n{a_prompt}"
        else:
            prompt = f"{init_prompt}\n{q_prompt} {user_prompt}\n{a_prompt}"
        if custom_prompt:
            prompt = user_prompt
        if history and chat_id:
            prompt = get_last_messages(chat_id) + prompt

        logger.debug(f"Generation for: {prompt}")

        if stream and max_tokens > 2048:
            logger.warning("This is likely to exceed 4096 characters, which would not fit into one stream message")

        return llama.create_completion(prompt, max_tokens=max_tokens, top_k=100, top_p=0.95, temperature=0.7,
                                           stream=stream, stop=["<|endoftext|>", "###", a_prompt, q_prompt])

    user_prompt = job[0]
    chat_id = job[1]
    msg = job[2]
    custom_prompt = job[3]

    try:
        bot.edit_message_text(chat_id=msg.chat.id, text="Started to generate text for you...",
                              message_id=msg.message_id)
        logger.info(f"Generating text for user {msg.chat.username}")

        if custom_prompt:
            json_obj = generate_text(user_prompt, chat_id=chat_id, stream=False,
                                     custom_prompt=True)
        else:
            json_obj = generate_text(user_prompt, chat_id=chat_id, stream=False)
        output = json_obj['choices'][0]["text"]

        logger.debug(json.dumps(json_obj, indent=2))
        text_to_user = output

        send_by_chunks(msg, text_to_user)
        logger.info(f"Sent to user {msg.chat.username}: {text_to_user}")

        if args.enable_history:
            historyDb.insert_message(chat_id, user_prompt, output)
        bot.delete_message(msg.chat.id, msg.message_id)  # delete 'please wait a moment'
    except OSError as e:
        bot.reply_to(msg, f"OSError: {e}")
    except Exception as e:
        bot.reply_to(msg, f"Error: {e}")


def process_queue():
    while True:
        try:
            job = job_queue.get()
            start_time = time.time()
            process_job(job)
            end_time = time.time()
            elapsed_time = end_time - start_time
            logger.info(f"Job processed in {elapsed_time:02f} seconds")
            job_queue.task_done()
        except Exception as e:
            logger.error(f"Error: {e}")


def send_by_chunks(message, text, **kwargs):
    if len(text) < 5:
        logger.error("Message is empty or too short")
    if len(text) <= 4096:
        bot.send_message(message.chat.id, text, **kwargs)
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
    for user_prompt, answer in messages:
        history += f"{q_prompt} {user_prompt}\n {a_prompt} {answer}\n"
    return history


@bot.message_handler(commands=['history'])
def history_command(message):
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
    bot.send_message(call.message.chat.id, "Chat history successfully forgotten")


@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    bot.reply_to(message, "Hello. This is chatGPT bot based on LLaMa.\nUsage:"
                          "\n\n<text> - Q&A mode.\n"
                          "/raw <prompt> - Use your own prompt.\n"
                          "/history - show history and delete it\n\n"
                          f"Current model: {model.name}")


@bot.message_handler(commands=['raw'])
def raw_command(message):
    user_prompt = message.text.replace("/raw ", '', 1)

    msg = bot.reply_to(message, f"Please wait a moment. Current queue: {job_queue.qsize()}")
    bot.send_chat_action(chat_id=message.chat.id, action='typing')
    job_queue.put((user_prompt, message.chat.id, msg, True))


@bot.message_handler(func=lambda message: True)
def main(message):
    if message.text.startswith("/"):
        bot.reply_to(message, "Wrong command")
        return
    user_prompt = message.text
    msg = bot.reply_to(message, f"Please wait a moment. Current queue: {job_queue.qsize()}")
    bot.send_chat_action(chat_id=message.chat.id, action='typing')
    job_queue.put((user_prompt, message.chat.id, msg, False))
    logger.info("Added a new task from user: %s (%s), text: %s",  message.chat.username,  message.chat.id, user_prompt)


t = threading.Thread(target=process_queue)
t.daemon = True
t.start()

bot.infinity_polling()
