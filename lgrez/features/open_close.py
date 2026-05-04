"""lg-rez / features / Gestion des votes et actions

Ouverture / fermeture / rappels des votes et actions (+ refill)

"""

import datetime
import enum
from typing import Literal

from discord import app_commands
import discord

from lgrez import commons, config
from lgrez.blocs import tools
from lgrez.blocs.journey import DiscordJourney, journey_command
from lgrez.features import gestion_actions, communication
from lgrez.bdd import (
    Joueur,
    Action,
    BaseAction,
    Tache,
    CandidHaro,
    Utilisation,
    CandidHaroType,
    ActionTrigger,
    Vote,
    Role,
    Camp,
    Statut,
)
from lgrez.features.taches import planif_command
from lgrez.features.voter_agir import do_vote_random
from lgrez.bdd.enums import Statut


async def _get_joueurs(quoi: Literal["open", "close", "remind"], qui: Vote) -> list[Joueur]:
    """Récupère les joueurs concernés par la tâche /quoi <qui> [heure].

    Args:
        quoi: évènement, ``"open" / "close" / "remind"``.
        qui:
            ===========     ===========
            ``Vote``        pour le vote correspondant
            ``actions``     pour les actions commençant à ``heure``
            ``{id}``        pour une action précise (:attr:`bdd.Action.id`)
            ===========     ===========

        heure: si ``qui == "actions"``, heure associée (au format ``HHhMM``).

    Returns:
        La liste des joueurs concernés.
    """
    # Critère principal : présence/absence d'une action actuellement ouverte (et non traitée pour remind)
    criteres = {
        "open": ~Joueur.actions.any(Action.is_open, vote=qui),
        "close": Joueur.actions.any(Action.is_open, vote=qui),
        "remind": Joueur.actions.any(Action.is_waiting, vote=qui),
    }
    critere = criteres[quoi]
    if quoi == "open":
        # Open : le joueur doit en plus avoir votant_village/loups True
        if qui == Vote.loups:
            critere &= Joueur.votant_loups.is_(True)
        else:
            critere &= Joueur.votant_village.is_(True)

    return Joueur.query.filter(critere).all()


async def _get_actions(quoi: Literal["open", "close", "remind"], heure: str) -> list[Action]:
    # Si l'heure est précisée, on convertit "HHhMM" -> datetime.time
    tps = tools.heure_to_time(heure)
    return gestion_actions.get_actions(quoi, ActionTrigger.temporel, tps)


async def _get_action(quoi: Literal["open", "close", "remind"], id: int) -> Action | None:
    action = Action.query.get(id)
    if not action:
        raise commons.UserInputError("qui", f"Pas d'action d'ID = {id}")
    if not action.active:
        raise commons.UserInputError("qui", f"Action d'ID = {id} inactive")

    # Appel direct action par son numéro (perma : rappel seulement)
    if (
        (quoi == "open" and (not action.is_open or action.base.trigger_debut == ActionTrigger.perma))
        or (quoi == "close" and action.is_open)
        or (quoi == "remind" and action.is_waiting)
    ):
        # Action lançable
        return action
    else:
        return None


async def _do_refill(motif: str, action: Action) -> None:
    # Détermination nouveau nombre de charges
    if motif in config.refills_full:
        # Refill -> nombre de charges initial de l'action
        new_charges = action.base.base_charges
    else:
        # Refill -> + 1 charge
        new_charges = action.charges + 1

    # Refill proprement dit
    if new_charges <= action.charges:
        # Pas de rechargement à faire (déjà base_charges)
        return

    if not action.charges and action.base.trigger_debut == ActionTrigger.perma:
        # Action permanente qui était épuisée : on ré-ouvre !
        if tools.en_pause():
            ts = tools.fin_pause()
        else:
            ts = datetime.datetime.now() + datetime.timedelta(seconds=10)
            # + 10 secondes pour ouvrir après le message de refill
        await planif_command(ts, open_action, id=action.id)

    action.charges = new_charges
    config.session.commit()

    await action.joueur.private_chan.send(
        f"Ton action {action.base.slug} vient d'être rechargée, "
        f"tu as maintenant {new_charges} charge(s) disponible(s) !"
    )


