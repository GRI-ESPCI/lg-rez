"""lg-rez / blocs / Outils divers et variés

Récupération d'objets Discord, décorateurs pour commandes, structures
d'interaction dans les channels, utilitaires d'emojis, de date/temps,
de formatage...

"""

from __future__ import annotations

import asyncio
import datetime
import re
import string
import typing
from typing import Any, Callable

import discord
import discord.utils
from discord import app_commands
import unidecode

from lgrez import config, bdd, commons
from lgrez.bdd import Camp, CandidHaro, CandidHaroType, Joueur, Role


# ---------------------------------------------------------------------------
# Utilitaires de récupération d'objets Discord (détectent les mentions)
# ---------------------------------------------------------------------------


def _get(collec, **attrs):
    for elem in collec:
        if all(getattr(elem, attr) == value for attr, value in attrs.items()):
            return elem
    return None


_T = typing.TypeVar("_T")


def _find_by_mention_or_name(
    collec: typing.Collection[_T],
    val: str,
    pattern: str | None = None,
    must_be_found: bool = False,
    raiser: str | None = None,
) -> _T | None:
    """Utilitaire pour la suite : trouve un élément dans une liste.

    Args:
        collection: liste d'éléments.
        val: nom de l'élément à trouver, correspondant à son attribut
            ``name`` ou respectant une regex.
        pattern: motif regex à utiliser pour la recherche, si besoin.
        must_be_found: Si ``True``, raise une :exc:`ValueError` si
            ``val`` est introuvable.
        raiser: nom de la fonction à envoyer dans l'exception si
            introuvable (défaut : cette fonction).

    Returns:
        L'élément recherché, si on l'a trouvé.

    Raises:
        ValueError: Si ``must_be_found`` est ``True`` et que l'élément
            n'a pas été trouvé.
    """
    if not val:
        item = None
    elif pattern and (match := re.search(pattern, val)):
        item = _get(collec, id=int(match.group(1)))
    else:
        item = _get(collec, name=val)

    if must_be_found and not item:
        if raiser is None:
            raiser = "tools._find_by_mention_or_name"
        raise ValueError(f"{raiser} : Élément '{val}' introuvable")

    return item


@typing.overload
def channel(nom: str, must_be_found: typing.Literal[True] = True) -> discord.TextChannel | discord.CategoryChannel:
    ...


@typing.overload
def channel(nom: str, must_be_found: typing.Literal[False]) -> discord.TextChannel | discord.CategoryChannel | None:
    ...


def channel(nom, must_be_found=True):
    """Renvoie l'objet associé au salon ``#nom``.

    Args:
        nom: nom du channel (texte/vocal/catégorie) ou sa
            mention (détection directe par regex)
        must_be_found: si ``True`` (défaut), raise une
            :exc:`ValueError` si le channel ``#nom`` n'existe pas
            (si ``False``, renvoie ``None``)

    Returns:
        Le salon ou la catégorie Discord correspondant.
    """
    return _find_by_mention_or_name(
        config.guild.channels, nom, pattern="<#([0-9]{18})>", must_be_found=must_be_found, raiser="tools.channel"
    )


@typing.overload
def role(nom: str, must_be_found: typing.Literal[True] = True) -> discord.Role:
    ...


@typing.overload
def role(nom: str, must_be_found: typing.Literal[False] = True) -> discord.Role | None:
    ...


def role(nom, must_be_found=True):
    """Renvoie l'objet associé au rôle ``@&nom``.

    Args:
        nom: nom du rôle ou sa mention
            (détection directe par regex)
        must_be_found: si ``True`` (défaut), raise une
            :exc:`ValueError` si le channel ``@&nom`` n'existe pas
            (si ``False``, renvoie ``None``)

    Returns:
        Le rôle Discord correspondant.
    """
    return _find_by_mention_or_name(
        config.guild.roles, nom, pattern="<@&([0-9]{18})>", must_be_found=must_be_found, raiser="tools.role"
    )


@typing.overload
def member(nom: str, must_be_found: typing.Literal[True] = True) -> discord.Member:
    ...


@typing.overload
def member(nom: str, must_be_found: typing.Literal[False] = True) -> discord.Member | None:
    ...


def member(nom, must_be_found=True):
    """Renvoie l'objet associé au membre ``@nom``.

    Args:
        nom: nom du joueur ou sa mention
            (détection directe par regex)
        must_be_found: si ``True`` (défaut),
            raise une :exc:`ValueError` si le membre ``@nom`` n'existe pas
            (si ``False``, renvoie ``None``)

    Returns:
        Le membre Discord correspondant.
    """
    return _find_by_mention_or_name(
        config.guild.members, nom, pattern="<@!([0-9]{18})>", must_be_found=must_be_found, raiser="tools.member"
    )


@typing.overload
def emoji(nom: str, must_be_found: typing.Literal[True] = True) -> discord.Emoji:
    ...


@typing.overload
def emoji(nom: str, must_be_found: typing.Literal[False] = True) -> discord.Emoji | None:
    ...


