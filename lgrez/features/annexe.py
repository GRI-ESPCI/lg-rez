"""lg-rez / features / Commandes annexes

Commandes diverses qu'on ne savait pas où ranger

"""

import random
import requests
import datetime

from discord import app_commands
from akinator.async_aki import Akinator

from lgrez import config, commons
from lgrez.blocs import tools
from lgrez.blocs.journey import DiscordJourney, journey_command
from lgrez.bdd import Joueur, Role, Camp


DESCRIPTION = """Commandes annexes aux usages divers"""

next_roll = None


@app_commands.command()
@journey_command
async def roll(journey: DiscordJourney, *, pattern: str):
    """Lance un ou plusieurs dés, ou tire un nom dans un liste.

    Args:
        pattern: Dés à lancer (XdY [+ ...] [+ Z ...]) OU roll spécial (joueur / vivant / mort / rôle / camp).

    Examples:
        - ``/roll 1d6``           -> lance un dé à 6 faces
        - ``/roll 1d20 +3``       -> lance un dé à 20 faces, ajoute 3 au résultat
        - ``/roll 1d20 + 2d6 -8`` -> lance un dé 20 plus deux dés 6, enlève 8 au résultat
        - ``/roll vivant``        -> choisit un joueur vivant
    """
    global next_roll

    inp = pattern.lower()
    # Rolls spéciaux
    result = None
    if inp in ["joueur", "joueurs"]:
        result = random.choice(Joueur.query.all()).nom
    elif inp in ["vivant", "vivants"]:
        jr = random.choice(Joueur.query.filter(Joueur.est_vivant).all())
        result = jr.nom
    elif inp in ["mort", "morts"]:
        jr = random.choice(Joueur.query.filter(Joueur.est_mort).all())
        result = jr.nom
    elif inp in ["role", "rôle", "roles", "rôles"]:
        role = random.choice(Role.query.filter_by(actif=True).all())
        result = role.nom_complet
    elif inp in ["camp", "camps"]:
        result = random.choice(Camp.query.filter_by(public=True).all()).nom
    elif inp in ["ludo", "ludopathe"]:
        result = random.choice(["Voyante", "Marionnettiste", "Notaire", "Popo de mort", "Chat-garou", "Espion"])
    elif inp in ["taverne", "tavernier"]:
        result = random.choice(["Rôle choisi", "Vrai rôle", "Rôle random"])

    if result:
        if next_roll is not None:
            result = next_roll
            next_roll = None
        await journey.send(result)
        return

    parts = inp.replace(" ", "").replace("-", "+-").split("+")
    # "1d6 + 5 - 2" -> ["1d6", "5", "-2"]
    sum = 0
    rep = ""
    for part in parts:
        if not part:
            continue
        if "d" in part:
            # Lancer de dé
            nb, _, faces = part.partition("d")
            try:
                nb, faces = int(nb), int(faces)
                if faces < 1:
                    raise ValueError
            except ValueError:
                raise commons.UserInputError("pattern", f"Pattern de dé non reconnu : {part}")
            # Sécurité
            if abs(nb) > 1000 or faces > 1000000:
                await journey.send.send(
                    "Suite à des abus (coucou Gabin), il est "
                    "interdit de lancer plus de 1000 dés ou "
                    "des dés à plus de 1 million de faces."
                )
                return
            sig = -1 if nb < 0 else 1
            sig_s = "-" if nb < 0 else "+"
            for _ in range(abs(nb)):
                val = random.randrange(faces) + 1
                if next_roll is not None:
                    try:
                        val = int(next_roll)
                    except ValueError:
                        pass
                    else:
                        next_roll = None
                sum += sig * val
                rep += f" {sig_s} {val}₍{tools.sub_chiffre(faces, True)}₎"
        else:
            # Bonus / malus fixe
            try:
                val = int(part)
            except ValueError:
                raise commons.UserInputError("pattern", f"Pattern fixe non reconnu : {part}")
            sum += val
            rep += f" {'-' if val < 0 else '+'} {abs(val)}"
    # Total
    sig = "- " if sum < 0 else ""
    rep += f" = {sig}{tools.emoji_chiffre(abs(sum), True)}"
    rep = rep[3:] if rep.startswith(" +") else rep
    await journey.send(rep)


@app_commands.command()
@tools.mjs_only
@journey_command
async def nextroll(journey: DiscordJourney, *, next: str = None):
    """✨ Shhhhhhhhhhhh.

    Ça sent la magouilleuh
    """
    global next_roll
    next_roll = next
    await journey.send("🤫", ephemeral=True)


@journey_command
@app_commands.command()
async def coinflip(journey: DiscordJourney):
    """Pile ou face ?

    Pile je gagne, face tu perds.
    """
    await journey.send(random.choice(["Pile", "Face"]))