DESCRIPTION = """Commandes de gestion des votes et actions"""


open = app_commands.Group(name="open", description="Ouvrir quelque chose")
open = tools.mjs_only(open)


@open.command(name="vote")
@tools.mjs_only
@journey_command
async def open_vote(journey: DiscordJourney, *, qui: Vote, heure: str | None = None, heure_chain: str | None = None):
    """Lance un vote (COMMANDE BOT / MJ)

    Args:
        qui: Type de vote à lancer (vote pour le condamné du jour, le nouveau maire ou la victime des loups).
        heure: Heure à laquelle programmer la fermeture du vote, optionnel (HHh / HHhMM).
        heure_chain: Heure à laquelle programmer une ré-ouverture, pour boucler à l'infini (HHh / HHhMM).

    Une sécurité empêche de lancer un vote ou une action déjà en cours.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi
    (penser à envoyer / planifier la fermeture des votes, par exemple).

    Examples:
        - ``/open maire`` :         lance un vote maire maintenant
        - ``/open cond 19h`` :      lance un vote condamné maintenant et programme sa fermeture à 19h00
        - ``/open cond 18h 10h`` :  lance un vote condamné maintenant, programme sa fermeture à 18h00,
                                    et une prochaine ouverture à 10h qui se fermera à 18h, et ainsi de suite
    """
    joueurs = await _get_joueurs("open", qui)

    await journey.send(
        "\n".join(f" - {joueur.nom}" for joueur in joueurs),
        code=True,
        prefix=f"Joueur(s) répondant aux critères ({len(joueurs)}) :",
    )

    match qui:
        case Vote.cond:
            content = (
                f"{tools.montre()}  Le vote pour le condamné du jour est ouvert !  {config.Emoji.bucher} \n"
                + (f"Tu as jusqu'à {heure} pour voter. \n" if heure else "")
                + tools.ital(f"Tape {tools.code('/vote <joueur>')} pour voter.")
            )
            vote_command = "vote"
            haro_command = "haro"

        case Vote.maire:
            content = (
                f"{tools.montre()}  Le vote pour l'élection du maire est ouvert !  {config.Emoji.maire} \n"
                + (f"Tu as jusqu'à {heure} pour voter. \n" if heure else "")
                + tools.ital(f"Tape {tools.code('/votemaire <joueur>')} pour voter.")
            )
            vote_command = "votemaire"
            haro_command = "candid"

        case Vote.loups:
            content = (
                f"{tools.montre()}  Le vote pour la victime de cette nuit est ouvert !  {config.Emoji.lune} \n"
                + (f"Tu as jusqu'à {heure} pour voter. \n" if heure else "")
                + tools.ital(f"Tape {tools.code('/voteloups <joueur>')} pour voter.")
            )
            vote_command = "voteloups"
            haro_command = None

    # Activation commande de vote
    # config.bot.tree.enable_command(vote_command)
    # if haro_command:
    #     config.bot.tree.enable_command(haro_command)
    # await config.bot.tree.sync(guild=config.guild)

    # Création utilisations & envoi messages
    for joueur in joueurs:
        chan = joueur.private_chan

        action = joueur.action_vote(qui)
        if action.is_open:  # Sécurité : action ouverte depuis
            continue
        util = Utilisation(action=action)
        util.add()
        util.open()

        await chan.send(content)

    config.session.commit()

    # Actions déclenchées par ouverture
    if isinstance(qui, Vote):
        for action in Action.query.join(Action.base).filter(BaseAction.trigger_debut == ActionTrigger.open(qui)):
            await gestion_actions.open_action(action)

        for action in Action.query.join(Action.base).filter(BaseAction.trigger_fin == ActionTrigger.open(qui)):
            await gestion_actions.close_action(action)

    # Réinitialise haros/candids
    items = []
    if qui == Vote.cond:
        items = CandidHaro.query.filter_by(type=CandidHaroType.haro).all()
    elif qui == Vote.maire:
        items = CandidHaro.query.filter_by(type=CandidHaroType.candidature).all()
    if items:
        for item in items:
            await item.disable_message_buttons()
        CandidHaro.delete(*items)

        await tools.log(f"/open {qui.name} : haros/candids wiped")
        await config.Channel.haros.send(
            f"{config.Emoji.void}\n" * 30
            + "Nouveau vote, nouveaux haros !\n"
            + tools.ital(
                f"Les posts ci-dessus sont invalides pour le vote actuel. "
                f"Utilisez {tools.code('/haro')} pour en relancer."
            )
        )
        
        
    # Crée des candidatures automatiques pour tous les villagois en cas de vote maire
    if qui == Vote.maire:
        candidats = Joueur.query.filter(Joueur.votant_village.is_(True)).all()
        for joueur in candidats:
            CandidHaro.add(CandidHaro(joueur=joueur, type=CandidHaroType.candidature))
        config.session.commit()

        await tools.log(f"/open maire : {len(candidats)} candidatures automatiques créées")
        await config.Channel.haros.send(
            f"{len(candidats)} joueurs sont automatiquement candidats à la mairie ! {config.Emoji.maire}"
        )

    # Programme fermeture
    if heure:
        ts = tools.next_occurrence(tools.heure_to_time(heure))
        await planif_command(ts - datetime.timedelta(minutes=30), remind_vote, qui=qui)
        if heure_chain:
            await planif_command(ts, close_vote, qui=qui, heure=heure_chain, heure_chain=heure)
        else:
            await planif_command(ts, close_vote, qui=qui)
            
    class _RandomView(discord.ui.View):
        @discord.ui.button(
            label=f"Voter random"[:80], style=discord.ButtonStyle.primary, emoji=config.Emoji.bucher
        )
        async def vote(self, vote_interaction: discord.Interaction, button: discord.ui.Button):
            async with DiscordJourney(vote_interaction, ephemeral=True) as vote_journey:
                try:
                    votant = Joueur.from_member(vote_journey.member)
                except ValueError:
                    await vote_journey.send(":x: Tu n'as pas le droit de vote, toi")
                    return
                await do_vote_random(vote_journey, Vote.cond, votant=votant)

        async def on_error(self, _interaction: discord.Interaction, error: Exception, _item: discord.ui.Item) -> None:
            raise error


    # Activation de la commande voterrandom
    if qui == Vote.cond:
        config.bot.tree.enable_command("voterrandom")
        await config.bot.tree.sync(guild=config.guild)
        random_message = await config.Channel.haros.send(
            f"Vote random (sera désigné a 18h15 en cas de majorité)", view=_RandomView(timeout=None)
        )

