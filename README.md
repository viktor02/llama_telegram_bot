# LLaMa telegram bot

![Logo](static/logo.png)

## Supported models

All models based on LLaMa and converted into the latest GGML format, such as Alpaca, Vicuna, Gpt4All and others.

## How to set up

1. Place the model weight(ggml format) somewhere
2. Install requirements  
`pip install -r requirements.txt`
3. Run
`python main.py "TELEGRAM_BOT_TOKEN" -m PATH_TO_MODEL`
4. Enjoy

## Usage
```commandline
LLaMa telegram bot

positional arguments:
  token                 Telegram bot token

options:
  -h, --help            show this help message and exit
  -m MODEL, --model MODEL
                        Path to the LLaMa model
  -t THREADS, --threads THREADS
                        Number of threads to use
  --max-token MAX_TOKEN
                        The maximum number of tokens to generate
  --remember-history    Simulate memory in a chatbot
```



## How to tune

Prompt is tuned for [Vicuna](https://vicuna.lmsys.org/) model, but you can write your own in the `init_prompt` and `a/q_prompt` variables in main.py. 

Example:  
```python
init_prompt = "Below is an instruction that describes a task. Write a short response that appropriately completes the " \
              "request. Answer briefly but clearly.\n"
q_prompt = "### Human:"
a_prompt = "### Assistant:"

user_prompt = "What is the task you need to complete?"  # This is the prompt that the user sends to bot

prompt = f"{init_prompt}\n{q_prompt} {user_prompt}\n{a_prompt}"  # Final prompt to be passed on to the model
```