@app_commands.command()
@journey_command
async def ping(journey: DiscordJourney):
    """Envoie un ping au bot, pour vérifier si il est réactif tout ça.

    Pong
    """
    ts_rec = datetime.datetime.now(datetime.timezone.utc)
    delta_rec = ts_rec - journey.created_at
    # Temps de réception = temps entre création message et sa réception

    cont = f" Réception : {delta_rec.total_seconds()*1000:4.0f} ms\n Latence :   {config.bot.latency*1000:4.0f} ms\n"
    *_, mess = await journey.send(f"pong\n" + tools.code_bloc(cont + " (...)"))

    ts_ret = datetime.datetime.now(datetime.timezone.utc)
    delta_ret = ts_ret - mess.created_at
    # Retour information message réponse créé
    delta_env = ts_ret - ts_rec - delta_ret
    # Temps d'envoi = temps entre réception 1er message (traitement quasi instantané)
    # et création 2e, moins temps de retour d'information
    delta_tot = delta_rec + delta_ret + delta_env
    # Total = temps entre création message /pong et réception information réponse envoyée
    await mess.edit(
        content=f"/pong\n"
        + tools.code_bloc(
            cont + f" Envoi :     {delta_env.total_seconds()*1000:4.0f} ms\n"
            f" Retour :    {delta_ret.total_seconds()*1000:4.0f} ms\n"
            f"——————————————————————\n"
            f" Total :     {delta_tot.total_seconds()*1000:4.0f} ms"
        )
    )


@app_commands.command()
@journey_command
async def akinator(journey: DiscordJourney):
    """J'ai glissé chef

    Implémentation directe de https://pypi.org/project/akinator.py
    """
    # Un jour mettre ça dans des embeds avec les https://fr.akinator.com/
    # bundles/elokencesite/images/akitudes_670x1096/<akitude>.png croppées,
    # <akitude> in ["defi", "serein", "inspiration_legere",
    # "inspiration_forte", "confiant", "mobile", "leger_decouragement",
    # "vrai_decouragement", "deception", "triomphe"]
    await journey.send(
        "Vous avez demandé à être mis en relation avec "
        + tools.ital("Akinator : Le Génie du web")
        + ".\nVeuillez patienter..."
    )

    chan = journey.channel
    async with chan.typing():
        # Connexion
        aki = Akinator()
        question = await aki.start_game(language="fr")

    while aki.progression <= 80:
        reponse = await journey.buttons(
            f"({aki.step + 1}) {question}", {"yes": "👍", "idk": "🤷", "no": "👎", "stop": "⏭️"}
        )
        if reponse == "stop":
            break
        question = await aki.answer(reponse)

    await aki.win()

    if await journey.yes_no(
        f"Tu penses à {tools.bold(aki.first_guess['name'])} "
        f"({tools.ital(aki.first_guess['description'])}) !\n"
        f"J'ai bon ?\n{aki.first_guess['absolute_picture_path']}"
    ):
        await chan.send("Yay\nhttps://fr.akinator.com/bundles/elokencesite/images/akitudes_670x1096/triomphe.png")
    else:
        await chan.send("Oof\nhttps://fr.akinator.com/bundles/elokencesite/images/akitudes_670x1096/deception.png")


@app_commands.command()
@journey_command
async def xkcd(journey: DiscordJourney, num: int):
    """J'ai aussi glissé chef, mais un peu moins

    Args:
        num: Numéro de la planche à récupérer.
    """
    rep = requests.get(f"https://xkcd.com/{num}/info.0.json")

    if not rep:
        await journey.send(":x: Paramètre incorrect ou service non accessible.")
        return

    url = rep.json().get("img")
    if not url:
        await journey.send(":x: Paramètre incorrect ou service non accessible.")
        return

    await journey.send(url)
 
 
import asyncio
import os
import sys
import traceback
from typing import Literal

# Unused imports because useful for /do or /shell globals
import discord
from discord import app_commands

from lgrez import __version__, config, features, blocs, bdd, commands, commons
from lgrez.blocs import gsheets, tools, realshell
from lgrez.bdd import *  # toutes les tables dans globals()
from lgrez.blocs.journey import DiscordJourney, journey_command
    