def emoji(nom, must_be_found=True):
    """Renvoie l'objet associé à l'emoji ``:nom:``.

    Args:
        nom: nom de l'emoji (texte/vocal/catégorie)
            ou son utilisation (détection directe par regex)
        must_be_found: si ``True`` (défaut), raise une
            :exc:`ValueError` si l'emoji ``:nom:`` n'existe pas
            (si ``False``, renvoie ``None``)

    Returns:
        L'emoji Discord correspondant.
    """
    return _find_by_mention_or_name(
        config.guild.emojis, nom, pattern="<:.*:([0-9]{18})>", must_be_found=must_be_found, raiser="tools.emoji"
    )


# Appel aux MJs
def mention_MJ(arg: discord.Member | discord.Interaction) -> str:
    """Renvoie la mention ou le nom du rôle MJ

        - Si le joueur n'est pas un MJ, renvoie la mention de
          :attr:`config.Role.mj`
        - Sinon, renvoie son nom (pour ne pas rameuter tout le monde).

    Args:
        arg: Le membre ou le contexte d'un message envoyé par un membre.

    Returns:
        La chaîne à utiliser pour mentionner le rôle MJ.
    """
    member = arg.user if isinstance(arg, discord.Interaction) else arg
    if config.is_setup and isinstance(member, discord.Member) and member.top_role == config.Role.mj:
        # Pas un webhook et (au moins) MJ
        return f"@{config.Role.mj.name}"
    else:
        return config.Role.mj.mention


# ---------------------------------------------------------------------------
# Décorateurs pour les différentes commandes, en fonction de leur usage
# ---------------------------------------------------------------------------


def mjs_only(callback):
    """Décorateur pour commande (:func:`discord.app_commands.check`)

    Commande exécutable uniquement par un :attr:`MJ <.config.Role.mj>`
    ou un webhook (tâche planifiée)
    """
    return app_commands.checks.has_role(config.Role.get_raw("mj"))(
        app_commands.default_permissions(manage_messages=True)(callback)
    )


def mjs_et_redacteurs(callback):
    """Décorateur pour commandes d'IA (:func:`discord.app_commands.check`)

    commande exécutable par un :attr:`MJ <.config.Role.mj>`, un
    :attr:`Rédacteur <.config.Role.redacteur>` ou un webhook (tâche planifiée)
    """
    return app_commands.checks.has_any_role(config.Role.get_raw("mj"), config.Role.get_raw("redacteur"))(
        app_commands.default_permissions(priority_speaker=True)(callback)  # Hack since we cannot restrict on roles
    )


def joueurs_only(callback):
    """Décorateur pour commande (:func:`discord.app_commands.check`) :

    commande exécutable uniquement par un joueur,
    :attr:`vivant <.config.Role.joueur_en_vie>` ou
    :attr:`mort <.config.Role.joueur_mort>`.
    """
    return app_commands.checks.has_any_role(config.Role.get_raw("joueur_en_vie"), config.Role.get_raw("joueur_mort"))(
        callback
    )


def vivants_only(callback):
    """Décorateur pour commande (:func:`discord.app_commands.check`) :

    commande exécutable uniquement par un
    :attr:`joueur vivant <.config.Role.joueur_en_vie>`
    """
    return app_commands.checks.has_role(config.Role.get_raw("joueur_en_vie"))(
        app_commands.default_permissions(send_messages=True)(callback)
    )


_Command = typing.TypeVar("_Command", bound=typing.Callable)


def private() -> Callable[[_Command], _Command]:
    """Décorateur : commande utilisable dans son chan privé uniquement.

    Lors d'une invocation de la commande décorée hors d'un channel privé
    (commençant par :attr:`config.private_chan_prefix`), supprime le
    message d'invocation et exécute la commande dans le channel privé de l'invocateur.

    Si le joueur ayant utilisé la commande n'a pas de chan privé (pas en base), raise une :exc:`ValueError`.

    Utilisable en combinaison avec :func:`.joueurs_only` et :func:`.vivants_only`
    (pas avec les autres attention, vu que seuls les joueurs ont un channel privé).
    """

    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.channel.name.startswith(config.private_chan_prefix):  # OK
            return True

        private_chan = Joueur.from_member(interaction.user).private_chan
        await interaction.response.send_message(
            f":x: La commande `/{interaction.command.qualified_name}` est interdite en dehors de ta conv privée !\n"
            f":arrow_forward: Réessaie dans {private_chan.mention}",
            ephemeral=True,
        )
        return False

    return app_commands.check(predicate)


# ---------------------------------------------------------------------------
# Transformers
# ---------------------------------------------------------------------------


_Table = typing.TypeVar("_Table", bound=bdd.base.TableBase)


class _TableTransformerMixin:
    async def _transform(self, table: type[_Table], value: str) -> _Table:
        elems = table.find_nearest(value, col="nom")
        if not elems:
            raise commons.UserInputError(table.__name__.lower(), f"{table.__name__} introuvable en base : {value}")
        return elems[0][0]

    async def _autocomplete(self, table: type[_Table], current: str, filtre=None) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=elem.nom, value=elem.nom) for elem in self.get_elems(table, current, filtre=filtre)
        ][:25]

    def get_elems(self, table, current, filtre=None):
        base_filtre = table.discord_id != -1 if hasattr(table, 'discord_id') else None
        if base_filtre is not None:
            filtre = base_filtre if filtre is None else (filtre & base_filtre)
        for elem, _ in table.find_nearest(current, table.nom, sensi=0.25 if len(current) > 2 else 0, filtre=filtre):
            yield elem