@open.command(name="actions")
@tools.mjs_only
@journey_command
async def open_actions(journey: DiscordJourney, heure: str):
    """Ouvre les actions commençant à une heure donnée (COMMANDE BOT / MJ)

    Args:
        heure: Heure de début des actions à lancer.

    Une sécurité empêche d'ouvrir une action déjà en cours.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi (penser à envoyer /
    planifier la fermeture de l'action).
    """
    actions = await _get_actions("open", heure)

    await journey.send(
        "\n".join(f" - {action.base.slug} - {action.joueur.nom}" for action in actions),
        code=True,
        prefix=f"Action(s) répondant aux critères ({len(actions)}) :",
    )
    for action in actions:
        await gestion_actions.open_action(action)


@open.command(name="action")
@tools.mjs_only
@journey_command
async def open_action(journey: DiscordJourney, id: int):
    """Lance une action donnée (COMMANDE BOT / MJ)

    Args:
        id: ID de l'action à ouvrir.

    Une sécurité empêche d'ouvrir une action déjà en cours.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi (penser à envoyer /
    planifier la fermeture de l'action).
    """
    action = await _get_action("open", id)
    if not action:
        await journey.send(f"L'action #{id} est déjà ouverte !")
        return

    await journey.send(f"Joueur concerné : {action.joueur}")
    await gestion_actions.open_action(action)


