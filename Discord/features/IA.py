import random

from discord.ext import commands

import tools
from blocs import bdd_tools
from bdd_connect import db, Triggers, Reactions


# Marqueurs de séparation du mini-langage des séquences-réactions
MARK_OR = ' <||> '
MARK_THEN = ' <&&> '
MARK_REACT = '<::>'
MARK_CMD = '<!!>'



# Construction d'une séquence-réaction par l'utilisateur
async def build_sequence(ctx):
    reponse = ""
    fini = False
    while not fini:
        message = await ctx.send("Réaction du bot : prochain message/commande/média, ou réaction à ce message")
        ret = await tools.wait_for_react_clic(ctx.bot, message, process_text=True, trigger_all_reacts=True, trigger_on_commands=True)
        if isinstance(ret, str):
            if ret.startswith(ctx.bot.command_prefix):      # Commande
                reponse += MARK_CMD + ret.lstrip(ctx.bot.command_prefix)
            else:                                           # Texte / média
                reponse += ret
        else:                                               # React
            reponse += MARK_REACT + ret.name

        message = await ctx.send("▶ Puis / 🔀 Ou / ⏹ Fin ?")
        ret = await tools.wait_for_react_clic(ctx.bot, message, emojis={"▶":MARK_THEN, "🔀":MARK_OR, "⏹":False})
        if ret:
            reponse += ret          # On ajoute la marque OR ou THEN à la séquence
        else:
            fini = True

    return reponse



class GestionIA(commands.Cog):
    """GestionIA - Commandes relatives à l'IA (réponses automatiques du bot)"""

    @commands.command()
    @tools.private
    async def stfu(self, ctx, force=None):
        """Active/désactive la réponse automatique du bot sur ton channel privé

        [force=start/stop] permet de forcer l'activation / la désactivation. 
        Sans argument, la commande agit comme un toggle (active les réactions si désactivées et vice-versa).

        N'agit que sur les messages classiques envoyés dans le channel : les commandes restent reconnues.
        Si vous ne comprenez pas le nom de la commande, demandez à Google.
        """
        id = ctx.channel.id
        
        if force in [None, "start"] and id not in ctx.bot.in_stfu:
            ctx.bot.in_stfu.append(id)
            await ctx.send("Okay, je me tais ! Tape !stfu quand tu voudras de nouveau de moi :cry:")

        elif force in [None, "stop"] and id in ctx.bot.in_stfu:
            ctx.bot.in_stfu.append(id)
            await ctx.send("Ahhh, ça fait plaisir de pouvoir reparler !")
            
        else:       # Quelque chose d'autre que start/stop précisé après !stfu : bot discret
            if id in ctx.bot.in_stfu:
                ctx.bot.in_stfu.remove(id)
            else:
                ctx.bot.in_stfu.append(id)


    @commands.command()
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def addIA(self, ctx, *, triggers=None):
        """Ajoute au bot une règle d'IA : mots ou expressions déclenchant une réaction (COMMANDE MJ)

        [trigger] mot(s), phrase(s), ou expression(s) séparées par des points-virgules ou sauts de lignes
        Dans le cas où plusieurs expressions sont spécifiées, toutes déclencheront l'action demandée.
        """
        if not triggers:
            await ctx.send("Mots/expressions déclencheurs (non sensibles à la casse / accents), séparés par des points-virgules ou des sauts de ligne :")
            mess = await tools.wait_for_message(ctx.bot, check=lambda m:m.channel == ctx.channel and m.author != ctx.bot.user)
            triggers = mess.content

        triggers = triggers.replace('\n', ';').split(';')
        triggers = [tools.remove_accents(s).lower().strip() for s in triggers]
        await ctx.send(f"Triggers : `{'` – `'.join(triggers)}`")

        reponse = await build_sequence(ctx)

        await ctx.send(f"Résumé de la séquence : {tools.code(reponse)}")
        async with ctx.typing():
            reac = Reactions(reponse=reponse)
            db.session.add(reac)
            db.session.flush()          # On "fait comme si" on commitait l'ajout de reac, ce qui calcule read.id (autoincrément)

            trigs = [Triggers(trigger=trigger, reac_id=reac.id) for trigger in triggers]
            db.session.add_all(trigs)
            db.session.commit()
        await ctx.send(f"Règle ajoutée en base.")
        

    @commands.command()
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def listIA(self, ctx, trigger=None, sensi=0.5):
        """Liste les règles d'IA actuellement reconnues par le bot (COMMANDE MJ)

        [trigger] (optionnel) mot/expression permettant de filter et trier les résultats. SI TRIGGER FAIT PLUS D'UN MOT, IL DOIT ÊTRE ENTOURÉ PAR DES GUILLEMETS !
        Si trigger est précisé, les triggers sont détectés avec une sensibilité [sensi] (ratio des caractères correspondants, entre 0 et 1).
        """
        async with ctx.typing():
            if trigger:
                trigs = await bdd_tools.find_nearest(trigger, table=Triggers, carac="trigger", sensi=sensi, solo_si_parfait=False)
                if not trigs:
                    await ctx.send(f"Rien trouvé, pas de chance (sensi = {sensi})")
                    return
            else:
                raw_trigs = Triggers.query.order_by(Triggers.id).all()          # Trié par date de création
                trigs = list(zip(raw_trigs, [None]*len(raw_trigs)))             # Mise au format (trig, score)

            reacts_ids = []     # IDs des réactions associées à notre liste de triggers
            [reacts_ids.append(id) for trig in trigs if (id := trig[0].reac_id) not in reacts_ids]    # Pas de doublons, et reste ordonné
            
            def nettoy(s):      # Abrège la réponse si trop longue et neutralise les sauts de ligne / rupture code_bloc, pour affichage
                s = s.replace('\r\n', '\\n').replace('\n', '\\n').replace('\r', '\\r').replace("```", "'''")
                if len(s) < 75:
                    return s
                else: 
                    return s[:50] + " [...] " + s[-15:]

            L = ["- " + " – ".join([(f"({float(score):.2}) " if score else "") + trig.trigger       # (score) trigger - (score) trigger ...
                                    for (trig, score) in trigs if trig.reac_id == id]).ljust(50)        # pour chaque trigger
                 + f" ⇒ {nettoy(Reactions.query.get(id).reponse)}"                                 # ⇒ réponse
                 for id in reacts_ids]                                                                  # pour chaque réponse
                 
            r = "\n".join(L) + "\n\nPour modifier une réaction, utiliser !modifIA <trigger>."
            
        [await ctx.send(tools.code_bloc(mess)) for mess in tools.smooth_split(r)]       # On envoie, en séparant en blocs de 2000 caractères max
        

    @commands.command()
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
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
                r += f"\nMarqueur OU : {tools.code(MARK_OR)}, Marqueur ET : {tools.code(MARK_THEN)}, Marqueur REACT : {tools.code(MARK_REACT)}, Marqueur CMD : {tools.code(MARK_CMD)}"
                mess = await ctx.send(r + "\nNouvelle séquence :")
                reponse = (await tools.wait_for_message(ctx.bot, lambda m:m.channel == ctx.channel and m.author != ctx.bot.user)).content

            bdd_tools.modif(rep, "reponse", reponse)

        if not (MT or MR):      # Suppression
            db.session.delete(rep)
            for trig in trigs:
                db.session.delete(trig)

        db.session.commit()

        await ctx.send("Fini.")