class JoueurTransformer(app_commands.Transformer, _TableTransformerMixin):
    async def transform(self, interaction: discord.Interaction, value: str) -> Joueur:
        return await super()._transform(Joueur, value)

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await super()._autocomplete(Joueur, current)


class VivantTransformer(app_commands.Transformer, _TableTransformerMixin):
    async def transform(self, interaction: discord.Interaction, value: str) -> Joueur:
        joueur = await super()._transform(Joueur, value)
        if not joueur.est_vivant:
            raise commons.UserInputError("joueur", f"Eh oh, tu ne vois pas que {value} est mort ?")
        return joueur

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await super()._autocomplete(Joueur, current, filtre=Joueur.est_vivant)


class MortTransformer(app_commands.Transformer, _TableTransformerMixin):
    async def transform(self, interaction: discord.Interaction, value: str) -> Joueur:
        joueur = await super()._transform(Joueur, value)
        if not joueur.est_mort:
            raise commons.UserInputError("joueur", f"Eh oh, {value} est encore vivant aux dernière nouvelles !")
        return joueur

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await super()._autocomplete(Joueur, current, filtre=Joueur.est_mort)


class _CandidHaroTransformerMixin(_TableTransformerMixin):
    OK_SUFFIX = ""
    NOK_SUFFIX = ""

    async def _transform(self, table: type[_Table], value: str) -> _Table:
        return await super()._transform(table, value.removesuffix(self.OK_SUFFIX).removesuffix(self.NOK_SUFFIX))

    async def get_choices(
        self, current: str, candid_haro_type: CandidHaroType, ok_mark: str, nok_mark: str
    ) -> list[app_commands.Choice[str]]:
        harotes = {haro.joueur for haro in CandidHaro.query.filter_by(type=candid_haro_type).all()}

        if len(current) <= 2 and harotes:
            return [app_commands.Choice(name=f"{joueur.nom}{self.OK_SUFFIX}", value=joueur.nom) for joueur in harotes][
                :25
            ]

        proches = super().get_elems(Joueur, current, filtre=Joueur.est_vivant)
        choix_proches = [
            app_commands.Choice(name=f"{joueur.nom}{self.NOK_SUFFIX}", value=joueur.nom) for joueur in proches
        ]
        choix_harotes = [
            app_commands.Choice(name=f"{joueur.nom}{self.OK_SUFFIX}", value=joueur.nom)
            for joueur in harotes
            if joueur not in proches
        ]
        return choix_proches[: 3 if choix_harotes else 25] + choix_harotes[:22]


class HaroteTransformer(VivantTransformer, _CandidHaroTransformerMixin):
    OK_SUFFIX = f" ✅ haro"
    NOK_SUFFIX = f" ⚠️ pas de haro"

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        #return await super().get_choices(current, CandidHaroType.haro, "")
        return await super().get_choices(current, CandidHaroType.haro, self.OK_SUFFIX, self.NOK_SUFFIX)



class CandidatTransformer(VivantTransformer, _CandidHaroTransformerMixin):
    OK_SUFFIX = f" ✅ candidat"
    NOK_SUFFIX = f" ⚠️ pas candidat"

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        #return await super().get_choices(current, CandidHaroType.candidature)
        return await super().get_choices(current, CandidHaroType.haro, self.OK_SUFFIX, self.NOK_SUFFIX)



class RoleTransformer(app_commands.Transformer, _TableTransformerMixin):
    async def transform(self, interaction: discord.Interaction, value: str) -> Role:
        role = await super()._transform(Role, value)
        if not role.actif:
            raise commons.UserInputError("role", "C'est quoi ce rôle ? Je connais pas")
        return role

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await super()._autocomplete(Role, current, filtre=Role.actif == True)


class CampTransformer(app_commands.Transformer, _TableTransformerMixin):
    async def transform(self, interaction: discord.Interaction, value: str) -> Camp:
        camp = await super()._transform(Camp, value)
        if not camp.public:
            raise commons.UserInputError("camp", "T'as vu ça où toi ?")
        return camp

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return await super()._autocomplete(Camp, current, filtre=Camp.public == True)


class CommandTransformer(app_commands.Transformer):
    @staticmethod
    def _get_commands(interaction: discord.Interaction) -> dict[str, app_commands.Command]:
        if getattr(interaction.namespace, "mode") == "enable":
            return config.bot.tree.disabled_commands
        else:
            return config.bot.tree.enabled_commands

    async def transform(self, interaction: discord.Interaction, value: str) -> app_commands.Command:
        return self._get_commands(interaction)[value]

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=name, value=name) for name in self._get_commands(interaction) if current in name
        ][:25]


class SubCommandTransformer(app_commands.Transformer):
    @staticmethod
    def _get_commands(interaction: discord.Interaction) -> dict[str, app_commands.Command]:
        return config.bot.tree.enabled_commands_and_subcommands

    async def transform(self, interaction: discord.Interaction, value: str) -> app_commands.Command:
        return self._get_commands(interaction)[value]

    async def autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=name, value=name) for name in self._get_commands(interaction) if current in name
        ][:25]