close = app_commands.Group(name="close", description="Clôturer quelque chose")
close = tools.mjs_only(close)


@close.command(name="vote")
@tools.mjs_only
@journey_command
async def close_vote(journey: DiscordJourney, *, qui: Vote, heure: str | None = None, heure_chain: str | None = None):
    """Ferme un vote (COMMANDE BOT / MJ)

    Args:
        qui: Type de vote à fermer (vote pour le condamné du jour, le nouveau maire ou la victime des loups).
        heure: Heure à laquelle programmer une prochaine ouverture du vote, optionnel (HHh / HHhMM).
        heure_chain: Heure à laquelle programmer une re-fermeture, pour boucler à l'infini (HHh / HHhMM).

    Une sécurité empêche de fermer un vote ou une action qui n'est pas en cours.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi
    (penser à envoyer / planifier la fermeture des votes, par exemple).

    Examples:
        - ``/close maire`` :        ferme le vote condamné maintenant
        - ``/close cond 10h`` :     ferme le vote condamné maintenant et programme une prochaine ouverture à 10h00
        - ``/close cond 10h 18h`` : ferme le vote condamné maintenant, programme une prochaine ouverture à 10h00,
                                    qui sera fermé à 18h, puis une nouvelle ouverture à 10h, etc
    """
    joueurs = await _get_joueurs("close", qui)

    await journey.send(
        "\n".join(f" - {joueur.nom}" for joueur in joueurs),
        code=True,
        prefix=f"Joueur(s) répondant aux critères ({len(joueurs)}) :",
    )

    match qui:
        case Vote.cond:
            content = (
                f"{tools.montre()}  Fin du vote pour le condamné du jour !\nVote définitif : {{nom_cible}}\n"
                f"Les résultats arrivent dans l'heure !\n"
            )
            vote_command = "vote"
            haro_command = "haro"

        case Vote.maire:
            content = f"{tools.montre()}  Fin du vote pour le maire ! \nVote définitif : {{nom_cible}}"
            vote_command = "votemaire"
            haro_command = "candid"

        case Vote.loups:
            content = f"{tools.montre()}  Fin du vote pour la victime du soir !\nVote définitif : {{nom_cible}}"
            vote_command = "voteloups"
            haro_command = None

    # Activation commande de vote
    # config.bot.tree.disable_command(vote_command)
    # if haro_command:
    #     config.bot.tree.disable_command(haro_command)
    # await config.bot.tree.sync(guild=config.guild)

    # Fermeture utilisations et envoi messages
    for joueur in joueurs:
        chan = joueur.private_chan

        if isinstance(qui, Vote):
            action = joueur.action_vote(qui)
            if not action.is_open:  # Sécurité : action fermée depuis
                continue
            util = joueur.action_vote(qui).utilisation_ouverte
            nom_cible = util.cible.nom if util.cible else "*non défini*"

            util.close()  # update direct pour empêcher de voter

        await chan.send(content.format(nom_cible=nom_cible))

    config.session.commit()

    # Actions déclenchées par fermeture
    if isinstance(qui, Vote):
        for action in Action.query.join(Action.base).filter(BaseAction.trigger_debut == ActionTrigger.close(qui)):
            await gestion_actions.open_action(action)

        for action in Action.query.join(Action.base).filter(BaseAction.trigger_fin == ActionTrigger.close(qui)):
            await gestion_actions.close_action(action)

    # Programme prochaine ouverture
    if heure:
        ts = tools.next_occurrence(tools.heure_to_time(heure))
        if heure_chain:
            await planif_command(ts, open_vote, qui=qui, heure=heure_chain, heure_chain=heure)
        else:
            await planif_command(ts, open_vote, qui=qui)
     
     # Désactivation de la commande voterrandom à la fermeture
    if qui == Vote.cond:
        try:
            config.bot.tree.disable_command("voterrandom")
            await config.bot.tree.sync(guild=config.guild)
        except LookupError:
            pass


