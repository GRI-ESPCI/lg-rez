import random
import unidecode
import traceback

from discord.ext import commands

import tools
from blocs import bdd_tools
from bdd_connect import db, Triggers, Reactions

MARK_OR = ' <||> '
MARK_AND = ' <&&> '
MARK_REACT = '<::>'
MARK_CMD = '<!!>'

# Commandes de STFU
async def stfu_on(ctx):
    if ctx.channel.id not in ctx.bot.in_stfu:
        await ctx.send("Okay, je me tais ! Tape !stfu quand tu voudras de nouveau de moi :cry:")
        ctx.bot.in_stfu.append(ctx.channel.id)
        #await ctx.channel.edit(topic = "Ta conversation privée avec le bot, c'est ici que tout se passera ! (STFU ON)")
    else:
        await ctx.send("Arrête de t'acharner, tu m'as déja dit de me taire...")

async def stfu_off(ctx):
    if ctx.channel.id in ctx.bot.in_stfu:
        await ctx.send("Ahhh, ça fait plaisir de pouvoir reparler !")
        ctx.bot.in_stfu.remove(ctx.channel.id)
        #await ctx.channel.edit(topic = "Ta conversation privée avec le bot, c'est ici que tout se passera !")
    else:
        await ctx.send("Ça mon p'tit pote, tu l'as déjà dit !")


async def build_sequence(ctx):
    reponse = ""
    fini = False
    while not fini:
        message = await ctx.send("Réaction du bot : prochain message/commande/média, ou réaction à ce message")
        ret = await tools.wait_for_react_clic(ctx.bot, message, process_text=True, trigger_all_reacts=True, trigger_on_commands=True)
        if isinstance(ret, str):
            if ret.startswith(ctx.bot.command_prefix):      # Commande
                reponse += MARK_CMD + ret.lstrip(ctx.bot.command_prefix).strip()
            else:                                           # Texte / média
                reponse += ret.strip()
        else:                                               # React
            reponse += MARK_REACT + ret.name

        message = await ctx.send("▶ Puis / 🔀 Ou / ⏹ Fin ?")
        ret = await tools.wait_for_react_clic(ctx.bot, message, emojis={"▶":MARK_AND, "🔀":MARK_OR, "⏹":False})
        if ret:
            reponse += ret
        else:
            fini = True

    return reponse