# ---------------------------------------------------------------------------
# Commandes d'interaction avec les joueurs : input, boucles, confirmation...
# ---------------------------------------------------------------------------

# Commande générale, à utiliser à la place de bot.wait_for('message', ...)
async def wait_for_message(
    check: Callable[[discord.Message], bool],
    chan: discord.TextChannel,
) -> discord.Message:
    """Attend le premier message reçu rencontrant les critères demandés.

    Surcouche de :meth:`discord.Client.wait_for` permettant de réagir au mot-clé ``stop``.

    Args:
        check: Fonction validant ou non chaque message.
        chan: Le channel dans lequel le message est attendu.

    Returns:
        Le message reçu.

    Raises:
        .CommandExit: si le message est un des :obj:`.config.stop_keywords`
            (insensible à la casse), même si il respecte ``check``
    """
    stop_keywords = [kw.lower() for kw in config.stop_keywords]

    def trig_check(message: discord.Message):
        return check(message) or (message.channel == chan and message.content.lower() in stop_keywords)

    return await config.bot.wait_for("message", check=trig_check)


async def wait_for_react_added(message: discord.Message, process_text: bool = False) -> str | discord.Emoji:
    """Attend l'ajout d'une réaction sur un message.

    Args:
        message: Message où détecter les réactions.
        process_text: si ``True``, détecte aussi la réponse par message dans le même channel.

    Returns:
        L'emoji ajouté, ou le contenu du message textuel.
    """

    def react_check(react: discord.RawReactionActionEvent) -> bool:
        # Check REACT : bon message, bon emoji, et pas react du bot
        return react.message_id == message.id

    react_task = asyncio.create_task(config.bot.wait_for("raw_reaction_add", check=react_check))

    if process_text:
        # Check MESSAGE : bon channel, pas du bot, et filtre
        def message_check(mess: discord.Message) -> bool:
            return mess.channel == message.channel and mess.author != config.bot.user

    else:
        # On process DANS TOUS LES CAS, mais juste pour détecter les stop_keywords si process_text == False
        def message_check(mess: discord.Message) -> bool:
            return False

    mess_task = asyncio.create_task(wait_for_message(check=message_check, chan=message.channel))

    done, pending = await asyncio.wait([react_task, mess_task], return_when=asyncio.FIRST_COMPLETED)
    # Le bot attend ici qu'une des deux tâches aboutisse
    for task in pending:
        task.cancel()
    done_task = next(iter(done))  # done = tâche aboutie

    if done_task == react_task:  # Réaction
        return done_task.result().emoji

    # Réponse par message / STOP
    return done_task.result().content


async def sleep(chan: discord.abc.Messageable, tps: float) -> None:
    """Attend un temps donné en avertissant l'utilisateur.

    Pause l'exécution d'une commande en affichant l'indicateur *typing*
    ("*LGBot est en train d'écrire...*") sur un salon.

    Permet d'afficher plusieurs messages d'affilée en laissant le temps
    de lire, tout en indiquant que le bot n'a pas fini d'écrire.

    Args:
        chan: salon / contexte /... sur lequel attendre.
        tps: temps à attendre, en secondes.
    """
    async with chan.typing():
        await asyncio.sleep(tps)


# ---------------------------------------------------------------------------
# Utilitaires d'emojis
# ---------------------------------------------------------------------------


def montre(heure: str | None = None) -> str:
    """Renvoie l'emoji horloge le plus proche d'une heure donnée.

    Args:
        heure: heure à représenter, au format ``"XXh"`` ou ``"XXhMM"`` (défaut : heure actuelle).

    Returns:
       🕧, 🕓, 🕝...
    """
    if heure and isinstance(heure, str):
        heure, minute = heure.split("h")
        heure = int(heure) % 12
        minute = int(minute) % 60 if minute else 0
    else:
        now = datetime.datetime.now()
        heure = now.hour % 12
        minute = now.minute

    if minute >= 45:
        heure = (heure + 1) % 12

    if 15 < minute < 45:  # Demi heure
        L = [
            "\N{CLOCK FACE TWELVE-THIRTY}",
            "\N{CLOCK FACE ONE-THIRTY}",
            "\N{CLOCK FACE TWO-THIRTY}",
            "\N{CLOCK FACE THREE-THIRTY}",
            "\N{CLOCK FACE FOUR-THIRTY}",
            "\N{CLOCK FACE FIVE-THIRTY}",
            "\N{CLOCK FACE SIX-THIRTY}",
            "\N{CLOCK FACE SEVEN-THIRTY}",
            "\N{CLOCK FACE EIGHT-THIRTY}",
            "\N{CLOCK FACE NINE-THIRTY}",
            "\N{CLOCK FACE TEN-THIRTY}",
            "\N{CLOCK FACE ELEVEN-THIRTY}",
        ]
    else:  # Heure pile
        L = [
            "\N{CLOCK FACE TWELVE OCLOCK}",
            "\N{CLOCK FACE ONE OCLOCK}",
            "\N{CLOCK FACE TWO OCLOCK}",
            "\N{CLOCK FACE THREE OCLOCK}",
            "\N{CLOCK FACE FOUR OCLOCK}",
            "\N{CLOCK FACE FIVE OCLOCK}",
            "\N{CLOCK FACE SIX OCLOCK}",
            "\N{CLOCK FACE SEVEN OCLOCK}",
            "\N{CLOCK FACE EIGHT OCLOCK}",
            "\N{CLOCK FACE NINE OCLOCK}",
            "\N{CLOCK FACE TEN OCLOCK}",
            "\N{CLOCK FACE ELEVEN OCLOCK}",
        ]
    return L[heure]