async def _close_action(action):
    await action.joueur.private_chan.send(
        f"{tools.montre()}  Fin de la possibilité d'utiliser ton action {tools.code(action.base.slug)} ! \n"
        f"Action définitive : {action.decision}"
    )
    await gestion_actions.close_action(action)


@close.command(name="actions")
@tools.mjs_only
@journey_command
async def close_actions(journey: DiscordJourney, heure: str):
    """Clôture les actions terminant à une heure donnée (COMMANDE BOT / MJ)

    Args:
        heure: Heure de début des actions à clôturer.

    Une sécurité empêche de fermer une action déjà en cours.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi (penser à envoyer /
    planifier la fermeture de l'action).
    """
    actions = await _get_actions("close", heure)

    await journey.send(
        "\n ".join(f" - {action.base.slug} - {action.joueur.nom}" for action in actions),
        code=True,
        prefix=f"Action(s) répondant aux critères ({len(actions)}) :",
    )
    for action in actions:
        await _close_action(action)


@close.command(name="action")
@tools.mjs_only
@journey_command
async def close_action(journey: DiscordJourney, id: int):
    """Clôture un action (COMMANDE BOT / MJ)

    Args:
        id: ID de l'action à clôturer.

    Une sécurité empêche de fermer une action déjà en cours.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi (penser à envoyer /
    planifier la fermeture de l'action).
    """
    action = await _get_action("close", id)
    if not action:
        await journey.send(f"L'action #{id} n'est pas ouverte !")
        return

    await journey.send(f"Joueur concerné : {action.joueur}")
    await _close_action(action)


remind = app_commands.Group(name="remind", description="Rappeler quelque chose")
remind = tools.mjs_only(remind)


@remind.command(name="vote")
@tools.mjs_only
@journey_command
async def remind_vote(journey: DiscordJourney, *, qui: Vote):
    """Envoi un rappel de vote / actions de rôle (COMMANDE BOT / MJ)

    Args:
        qui: Type de vote à rappeler (vote pour le condamné du jour, le nouveau maire ou la victime des loups).

    Le bot n'envoie un message qu'aux joueurs n'ayant pas encore voté / agi,
    si le vote ou l'action est bien en cours.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi !

    Example:
        - ``/remind maire`` :       rappelle le vote maire maintenant
    """
    joueurs = await _get_joueurs("remind", qui)

    await journey.send(
        "\n".join(f" - {joueur.nom}" for joueur in joueurs),
        code=True,
        prefix=f"Joueur(s) répondant aux critères ({len(joueurs)}) :",
    )

    for joueur in joueurs:
        match qui:
            case Vote.cond:
                await joueur.private_chan.send(
                    f"⏰ {joueur.member.mention} Plus que 30 minutes pour voter pour le condamné du jour ! 😱 \n"
                )
            case Vote.maire:
                await joueur.private_chan.send(
                    f"⏰ {joueur.member.mention} Plus que 30 minutes pour élire le nouveau maire ! 😱 \n"
                )
            case Vote.loups:
                await joueur.private_chan.send(
                    f"⏰ {joueur.member.mention} Plus que 30 minutes pour voter pour la victime du soir ! 😱 \n"
                )


async def _remind_action(action):
    return await action.joueur.private_chan.send(
        f"⏰ {action.joueur.member.mention} Plus que 30 minutes pour utiliser ton action "
        f"{tools.code(action.base.slug)} ! 😱 \n"
    )


@remind.command(name="actions")
@tools.mjs_only
@journey_command
async def remind_actions(journey: DiscordJourney, heure: str):
    """Rappelle d'utiliser les actions terminant à une heure donnée (COMMANDE BOT / MJ)

    Args:
        heure: Heure de début des actions à rappeler.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi !
    """
    actions = await _get_actions("remind", heure)

    await journey.send(
        "\n".join(f" - {action.base.slug} - {action.joueur.nom}" for action in actions),
        code=True,
        prefix=f"Action(s) répondant aux critères ({len(actions)}) :",
    )
    for action in actions:
        await _remind_action(action)


