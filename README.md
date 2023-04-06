# LLaMa telegram bot

![Logo](static/logo.png)

## Supported models

All models based on LLaMa and converted into GGML format, such as Alpaca, Vicuna, Gpt4All and others.

## How to set up

1. Place the model weight(ggml format) somewhere
2. Install requirements  
`pip install -r requirements.txt`
3. Run
`python main.py "TELEGRAM_BOT_TOKEN" -m PATH_TO_MODEL`
4. Enjoy

## How to tune

Prompt is tuned for [Vicuna](https://vicuna.lmsys.org/) model, but you can write your own in the text_generation function in main.py  
```prompt = f"### Human: {user_prompt}\n### Assistant:"```