def emoji_chiffre(chiffre: int, multi: bool = False) -> str:
    """Renvoie l'emoji / les emojis chiffre correspondant à un chiffre/nombre.

    Args:
        chiffre: chiffre/nombre à représenter.
        multi: si ``True``, ``chiffre`` peut être n'importe quel entier positif, dont les chiffres seront convertis
            séparément ; sinon (par défaut), ``chiffre`` doit être un entier entre ``0`` et ``10``.

    Returns:
        0️⃣, 1️⃣, 2️⃣...
    """
    if isinstance(chiffre, int) and 0 <= chiffre <= 10:
        return ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"][chiffre]
    elif multi and str(chiffre).isdigit():
        return "".join([emoji_chiffre(int(chr)) for chr in str(chiffre)])
    else:
        raise ValueError(
            "L'argument de tools.emoji_chiffre doit être un entier entre 0 et 10 OU un entier positif avec multi=True"
        )


def super_chiffre(chiffre: int, multi: bool = False) -> str:
    """Renvoie le(s) caractère(s) exposant correspondant à un chiffre/nombre.

    Args:
        chiffre: chiffre/nombre à représenter.
        multi: si ``True``, ``chiffre`` peut être n'importe quel entier positif, dont les chiffres seront convertis
            séparément ; sinon (par défaut), ``chiffre`` doit être un entier entre ``0`` et ``9``.

    Returns:
        ⁰, ¹, ²...
    """
    if isinstance(chiffre, int) and 0 <= chiffre <= 9:
        return ["⁰", "¹", "²", "³", "⁴", "⁵", "⁶", "⁷", "⁸", "⁹"][chiffre]
    elif multi and str(chiffre).isdigit():
        return "".join([super_chiffre(int(chr)) for chr in str(chiffre)])
    else:
        raise ValueError(
            "L'argument de tools.super_chiffre doit être un entier entre 0 et 9 OU un entier positif avec multi=True"
        )


def sub_chiffre(chiffre: int, multi: bool = False) -> str:
    """Renvoie le(s) caractère(s) indice correspondant à un chiffre/nombre.

    Args:
        chiffre: chiffre/nombre à représenter.
        multi: si ``True``, ``chiffre`` peut être n'importe quel entier positif, dont les chiffres seront convertis
            séparément ; sinon (par défaut), ``chiffre`` doit être un entier entre ``0`` et ``9``.

    Returns:
        ₀, ₁, ₂...
    """
    if isinstance(chiffre, int) and 0 <= chiffre <= 9:
        return ["₀", "₁", "₂", "₃", "₄", "₅", "₆", "₇", "₈", "₉"][chiffre]
    elif multi and str(chiffre).isdigit():
        return "".join([sub_chiffre(int(c)) for c in str(chiffre)])
    else:
        raise ValueError(
            "L'argument de tools.sub_chiffre doit être un "
            "entier entre 0 et 9 OU un entier positif avec "
            "multi=True"
        )


# ---------------------------------------------------------------------------
# Utilitaires de date / temps, notamment liées aux horaires de jeu
# ---------------------------------------------------------------------------


def heure_to_time(heure: str) -> datetime.time:
    """Convertit l'écriture d'une heure en objet :class:`datetime.time`.

    Args:
        heure: heure au format ``HHh``, ``HHhMM`` ou ``HH:MM``.

    Returns:
        Le datetime correspondant.

    Raises:
        ValueError: conversion impossible (mauvais format)
    """
    try:
        if "h" in heure:
            hh, mm = heure.split("h")
        else:
            hh, mm = heure.split(":")
        return datetime.time(int(hh), int(mm) if mm else 0)
    except ValueError as exc:
        raise ValueError(f'Valeur "{heure}" non convertible ' "en temps") from exc


def time_to_heure(tps: datetime.time, sep: str = "h", force_minutes: bool = False) -> str:
    """Convertit un objet :class:`datetime.time` en heure.

    (version maison de :meth:`datetime.time.strftime`)

    Args:
        tps: temps à convertir.
        sep: séparateur heures / minutes à utiliser (défaut ``"h"``).
        force_minutes: si ``False`` (défaut), les minutes ne sont indiquées que si différentes de ``0``.

    Returns:
        La description du temps fourni (``""`` si ``tps`` est ``None``)
    """
    if tps:
        if force_minutes or tps.minute > 0:
            return f"{tps.hour}{sep}{tps.minute:02}"
        else:
            return f"{tps.hour}{sep}"
    else:
        return ""