# Exécute les règles d'IA en réaction à <message>
async def process_IA(bot, message):
    trigs = await bdd_tools.find_nearest(message.content, Triggers, carac="trigger", sensi=0.7)
    
    if trigs:       # Au moins un trigger trouvé à cette sensi
        trig = trigs[0][0]                                  # Meilleur trigger (score max)
        seq = Reactions.query.get(trig.reac_id).reponse     # Séquence-réponse associée

        for rep in seq.split(MARK_THEN):                    # Pour chaque étape :
            if MARK_OR in rep:                                  # Si plusieurs possiblités :
                rep = random.choice(rep.split(MARK_OR))             # On en choisit une random

            if rep.startswith(MARK_REACT):                      # Si réaction :
                react = rep.lstrip(MARK_REACT)
                emoji = tools.emoji(message, react) or react        # Si custom emoji : objet Emoji, sinon le codepoint de l'emoji direct
                await message.add_reaction(emoji)                   # Ajout de la réaction

            elif rep.startswith(MARK_CMD):                      # Si commande :
                message.content = rep.replace(MARK_CMD, bot.command_prefix)
                await bot.process_commands(message)                 # Exécution de la commande

            else:                                               # Sinon, texte / média :
                await message.channel.send(rep, tts=True)           # On envoie
                
    else:           # Aucun trigger trouvé à cette sensi
        c = message.content
        if c.lower().startswith(('dis ', 'dit ')) and len(c) > 4:
            mess = c[4:]
        elif c.lower().startswith(('di', 'dy')) and len(c) > 2:
            mess = c[2:]
        elif c.lower().startswith(('cri', 'cry', 'kri', 'kry')) and len(c) > 3:
            mess = tools.bold(c[3:].upper())
        else:    
            mess = "Désolé, je n'ai pas compris 🤷‍♂️"
            
        await message.channel.send(mess, tts=True)              # On envoie le texte par défaut / le di.../cri...