@app_commands.command()
@journey_command
async def setup2(journey: DiscordJourney):
    """✨ Prépare un serveur nouvellement crée (COMMANDE MJ)

    À n'utiliser que dans un nouveau serveur, pour créer les rôles, catégories, salons et emojis nécessaires.
    """
    await journey.ok_cancel("Setup le serveur ?")

    original_channels = list(config.guild.channels)

    structure = config.server_structure

    # Création rôles
    await journey.send("Création des rôles...")
    roles = {}
    for slug, role in structure["roles"].items():
        roles[slug] = tools.role(role["name"], must_be_found=False)
        if roles[slug]:
            continue
        if isinstance(role["permissions"], list):
            perms = discord.Permissions(**{perm: True for perm in role["permissions"]})
        else:
            perms = getattr(discord.Permissions, role["permissions"])()
        roles[slug] = await config.guild.create_role(
            name=role["name"],
            color=int(role["color"], base=16),
            hoist=role["hoist"],
            mentionable=role["mentionable"],
            permissions=perms,
        )
    # Modification @everyone
    roles["@everyone"] = tools.role("@everyone")
    await roles["@everyone"].edit(
        permissions=discord.Permissions(**{perm: True for perm in structure["everyone_permissions"]})
    )
    await journey.send(f"{len(roles)} rôles créés.")

    # Assignation rôles
    for member in config.guild.members:
        await member.add_roles(roles["bot"] if member == config.bot.user else roles["mj"])

    # Création catégories et channels
    await journey.send("Création des salons...")
    categs = {}
    channels = {}
    for slug, categ in structure["categories"].items():
        categs[slug] = tools.channel(categ["name"], must_be_found=False)
        if not categs[slug]:
            categs[slug] = await config.guild.create_category(
                name=categ["name"],
                overwrites={
                    roles[role]: discord.PermissionOverwrite(**perms) for role, perms in categ["overwrites"].items()
                },
            )
        for position, (chan_slug, channel) in enumerate(categ["channels"].items()):
            channels[chan_slug] = tools.channel(channel["name"], must_be_found=False)
            if channels[chan_slug]:
                continue
            channels[chan_slug] = await categs[slug].create_text_channel(
                name=channel["name"],
                topic=channel["topic"],
                position=position,
                overwrites={
                    roles[role]: discord.PermissionOverwrite(**perms) for role, perms in channel["overwrites"].items()
                },
            )
        for position, (chan_slug, channel) in enumerate(categ["voice_channels"].items()):
            channels[chan_slug] = tools.channel(channel["name"], must_be_found=False)
            if channels[chan_slug]:
                continue
            channels[chan_slug] = await categs[slug].create_voice_channel(
                name=channel["name"],
                position=position,
                overwrites={roles[role]: discord.PermissionOverwrite(**perms) for role, perms in channel["overwrites"]},
            )
    await journey.send(f"{len(channels)} salons créés dans {len(categs)} catégories.")

    # Création emojis
    await journey.send("Import des emojis... (oui c'est très long)")

    async def _create_emoji(name: str, data: bytes):
        can_use = None
        if restrict := structure["emojis"]["restrict_roles"].get(name):
            can_use = [roles[role] for role in restrict]
        await config.guild.create_custom_emoji(
            name=name,
            image=data,
            roles=can_use,
        )

    n_emojis = 0
    if structure["emojis"]["drive"]:
        folder_id = structure["emojis"]["folder_path_or_id"]
        for file in gsheets.get_files_in_folder(folder_id):
            if file["extension"] != "png":
                continue
            name = file["name"].removesuffix(".png")
            if tools.emoji(name, must_be_found=False):
                continue
            data = gsheets.download_file(file["file_id"])
            await _create_emoji(name, data)
            n_emojis += 1
    else:
        root = structure["emojis"]["folder_path_or_id"]
        for file in os.scandir(root):
            name, extension = os.path.splitext(file.name)
            if extension != ".png":
                continue
            if tools.emoji(name, must_be_found=False):
                continue
            with open(file.path, "rb") as fh:
                data = fh.read()
            await _create_emoji(name, data)
            n_emojis += 1
    await journey.send(f"{n_emojis} emojis importés.")

    # Paramètres généraux du serveur
    await journey.send("Configuration du serveur...")
    if not structure["icon"]:
        icon_data = None
    elif structure["icon"]["drive"]:
        file_id = structure["icon"]["png_path_or_id"]
        icon_data = gsheets.download_file(file_id)
    else:
        with open(structure["icon"]["png_path_or_id"], "rb") as fh:
            icon_data = fh.read()

    await config.guild.edit(
        name=structure["name"],
        icon=icon_data,
        afk_channel=channels.get(structure["afk_channel"]),
        afk_timeout=int(structure["afk_timeout"]),
        verification_level=discord.VerificationLevel[structure["verification_level"]],
        default_notifications=discord.NotificationLevel[structure["default_notifications"]],
        explicit_content_filter=discord.ContentFilter[structure["explicit_content_filter"]],
        system_channel=channels[structure["system_channel"]],
        system_channel_flags=discord.SystemChannelFlags(**structure["system_channel_flags"]),
        preferred_locale=structure["preferred_locale"],
        reason="Guild set up!",
    )
    await journey.send(f"Fin de la configuration !")

    config.is_setup = True

    # Delete current chan (will also trigger on_ready)
    await journey.yes_no("Terminé ! Ce salon va être détruit (ce n'est pas une question).")
    for channel in original_channels:
        await channel.delete()