def next_occurrence(tps: datetime.time) -> datetime.datetime:
    """Renvoie la prochaine occurrence temporelle d'une heure donnée.

    Renvoie le prochain timestamp arrivant DANS LES HORAIRES DU JEU :
    entre :func:`.tools.fin_pause` et :func:`.tools.debut_pause`.

    Args:
        tps: heure dont on veut connaître la prochaine occurrence.

    Returns:
        Le datetime du prochain timestamp.
    """
    now = datetime.datetime.now()
    jour = now.date()
    if tps < now.time():
        # Si plus tôt dans la journée que l'heure actuelle,
        # on réfléchit comme si on était demain
        jour += datetime.timedelta(days=1)

    test_dt = datetime.datetime.combine(jour, tps)
    if test_dt < debut_pause() and not en_pause():
        # Prochaine occurence avant la pause : OK
        return test_dt

    # Sinon, programmer après la pause
    finp = fin_pause()
    jour = finp.date()
    if tps < finp.time():
        # Si plus tôt dans la journée que l'heure de reprise,
        # on réfléchit comme si on était le lendemain
        jour += datetime.timedelta(days=1)

    return datetime.datetime.combine(jour, tps)


def debut_pause() -> datetime.datetime:
    """Datetime du prochain début de pause du jeu.

    Returns:
        Le timestamp correspondant au prochain vendredi 19h.
    """
    pause_time = datetime.time(hour=19)
    pause_wday = 4  # Vendredi

    now = datetime.datetime.now()
    jour = now.date()
    if pause_time < now.time():
        # Si plus tôt dans la journée que l'heure actuelle,
        # on réfléchit comme si on était demain
        jour += datetime.timedelta(days=1)

    ddays = (pause_wday - jour.weekday()) % 7
    # Jour décalé du nombre de jours avant vendredi
    pause_jour = jour + datetime.timedelta(days=ddays)
    return datetime.datetime.combine(pause_jour, pause_time)


def fin_pause() -> datetime.datetime:
    """Datetime de la prochaine fin de pause du jeu.

    Returns:
       Le timestamp correspondant au prochain dimanche 19h.
    """
    reprise_time = datetime.time(hour=19)
    reprise_wday = 6  # Dimanche

    now = datetime.datetime.now()
    jour = now.date()
    if reprise_time < now.time():
        # Si plus tôt dans la journée que l'heure actuelle,
        # on réfléchit comme si on était demain
        jour += datetime.timedelta(days=1)

    ddays = (reprise_wday - jour.weekday()) % 7
    # Jour décalé du nombre de jours avant vendredi
    reprise_jour = jour + datetime.timedelta(days=ddays)
    return datetime.datetime.combine(reprise_jour, reprise_time)


def en_pause() -> bool:
    """Détermine si le jeu est actuellement en pause hebdomadaire.

    Si il n'y a pas de pause (:func:`.fin_pause` = :func:`.debut_pause`), renvoie toujours ``False``.

    Returns:
        Si le jeu est actuellement en pause hebdomadaire.
    """
    return fin_pause() < debut_pause()


# ---------------------------------------------------------------------------
# Split et log
# ---------------------------------------------------------------------------


def smooth_split(mess: str, N: int = 1990, sep: str = "\n", rep: str = "") -> list[str]:
    """Sépare un message en une blocs moins longs qu'une limite donnée.

    Très utile pour envoyer des messages de (potentiellement) plus de 2000 caractères (limitation Discord).

    Args:
        mess: message à découper.
        N: taille maximale des messages formés (défaut ``1990``, pour avoir un peu de marge par rapport
            à la limitation, et permettre d'entourer de ``````` par exemple)
        sep: caractères où séparer préférentiellement le texte (défaut : sauts de ligne).
            Si ``mess`` contient une sous-chaîne plus longue que ``N`` ne contenant pas ``sep``,
            le message sera tronqué à la limite.
        rep: chaîne ajoutée à la fin de chaque message formé (tronqué du séparateur final) (défaut : aucune).

    Returns:
        La liste des fractions du message.
    """
    if not mess or len(mess) <= N:
        return [mess]

    mess = str(mess)
    messages_list = []
    psl = 0  # indice du Précédent Saut de Ligne
    L = len(mess)
    while psl + N < L:
        if mess.count(sep, psl, psl + N + len(sep)):
            # +len(sep) parce que si sep est à la fin, on le dégage
            i = psl + N - mess[psl : psl + N + len(sep)][::-1].find(sep)
            # un peu sombre mais vrai, tkt frère
            messages_list.append(mess[psl:i] + rep)
            psl = i + 1  # on élimine le \n
        else:
            messages_list.append(mess[psl : psl + N] + rep)
            psl += N

    if psl < L:
        messages_list.append(mess[psl:])  # ce qui reste
    return messages_list


class _UpFollower:
    def __init__(self, interaction: discord.Interaction) -> None:
        self.followup = interaction.followup
        self.channel = interaction.channel

    async def send(self, content: str | None, view: discord.ui.View | None = None, **kwargs) -> discord.Message:
        try:
            if view:
                return await self.followup.send(content, view=view, **kwargs)
            else:
                fol = self.followup
                co = fol.send(content, **kwargs)
                return await co
        except discord.HTTPException:
            if view:
                return await self.channel.send(content, view=view, **kwargs)
            else:
                return await self.channel.send(content, **kwargs)


