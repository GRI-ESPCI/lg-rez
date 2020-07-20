import os
from dotenv import load_dotenv

from discord_webhook import DiscordWebhook

load_dotenv()
WEBHOOK_TP_URL = os.getenv("WEBHOOK_TP_URL")
WEBHOOK_SYNC_URL = os.getenv("WEBHOOK_SYNC_URL")
assert WEBHOOK_TP_URL, "webhook.py : WEBHOOK_TP_URL introuvable"
assert WEBHOOK_SYNC_URL, "webhook.py : WEBHOOK_SYNC_URL introuvable"

def send(message: str, source="tp"):
    """Appelle le webhook Discord de l'url <source> avec le message <message>.

    Raccourcis utilisables pour <source> :
        - "tp" ==> webhook Tâche planifiée (défini dans .env)
        - "sync" ==> webhook Synchronisation TDB (défini dans .env)
    """
    if source == "tp":
        url = WEBHOOK_TP_URL
    elif source == "sync":
        url = WEBHOOK_SYNC_URL
    else:
        url = source

    webhook = DiscordWebhook(url=url, content=message)
    response = webhook.execute()
    return response