@remind.command(name="action")
@tools.mjs_only
@journey_command
async def remind_action(journey: DiscordJourney, id: int):
    """Rappelle d'utiliser une action précise (COMMANDE BOT / MJ)

    Args:
        id: ID de l'action à rappeler.

    Cette commande a pour vocation première d'être exécutée automatiquement par des tâches planifiées.
    Elle peut être utilisée à la main, mais attention à ne pas faire n'importe quoi !
    """
    action = await _get_action("remind", id)
    if not action:
        await journey.send(f"L'action #{id} n'est pas ouverte !")
        return

    await journey.send(f"Joueur concerné : {action.joueur}")
    await _remind_action(action)


RefillMotif = enum.Enum("RefillMotif", config.refills_full + config.refills_one)


@app_commands.command()
@tools.mjs_only
@journey_command
async def refill(
    journey: DiscordJourney,
    motif: RefillMotif,
    *,
    joueur: app_commands.Transform[Joueur, tools.VivantTransformer] | None = None,
):
    """Recharger un/des pouvoirs rechargeables (COMMANDE BOT / MJ)

    Args:
        motif: Raison de rechargement (divin = forcer le refill car les MJs tout-puissants l'ont décidé).
        joueur: Si omis, recharge TOUS les joueurs.
    """
    motif: str = motif.name

    if motif in config.refills_divins:
        query = Action.query.filter(Action.active == True, Action.charges != None)
    else:
        query = Action.query.join(Action.base).filter(Action.active == True, BaseAction.refill.contains(motif))

    if joueur:
        query = query.filter(Action.joueur == joueur)
    else:
        await journey.ok_cancel("Tu as choisi de recharger le pouvoir de TOUS les joueurs actifs, en es-tu sûr ?")

    # do refill
    refillable = query.all()
    await tools.log(refillable, code=True, prefix=f"Refill {motif} {joueur.nom if joueur else 'ALL'} :")

    if joueur and len(refillable) > 1:
        action = await journey.select(
            "Action(s) répondant aux critères :",
            {action: f"{action.base.slug}, id = {action.id} \n" for action in refillable},
            placeholder="Choisir l'action à recharger",
        )
        refillable = [action]

    for action in refillable:
        await _do_refill(motif, action)
    await journey.send("Fait.")