async def _send_messages(
    messageable: discord.abc.Messageable | discord.Interaction,
    contents: list[str],
    view: discord.ui.View | None = None,
    ephemeral: bool = False,
    author: discord.Member | None = None,
    **kwargs,
) -> list[discord.Message]:
    if not contents:
        return []

    messages = []
    if isinstance(messageable, discord.Interaction):
        interaction = messageable
        # first message -> interaction reply, if possible
        if not interaction.is_expired() and not interaction.response.is_done():
            try:
                if view and len(contents) == 1:  # sole message -> display view, if applicable
                    await interaction.response.send_message(contents[0], view=view, ephemeral=ephemeral, **kwargs)
                else:
                    await interaction.response.send_message(contents[0], ephemeral=ephemeral, **kwargs)
            except discord.HTTPException:
                pass  # Problème "Unknown interaction", notamment
            else:
                contents.pop(0)
                messages.append(await interaction.original_response())

            if not contents:
                return messages

        channel = _UpFollower(interaction)
        original_channel = interaction.channel
    else:
        channel = messageable
        original_channel = channel

    if ephemeral:
        # Message éphémère : on ne peut pas l'envoyer hors contexte d'intégration -> envoi en privé à la place
        if not author:
            raise RuntimeError("Interaction context unavailable or expired, ephemeral message and no author provided")
        if author.top_role >= config.Role.mj:
            channel = config.Channel.logs
        else:
            try:
                joueur = Joueur.from_member(author)
            except ValueError:
                raise RuntimeError(
                    "Interaction context unavailable or expired, ephemeral message and author is not a player or MJ"
                ) from None
            channel = joueur.private_chan

        if channel != original_channel:
            await channel.send(
                f":warning: {author.mention} Afin que le secret de ton action reste entre nous, "
                "continuons ici :arrow_down:"
            )

    if not messages:
        first_content = contents.pop(0)
        if view and not contents:  # last message -> display view, if applicable
            messages.append(await channel.send(first_content, view=view, **kwargs))
        else:
            messages.append(await channel.send(first_content, **kwargs))
        if not contents:
            return messages

    *main_contents, last_content = contents
    for content in main_contents:
        messages.append(await channel.send(content))

    # last message -> display view, if applicable
    messages.append(await channel.send(last_content, view=view))

    return messages


async def send_blocs(
    messageable: discord.abc.Messageable | discord.Interaction,
    mess: str,
    *,
    N: int = 1990,
    sep: str = "\n",
    rep: str = "",
    code: bool = False,
    prefix: str = "",
    langage: str = "",
    **kwargs,
) -> list[discord.Message]:
    """Envoie un message en le coupant en blocs si nécessaire.

    Surcouche de :func:`.smooth_split` envoyant directement les messages formés.

    Args:
        messageable: objet où envoyer le message ou interaction.
        mess: message à envoyer
        N, sep, rep: passé à :func:`.smooth_split`.
        prefix: texte optionnel à mettre hors des code blocs, au début du premier message.
        language: voir :func:`.code_bloc`.

    Returns:
        La liste des messages envoyés.
    """
    mess = str(mess)
    if prefix:
        prefix = prefix.rstrip() + "\n"

    blocs = smooth_split(prefix + mess, N=N, sep=sep, rep=rep)

    if code and mess:
        if prefix:
            blocs[0] = blocs[0][len(prefix) :]
        blocs = [code_bloc(bloc, langage=langage) for bloc in blocs]
        if prefix:
            blocs[0] = prefix + blocs[0]

    return await _send_messages(messageable, blocs, **kwargs)


async def log(
    message: str,
    *,
    code: bool = False,
    N: int = 1990,
    sep: str = "\n",
    rep: str = "",
    prefix: str = "",
    langage: str = "",
) -> list[discord.Message]:
    """Envoie un message dans le channel :attr:`config.Channel.logs`.

    Surcouche de :func:`.send_blocs` / :func:`.send_code_blocs`.

    Args:
        message: message à log.
        code: si ``True``, log sous forme de bloc(s) de code (défaut ``False``).
        N, sep, rep: passé à :func:`.send_blocs` / :func:`.send_code_blocs`.
        prefix: voir :func:`.send_blocs`, simplement ajouté avant ``message`` si ``code`` vaut ``False``.
        language: *identique à* :func:`.send_code_blocs`, ignoré si `code` vaut ``False``.

    Returns:
        La liste des messages envoyés.
    """
    return await send_blocs(
        config.Channel.logs, message, N=N, sep=sep, rep=rep, code=code, prefix=prefix, langage=langage
    )


# ---------------------------------------------------------------------------
# Autres fonctions diverses
# ---------------------------------------------------------------------------


def remove_accents(text: str) -> str:
    """Enlève les accents d'un chaîne, mais conserve les caractères spéciaux.

    Version plus douce de ``unidecode.unidecode``, conservant notamment les emojis, ...

    Args:
        text: chaîne à désaccentuer.

    Returns:
        La chaîne désaccentuée.
    """
    p = re.compile("([À-ʲΆ-ת])")
    # Abracadabrax, c'est moche mais ça marche (source : tkt frère)
    return p.sub(lambda c: unidecode.unidecode(c.group()), text)


