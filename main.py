import json
import sys
import random
import logging
import argparse
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
parser.add_argument('--remember-history', action='store_true', help='Simulate memory in a chatbot')

args = parser.parse_args()

bot = telebot.TeleBot(args.token)
model = Path(args.model).resolve()
seed = random.randint(1, sys.maxsize)
llama = Llama(model_path=str(model), n_ctx=512, seed=seed, n_threads=args.threads)
historyDb = ChatHistoryDB("chat.db")
job_queue = queue.Queue()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info(f"Seed: {seed}")

init_prompt = "Below is an instruction that describes a task. Write a short response that appropriately completes the " \
              "request. Answer briefly but clearly.\n"
q_prompt = "### Human:"
a_prompt = "### Assistant:"


def process_job(job):
    def generate_text(user_prompt, max_tokens=args.max_token, stream=False, custom_prompt=False, chat_id=None,
                      history=args.remember_history):
        prompt = f"{init_prompt}\n{q_prompt} {user_prompt}\n{a_prompt}"
        if custom_prompt:
            prompt = user_prompt
        if history is True and chat_id is not None:
            prompt = get_last_messages(chat_id) + prompt

        logger.info(f"Generation for: {prompt}")

        if stream and max_tokens > 2048:
            logger.warning("This is likely to exceed 4096 characters, which would not fit into one stream message")

        json_obj = llama.create_completion(prompt, max_tokens=max_tokens, top_k=100, top_p=0.95, temperature=0.7,
                                           stream=stream, stop=["<|endoftext|>", "###", a_prompt, q_prompt])
        return json_obj

    user_prompt = job[0]
    chat_id = job[1]
    msg = job[2]
    custom_prompt = job[3]

    try:
        if custom_prompt:
            json_obj = generate_text(user_prompt, chat_id=chat_id, stream=False,
                                     custom_prompt=True)
        else:
            json_obj = generate_text(user_prompt, chat_id=chat_id, stream=False)
        output = json_obj['choices'][0]["text"]

        logger.debug(json.dumps(json_obj, indent=2))
        text_to_user = output

        send_by_chunks(msg, text_to_user)

        if args.remember_history:
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
            process_job(job)
            job_queue.task_done()
        except Exception as e:
            print(e)


def send_by_chunks(message, text, **kwargs):
    if len(text) < 5:
        logger.error("Message is empty or too short")
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

    msg = bot.reply_to(message, "Please wait a moment")
    bot.send_chat_action(chat_id=message.chat.id, action='typing')
    job_queue.put((user_prompt, message.chat.id, msg, True))


@bot.message_handler(func=lambda message: True)
def main(message):
    if message.text.startswith("/"):
        bot.reply_to(message, "Wrong command")
        return
    user_prompt = message.text
    msg = bot.reply_to(message, "Please wait a moment")
    bot.send_chat_action(chat_id=message.chat.id, action='typing')
    job_queue.put((user_prompt, message.chat.id, msg, False))
    logger.info("Added a new task from user: %s (%s)",  message.chat.username,  message.chat.id)


t = threading.Thread(target=process_queue)
t.daemon = True
t.start()

bot.infinity_polling()
