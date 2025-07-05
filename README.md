# WideSwing

Live Valorant Esports Updates via Telegram/SMS

#tentaive work flow:
Entry Point: /start on telegram WideSWing bot

    Bot prompts for match info, does polling for new match request

    once match is determined, passes this info to python producer

    Producer does polling on vlrggAPI for match updates

    When an update is detected