# Évaluation d'accolades
def eval_accols(rep: str, globals_: dict[str, Any] = None, locals_: dict[str, Any] = None, debug: bool = False) -> str:
    """Replace chaque bloc entouré par des ``{}`` par leur évaluation Python.

    Args:
        globals_: variables globales du contexte d'évaluation (passé à :func:`eval`).
        locals_: variables locales du contexte d'évaluation (passé à :func:`eval`).
        debug: si ``True``, insère le message d'erreur (type et texte de l'exception) dans le message
            à l'endroit où une exception est levée durant l'évaluation (défaut ``False``).

    Penser à passer les :func:`globals` et :func:`locals` si besoin.
    Généralement, il faut passer :func:`locals` qui contient ``ctx``, etc...
    mais pas :func:`globals` si on veut bénéficier de tous les modules importés dans ``tools.py``.
    """
    if globals_ is None:
        globals_ = globals()
        globals_.update(tools=__import__(__name__, fromlist=("tools")))
    if locals_ is None:
        locals_ = globals_

    if "{" not in rep:  # Si pas d'expressions, on renvoie direct
        return rep

    evrep = ""  # Réponse évaluée
    expr = ""  # Expression à évaluer
    noc = 0  # Nombre de { non appariés
    for car in rep:
        if car == "{":
            if noc:  # Expression en cours :
                expr += car  # on garde le {
            noc += 1
        elif car == "}":
            noc -= 1
            if noc:  # idem
                expr += car
            else:  # Fin d'une expression
                try:  # On essaie d'évaluer la chaîne
                    evrep += str(eval(expr, globals_, locals_))
                except Exception as e:
                    # Si erreur, on laisse {expr} non évaluée
                    evrep += "{" + expr + "}"
                    if debug:
                        evrep += code(f"->!!! {e} !!!")
                expr = ""
        elif noc:  # Expression en cours
            expr += car
        else:  # Pas d'expression en cours
            evrep += car
    if noc:  # Si expression jamais finie (nombre impair de {)
        evrep += "{" + expr
    return evrep


async def multicateg(base_name: str) -> discord.CategoryChannel:
    """Permet de gérer des groupes de catégories (plus de 50 salons).

    Renvoie la première catégorie pouvant accueillir un nouveau
    salon ; en crée une nouvelle si besoin.

    Args:
        base_name: le nom du groupe de catégorie (nom de la première catégorie, puis sera suivi de 2, 3...)

    Warning:
        Une catégorie appelée ``base_name`` doit exister au préalable dans le serveur (:attr:`config.guild`).

    Returns:
       La catégorie libre.
    """
    categ = channel(base_name)
    nb = 1
    while len(categ.channels) >= 50:
        # Limitation Discord : 50 channels par catégorie
        nb += 1
        next_name = f"{base_name} {nb}"
        next_categ = channel(next_name, must_be_found=False)
        if not next_categ:
            next_categ = await categ.clone(name=next_name)
        categ = next_categ

    return categ


def in_multicateg(categ: discord.CategoryChannel, base_name: str) -> bool:
    """Détecte si une catégorie appartient à un groupe de catégories.

    Args:
        categ: la catégorie à tester.
        base_name: le nom de base du groupe de catégories (voir :func:`.multicateg`).

    Returns:
        Si la catégorie fait partie du groupe.
    """
    stripped_name = categ.name.rstrip(string.digits + " ")
    return stripped_name == base_name


# ---------------------------------------------------------------------------
# Utilitaires de formatage de texte
# ---------------------------------------------------------------------------


def bold(text: str) -> str:
    """Formate une chaîne comme texte en **gras** dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f"**{text}**"


def ital(text: str) -> str:
    """Formate une chaîne comme texte en *italique* dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f"*{text}*"


def soul(text: str) -> str:
    """Formate une chaîne comme texte souligné dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f"__{text}__"


def strike(text: str) -> str:
    """Formate une chaîne comme texte barré dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f"~~{text}~~"


def code(text: str) -> str:
    """Formate une chaîne comme ``code`` (inline) dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f"`{text}`"


def code_bloc(text: str, langage: str = "") -> str:
    """Formate une chaîne comme un bloc de code dans Discord.

    Args:
        text: chaîne à formater.
        langage: langage du code, pour coloration syntaxique.

    Langages supportés (non exhaustif ?) : ``asciidoc``, ``autohotkey``,
    ``bash``, ``coffeescript``, ``cpp`` (C++), ``cs`` (C#), ``css``,
    ``diff``, ``fix``, ``glsl``, ``ini``, ``json``, ``md``, (markdown),
    ``ml``, ``prolog``, ``py``, ``tex``, ``xl``, ``xml``

    Returns:
        La chaîne formatée.
    """
    return f"```{langage}\n{text}```"


def quote(text: str) -> str:
    """Formate une chaîne comme citation (inline) dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f"> {text}"


def quote_bloc(text: str) -> str:
    """Formate une chaîne comme bloc de citation (multiline) dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f">>> {text}"


def spoiler(text: str) -> str:
    """Formate une chaîne comme spoiler (cliquer pour afficher) dans Discord.

    Args:
        text: chaîne à formater.

    Returns:
        La chaîne formatée.
    """
    return f"||{text}||"