@app_commands.command()
@tools.mjs_only
@journey_command
async def cparti(journey: DiscordJourney):
    """Lance le jeu (COMMANDE MJ)

    - Programme les votes condamnés quotidiens (avec chaînage) 10h-18h
    - Programme un vote maire 10h-18h
    - Programme les actions au lancement du jeu (choix de mentor...) et permanentes (forgeron)... à 19h
    - Crée les "actions de vote", sans quoi /open plante

    À utiliser le jour du lancement après 10h (lance les premières actions le soir et les votes le lendemain)
    """
    await journey.ok_cancel(
        "C'est parti ?\n"
        "Les rôles ont bien été attribués et synchronisés ? (si non, le faire AVANT de valider)\n\n"
        "On est bien après 10h le jour du lancement ?\n\n"
        "Tu es conscient que tous les joueurs recevront à 18h55 un message "
        "en mode « happy Hunger Games » ? (codé en dur parce que flemme)"
    )
    await journey.ok_cancel(
        "Les actions des joueurs ont été attribuées à la synchronisation des rôles, mais les /open "
        "n'ont aucun impact tant que tout le monde est en `role_actif == False` sur le Tableau de bord.\n"
        "Il faut donc **passer tout le monde à `True` maintenant** (puis `/sync silent`) avant de continuer."
    )
    await journey.ok_cancel(
        "Dernière chose à faire : activer le backup automatique du Tableau de bord tous les jours. "
        "Pour ce faire, l'ouvrir et aller dans `Extensions > Apps Script` puis dans le panel "
        "`Déclencheurs` à gauche (l'horloge) et cliquer sur `Ajouter un déclencheur` en bas à droite.\n\n"
        "Remplir les paramètres : `Backupfeuille`, `Head`, `Déclencheur horaire`, `Quotidien`, `Entre 1h et 2h` "
        "(pas plus tard car les votes du jour changent à 3h)."
    )
    
    config.bot.tree.disable_command("allie")
    await config.bot.tree.sync(guild=config.guild)
    rep = "C'est parti !\n"

    n10 = tools.next_occurrence(datetime.time(hour=10))
    n19 = tools.next_occurrence(datetime.time(hour=19))

    # Programmation votes condamnés chainés 10h-18h
    rep += "\nProgrammation des votes :\n"
    await planif_command(n10, open_vote, qui=Vote.cond, heure="18h", heure_chain="10h")
    rep += " - À 10h : /open cond 18h 10h\n"

    # Programmation votes loups chainés 19h-23h
    await planif_command(n19, open_vote, qui=Vote.loups, heure="23h", heure_chain="19h")
    rep += " - À 19h : /open loups 23h 19h\n"

    # Programmation premier vote maire 10h-17h
    await planif_command(n10, open_vote, qui=Vote.maire, heure="17h")
    rep += " - À 10h : /open maire 17h\n"

    # Programmation actions au lancement et actions permanentes
    rep += "\nProgrammation des actions start / perma :\n"
    start_perma = (
        Action.query.join(Action.base)
        .filter(BaseAction.trigger_debut.in_([ActionTrigger.start, ActionTrigger.perma]))
        .all()
    )
    for action in start_perma:
        rep += f" - À 19h : /open {action.id} (trigger_debut == {action.base.trigger_debut})\n"
        await planif_command(n19, open_action, id=action.id)

    # Programmation envoi d'un message aux connards
    rep += "\nEt, à 18h50 : /send all [message de hype oue oue c'est génial]\n"
    await planif_command(
        n19 - datetime.timedelta(minutes=10),
        communication.send,
        cibles="all",
        message=(
            "Ah {member.mention}... J'espère que tu es prêt(e), parce que la partie commence DANS 10 MINUTES !!!"
            "https://tenor.com/view/thehungergames-hungergames-thggifs-effie-gif-5114734"
        ),
    )
    await tools.log(rep, code=True)

    # Drop (éventuel) et (re-)création actions de vote
    Action.query.filter_by(base=None).delete()
    Action.add(*(Action(joueur=joueur, vote=vote) for joueur in Joueur.query.all() for vote in Vote))
    Action.query
    
    # Création du joueur fictif "Aléatoire" si pas déjà présent
    if not Joueur.query.get(-1):
        joueur_aleatoire = Joueur(
            discord_id=-1,
            chan_id_=-1,
            nom="Aléatoire",
            chambre=None,
            statut=Statut.mort,
            role=Role.default(),
            camp=Camp.default(),
            votant_village=False,
            votant_loups=False,
            role_actif=False,
        )
        joueur_aleatoire.add()

    await journey.send(f"C'est tout bon ! (détails dans {config.Channel.logs.mention})")


@app_commands.command()
@tools.mjs_only
@journey_command
async def cfini(journey: DiscordJourney):
    """✨ Clôture le jeu (COMMANDE MJ)

    Supprime toutes les tâches planifiées, ce qui stoppe de fait le jeu.
    """
    await journey.ok_cancel(
        "C'est fini ?\n"
        "ATTENTION : Confirmer supprimera TOUTES LES TÂCHES EN ATTENTE, ce qui est compliqué à annuler !"
    )

    await journey.send("Suppression des tâches...")
    async with journey.channel.typing():
        taches = Tache.query.all()
        Tache.delete(*taches)  # On supprime et déprogramme le tout !

    await journey.send(
        "C'est tout bon !\n"
        "Dernière chose : penser à désactiver le backup automatique du Tableau de bord !. "
        "Pour ce faire, l'ouvrir et aller dans `Extensions > Apps Script` puis dans le panel "
        "`Déclencheurs` à gauche (l'horloge) et cliquer sur les trois points à droite du déclencheur > Supprimer."
    )
