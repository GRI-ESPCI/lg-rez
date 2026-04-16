"""lg-rez / features / Nécromancien

Gestion de la déclaration des alliés des Nécromanciens en début de partie.

"""

import json
import os

from discord import app_commands

from lgrez.blocs import tools
from lgrez.blocs.journey import DiscordJourney, journey_command
from lgrez.bdd import Joueur
from typing import Literal


DESCRIPTION = """Commandes de gestion des alliés Nécromanciens"""

import os as _os
_ALLIES_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "allies_necromancien.json")

# Dictionnaire {discord_id (str) -> nom_allie (str)}, persisté dans _ALLIES_FILE


def _load_allies() -> dict[str, str]:
    if os.path.exists(_ALLIES_FILE):
        with open(_ALLIES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_allies(allies: dict[str, str]) -> None:
    with open(_ALLIES_FILE, "w", encoding="utf-8") as f:
        json.dump(allies, f, ensure_ascii=False, indent=2)


def reset_allies() -> None:
    """Remet à zéro le fichier de sauvegarde des alliés.

    À appeler entre deux parties, notamment depuis la commande ``/setup``.
    """
    _save_allies({})


@app_commands.command()
@tools.vivants_only
@tools.private()
@journey_command
async def allie(journey: DiscordJourney, *, nom: str):
    """Déclare (ou modifie) le nom de ton allié en tant que Nécromancien.

    Args:
        nom: Le prénom (et nom) de la personne que tu souhaites avoir comme allié.

    Le nom n'a pas besoin d'être celui d'un joueur déjà inscrit sur le serveur.
    Tu peux modifier ton choix autant de fois que tu le souhaites avant l'attribution des rôles.
    """
    joueur = Joueur.from_member(journey.member)
    allies = _load_allies()
    key = str(joueur.discord_id)

    if key in allies:
        ancien_nom = allies[key]
        if not await journey.yes_no(
            f"Tu avais déjà indiqué **{ancien_nom}** comme allié.\n"
            f"Veux-tu le remplacer par **{nom}** ?"
        ):
            await journey.send(f"Pas de changement, ton allié reste **{ancien_nom}**.")
            return
        allies[key] = nom
        _save_allies(allies)
        await journey.send(
            f"Ton allié a bien été mis à jour : **{ancien_nom}** → **{nom}**.\n"
            + tools.ital("Tu peux modifier ce choix à tout moment avant l'attribution des rôles.")
        )
        await tools.log(f"[Nécromancien] {joueur.nom} a changé son allié : {ancien_nom} → {nom}")
    else:
        allies[key] = nom
        _save_allies(allies)
        await journey.send(
            f"Ton allié a bien été enregistré : **{nom}**.\n"
            + tools.ital("Tu peux modifier ce choix à tout moment avant l'attribution des rôles avec `/allie`.")
        )
        await tools.log(f"[Nécromancien] {joueur.nom} a déclaré son allié : {nom}")


@app_commands.command()
@tools.mjs_only
@journey_command
async def allie_liste(journey: DiscordJourney):
    """Affiche la liste de tous les alliés déclarés par les joueurs. (COMMANDE MJ)

    Indique également les joueurs vivants n'ayant pas encore déclaré d'allié.
    """
    allies = _load_allies()
    joueurs_vivants = Joueur.query.filter(Joueur.est_vivant).order_by(Joueur.nom).all()

    lignes_declares = []
    lignes_non_declares = []

    for joueur in joueurs_vivants:
        if str(joueur.discord_id) in allies:
            lignes_declares.append(f" {joueur.nom.ljust(25)} → {allies[str(joueur.discord_id)]}")
        else:
            lignes_non_declares.append(f" {joueur.nom}")

    rep = f"Alliés déclarés ({len(lignes_declares)}) :\n"
    rep += "\n".join(lignes_declares) if lignes_declares else "  (aucun)"
    rep += f"\n\nJoueurs sans allié déclaré ({len(lignes_non_declares)}) :\n"
    rep += "\n".join(lignes_non_declares) if lignes_non_declares else "  (tous ont déclaré un allié)"

    await journey.send(rep, code=True)


@app_commands.command()
@tools.mjs_only
@journey_command
async def allie_rappel(journey: DiscordJourney, *, cibles: Literal["tous", "non_declares"] = "non_declares"):
    """Envoie un rappel à tous les joueurs vivants pour qu'ils déclarent leur allié. (COMMANDE MJ)
    Par défaut le rappel ne concerne que les joueurs ne l'ayant pas fait, précisé tous si besoin

    Le message rappelle ce qui a déjà été déclaré si le joueur a déjà renseigné un allié,
    ou demande de le faire sinon.
    """
    allies = _load_allies()
    joueurs = Joueur.query.filter(Joueur.est_vivant).all()
    nombre = len(joueurs)

    for joueur in joueurs:
            chan = joueur.private_chan
            a_declare = str(joueur.discord_id) in allies

            if cibles == "non_declares":
                if a_declare:
                    nombre = nombre -1
                    continue
                await chan.send(
                    f"{joueur.member.mention} 🔔 Les MJs te demandent d'indiquer le nom de ton allié "
                    f"Nécromancien (au cas où tu serais Nécromancien !).\n"
                    + tools.ital(
                        "Utilise `/allie <nom>` pour indiquer un prénom (et nom). "
                        "Le joueur n'a pas besoin d'être déjà inscrit sur le serveur."
                    )
                )
            else:  # "tous"
                if a_declare:
                    await chan.send(
                        f"{joueur.member.mention} 🔔 Rappel : tu as déclaré **{allies[str(joueur.discord_id)]}** "
                        f"comme allié Nécromancien.\n"
                        + tools.ital("Si tu souhaites modifier ce choix, utilise `/allie <nom>`.")
                    )
                else:
                    await chan.send(
                        f"{joueur.member.mention} 🔔 Les MJs te demandent d'indiquer le nom de ton allié "
                        f"Nécromancien (au cas où tu serais Nécromancien !).\n"
                        + tools.ital(
                            "Utilise `/allie <nom>` pour indiquer un prénom (et nom). "
                            "Le joueur n'a pas besoin d'être déjà inscrit sur le serveur."
                        )
                    )

    await journey.send(f"Fait")
    await tools.log(f"Rappel envoyé à {nombre} joueurs.")


@app_commands.command()
@tools.mjs_only
@journey_command
async def allie_modif(journey: DiscordJourney,*,joueur: app_commands.Transform[Joueur, tools.VivantTransformer],nom: str,):
    """Modifie l'allié déclaré d'un joueur (COMMANDE MJ)

    Args:
        joueur: Le joueur dont on veut modifier l'allié déclaré.
        nom: Le nouveau nom de l'allié.
    """
    allies = _load_allies()
    key = str(joueur.discord_id)

    if key in allies:
        ancien = allies[key]
        allies[key] = nom
        _save_allies(allies)
        await journey.send(f"Allié de {joueur.nom} modifié : **{ancien}** → **{nom}**.")
        await tools.log(f"[Nécromancien] Un MJ a modifié l'allié de {joueur.nom} : {ancien} → {nom}")
    else:
        allies[key] = nom
        _save_allies(allies)
        await journey.send(f"Allié de {joueur.nom} enregistré : **{nom}**.")
        await tools.log(f"[Nécromancien] Un MJ a enregistré l'allié de {joueur.nom} : {nom}")