class GestionIA(commands.Cog):
    """
    GestionIA - Commandes relatives à l'IA et aux réponses automatiques du bot
    """

    @commands.command()
    @tools.private
    async def stfu(self, ctx, force=None): #stfu le channel de la personne mise en arguments
        """Active/désactive la réponse automatique du bot sur les channels privés

        [force=start/stop] permet de forcer l'activation / la désactivation. 
        Sans argument, la commande agit comme un toggle (allume les réactions si éteintes et vice-versa).

        N'agit que sur les messages classiques envoyés dans le channel : les commandes restent reconnues.
        Si vous ne comprenez pas le nom de la commande, demandez à Google.
        """
        if force == "start":
            await stfu_on(ctx)
        elif force == "stop":
            await stfu_off(ctx)
        else:
            if ctx.channel.id not in ctx.bot.in_stfu:
                await stfu_on(ctx)
            else:
                await stfu_off(ctx)


    @commands.command()
    @commands.has_role("MJ")
    async def addIA(self, ctx, *, triggers=None):
        """Ajouter au bot une règle d'IA : mots ou expressions déclenchant une réaction (COMMANDE MJ)

        [trigger] mot(s), phrase(s), ou expression(s) séparées par des points-virgules ou sauts de lignes
        Dans le cas où plusieurs expressions sont spécifiées, toutes déclencheront l'action demandée.
        """

        if not triggers:
            await ctx.send("Mots/expressions déclencheurs (non sensibles à la casse / accents), séparés par des points-virgules ou des sauts de ligne :")
            mess = await tools.wait_for_message(ctx.bot, check=lambda m:m.channel == ctx.channel and m.author != ctx.bot.user)
            triggers = mess.content

        triggers = triggers.replace('\n', ';').split(';')
        triggers = [unidecode.unidecode(s).lower().strip() for s in triggers]
        await ctx.send(f"Triggers : `{'` – `'.join(triggers)}`")

        reponse = await build_sequence(ctx)

        await ctx.send(f"Résumé de la séquence : {tools.code(reponse)}")
        async with ctx.typing():
            reac = Reactions(reponse=reponse)
            db.session.add(reac)
            db.session.flush()

            trigs = [Triggers(trigger=trigger, reac_id=reac.id) for trigger in triggers]
            db.session.add_all(trigs)
            db.session.commit()
        await ctx.send(f"Ajouté en base.")


    @commands.command()
    @commands.has_role("MJ")
    async def listIA(self, ctx, trigger=None, sensi=0.25):
        """Liste les règles d'IA actuellement reconnues par le bot (COMMANDE MJ)

        [trigger] (optionnel) mot/expression permettant de filter et trier les résultats. SI TRIGGER FAIT PLUS D'UN MOT, il doit être entouré par des guillemets !
        Si trigger est précisé, les triggers sont détectés avec une sensibilité [sensi] (ratio des caractères correspondants, entre 0 et 1).
        """
        try:
            if trigger:
                trigs = await bdd_tools.find_nearest(trigger, Triggers, carac="trigger", sensi=sensi, solo_si_parfait=False)
                if not trigs:
                    await ctx.send(f"Rien trouvé, pas de chance (sensi = {sensi})")
                    return
                reacts_ids = list({trig[0].reac_id for trig in trigs})          # Pas de doublons (et reste ordonné)
            else:
                trigs = Triggers.query.order_by(Triggers.id).all()              # Trié par date de création (apeupré)
                reacts_ids = list({trig.reac_id for trig in trigs})             # Pas de doublons (et reste ordonné)
                
            reacts = Reactions.query.filter(Reactions.id.in_(reacts_ids))
            
            if trigger:
                L = ["- " + ' – '.join([f"({float(score):.2}) " + trig.trigger for (trig, score) in trigs if trig.reac_id == id]).ljust(50) 
                    + f" ⇒ {Reactions.query.get(id).reponse}" for id in reacts_ids]
            else:
                L = ["- " + ' – '.join([trig.trigger for trig in trigs if trig.reac_id == id]).ljust(50)
                    + f" ⇒ {Reactions.query.get(id).reponse}" for id in reacts_ids]
                    
            r = "\n".join(L) + "\n\nPour modifier une réaction, utiliser !modifIA <trigger>."
            
            [await ctx.send(tools.code_bloc(mess)) for mess in tools.smooth_split(r)]
        except Exception:
            await ctx.send(traceback.format_exc())


    @commands.command()
    @commands.has_role("MJ")
    async def modifIA(self, ctx, *, trigger=None):
        """Modifie/supprime une règle d'IA (COMMANDE MJ)

        [trigger] mot/expression déclenchant la réaction à modifier/supprimer
        
        Permet d'ajouter et supprimer des triggers, de modifier la réaction du bot (construction d'une séquence de réponses successives ou aléatoires) ou de supprimer la réaction.
        """
        if not trigger:
            await ctx.send("Mot/expression déclencheur de la réaction à modifier :")
            mess = await tools.wait_for_message(ctx.bot, check=lambda m:m.channel == ctx.channel and m.author != ctx.bot.user)
            trigger = mess.content

        trigs = await bdd_tools.find_nearest(trigger, Triggers, carac="trigger")
        if not trigs:
            await ctx.send("Rien trouvé.")
            return

        trig = trigs[0][0]
        rep = Reactions.query.get(trig.reac_id)
        trigs = Triggers.query.filter_by(reac_id=trig.reac_id).all()

        await ctx.send(f"Triggers : `{'` – `'.join([trig.trigger for trig in trigs])}`\n"
                       f"Séquence réponse : {tools.code(rep.reponse)}")

        message = await ctx.send("Modifier : ⏩ triggers / ⏺ Réponse / ⏸ Les deux / 🚮 Supprimer ?")
        MT, MR = await tools.wait_for_react_clic(ctx.bot, message, emojis={"⏩":(True, False), "⏺":(False, True),
                                                                           "⏸":(True, True), "🚮":(False, False)})

        if MT:                      # Modification des triggers
            fini = False
            while not fini:
                s = "Supprimer un trigger : \n"
                for i, t in enumerate(trigs[:10]):
                    s += f"{tools.emoji_chiffre(i+1)}. {t.trigger} \n"
                mess = await ctx.send(s + "Ou entrer un mot / une expression pour l'ajouter en trigger.\n⏹ pour finir")
                r = await tools.wait_for_react_clic(ctx.bot, mess, emojis={(tools.emoji_chiffre(i) if i else "⏹"):str(i) for i in range(len(trigs)+1)}, process_text=True)

                if r == "0":
                    fini = True
                elif r.isdigit() and (n := int(r)) <= len(trigs):
                    db.session.delete(trigs[n-1])
                    db.session.commit()
                    del trigs[n-1]
                else:
                    trig = Triggers(trigger=r, reac_id=rep.id)
                    trigs.append(trig)
                    db.session.add(trig)
                    db.session.commit()

            if not trigs:        # on a tout supprimé !
                await ctx.send("Tous les triggers supprimés, suppression de la réaction")
                db.session.delete(rep)
                db.session.commit()
                return

        if MR:                  # Modification de la réponse
            mess = await ctx.send("Réécrire complètement la séquence ? (si non, modification brute : plus compliqué !)")
            if (await tools.yes_no(ctx.bot, mess)):
                reponse = await build_sequence(ctx)
            else:
                r = f"Séquence actuelle : {tools.code(rep.reponse)}" if MT else ""    # Si ça fait longtemps, on le remet
                r += f"\nMarqueur OU : {tools.code(MARK_OR)}, Marqueur ET : {tools.code(MARK_AND)}, Marqueur REACT : {tools.code(MARK_REACT)}, Marqueur CMD : {tools.code(MARK_CMD)}"
                mess = await ctx.send(r + "\nNouvelle séquence :")
                reponse = (await tools.wait_for_message(ctx.bot, lambda m:m.channel == ctx.channel and m.author != ctx.bot.user)).content

            bdd_tools.modif(rep, "reponse", reponse)

        if not (MT or MR):      # Suppression
            db.session.delete(rep)
            for trig in trigs:
                db.session.delete(trig)

        db.session.commit()

        await ctx.send("Fini.")



async def main(ctx):
    trigs = await bdd_tools.find_nearest(ctx.message.content, Triggers, carac="trigger", sensi=0.7)
    if not trigs:
        await ctx.send("Désolé, je n'ai pas compris 🤷‍♂️")
        return

    trig = trigs[0][0]
    seq = Reactions.query.get(trig.reac_id).reponse

    etapes = seq.split(MARK_AND)
    for rep in etapes:
        if MARK_OR in rep:                              # Si plusieurs possiblités :
            rep = random.choice(rep.split(MARK_OR))         # Choix random

        if rep.startswith(MARK_REACT):                  # Réaction
            react = rep.lstrip(MARK_REACT)
            emoji = tools.emoji(ctx, react) or react        # Si custom emoji : objet Emoji, sinon le codepoint de l'emoji direct
            await ctx.message.add_reaction(emoji)

        elif rep.startswith(MARK_CMD):                  # Commande
            ctx.message.content = rep.replace(MARK_CMD, ctx.bot.command_prefix)
            ctx = await ctx.bot.process_commands(ctx.message)

        else:                                           # Texte / média
            await ctx.send(rep)
