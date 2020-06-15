import datetime

from discord.ext import commands

from blocs import webhook
import tools
from bdd_connect import db, Taches


def execute(tache):
    """Exécute la tâche <tache> (objet BDD Taches) : appel le webhook et supprime l'entrée en base"""
    
    webhook.send(tache.commande, source="tp")
    db.session.delete(tache)
    db.session.commit()


class GestionTaches(commands.Cog):
    """GestionTaches - planification et exécution de tâches"""

    @commands.command()
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def taches(self, ctx):
        """Liste les tâches en attente (COMMANDE MJ)

        Affiche les commandes en attente d'exécution (dans la table tâche) et le timestamp d'exécution associé.
        """

        taches = Taches.query.order_by(Taches.timestamp).all()
        LT = "\n".join([f"{str(tache.id).ljust(5)} {tache.timestamp.strftime('%d/%m/%Y %H:%M:%S')}    {tache.commande}" for tache in taches])
        
        await ctx.send(tools.code_bloc(("Tâches en attente : \n\nID    Timestamp              Commande\n"
                                        f"{'-'*80}\n{LT}\n\n"
                                        "Utilisez !cancel <ID> pour annuler une tâche.") if LT else "Aucune tâche en attente."))

                                        
                                        
    @commands.command(aliases=["doat"])
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def planif(self, ctx, quand, *, commande):
        """Planifie une tâche au moment voulu (COMMANDE MJ)
        
        - <quand> : format [<J>/<M>[/<AAAA>]-]<H>:<M>[:<S>], avec <J> (jours), <M> (mois), <AAAA> (année sur 4 chiffres), <H> (heures) et <M> (minutes) des entiers et <S> (secondes) un entier ou un flottant, optionnel (défaut : 0). 
        La date est optionnelle (défaut : date du jour). Si elle est précisée, elle doit être séparée de l'heure par un tiret et l'année peut être omise (défaut : année actuelle) ;
        
        - <commande> : commande à exécuter (commençant par un !). La commande sera exécutée PAR UN WEBHOOK et DANS LE CHAN #logs : toutes les commandes qui sont liées au joueur ou réservées au chan privé sont à proscrire (ou doivent a minima être précédées de !doas <cible>)

        Cette commande repose sur l'architecture en base de données, ce qui garantit l'exécution de la commande même si le bot plante entre temps.
        Si le bot est down à l'heure d'exécution prévue, la commande sera exécutée dès le bot de retour en ligne.
        Si la date est dans le passé, la commande est exécutée immédiatement.

        Ex. : - !planif 13/06/2020-10:00 !open maire
              - !planif 13/06-10:00 !open maire
              - !planif 18:00 !close maire
        """
        
        now = datetime.datetime.now()

        if "/" in quand:            # Date précisée
            date, time = quand.split("-")
            J, MA = date.split("/", maxsplit=1)
            day = int(J)
            if "/" in MA:           # Année précisée
                M, A = MA.split("/")
                month = int(M)
                year = int(A)
            else:
                month = int(MA)
                year = now.year
            date = datetime.date(year=year, month=month, day=day)
        else:
            date = now.date()
            time = quand
            
        H, MS = time.split(":", maxsplit=1)
        hour = int(H)
        if ":" in MS:               # Secondes précisées
            M, S = MS.split(":")
            minute = int(M)
            second = int(S)
        else:
            minute = int(MS)
            second = 0
        time = datetime.time(hour=hour, minute=minute, second=second)
        
        ts = datetime.datetime.combine(date, time)
        message = await ctx.send(f"Planifier {tools.code(commande)} pour le {tools.code(ts.strftime('%d/%m/%Y %H:%M:%S'))} ?")
        
        if await tools.yes_no(ctx.bot, message):
            tache = Taches(timestamp=ts, commande=commande)
            
            db.session.add(tache)                                                       # Enregistre la tâche en BDD
            db.session.commit()
            
            TH = ctx.bot.loop.call_later((ts - now).total_seconds(), execute, tache)    # Programme la tâche
            ctx.bot.tasks[tache.id] = TH
            await ctx.send("Fait.")
            
        else:
            await ctx.send("Mission aborted.")


    @commands.command(aliases=["retard", "doin"])
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def delay(self, ctx, duree, *, commande):
        """Exécute une commande après XhYmZs (COMMANDE MJ)

        - <duree> : format [<X>h][<Y>m][<Z>s], avec <X> (heures) et <Y> (minutes) des entiers et <Z> (secondes) un entier ou un flottant. Chacune des trois composantes est optionnelle, mais au moins une d'entre elle doit être présente ;
        - <commande> : commande à exécuter (commençant par un !). La commande sera exécutée PAR UN WEBHOOK et DANS LE CHAN #logs : toutes les commandes qui sont liées au joueur ou réservées au chan privé sont à proscrire (ou doivent a minima être précédées de !doas <cible>)

        Cette commande repose sur l'architecture en base de données, ce qui garantit l'exécution de la commande même si le bot plante entre temps.
        Si le bot est down à l'heure d'exécution prévue, la commande sera exécutée dès le bot de retour en ligne.

        Ex. : - !delay 2h !close maire
              - !delay 1h30m !doas @moi !vote Yacine Oussar
        """

        secondes = 0
        try:
            if "h" in duree.lower():
                h, duree = duree.split("h")
                secondes += 3600*int(h)
            if "m" in duree.lower():
                m, duree = duree.split("m")
                secondes += 60*int(m)
            if "s" in duree.lower():
                s, duree = duree.split("s")
                secondes += float(s)
        except Exception as e:
            raise commands.BadArgument("<duree>") from e
            
        if duree or not secondes:
            raise commands.BadArgument("<duree>")
            
        ts = datetime.datetime.now() + datetime.timedelta(seconds=secondes)
        tache = Taches(timestamp=ts, commande=commande)
        
        db.session.add(tache)                                       # Enregistre la tâche en BDD
        db.session.commit()
        
        TH = ctx.bot.loop.call_later(secondes, execute, tache)      # Programme la tâche
        ctx.bot.tasks[tache.id] = TH
        
        await ctx.send(f"Commande {tools.code(commande)} planifiée pour le {tools.code(ts.strftime('%d/%m/%Y %H:%M:%S'))}")
        
        
    @commands.command()
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def cancel(self, ctx, id):
        """Annule une tâche planifiée (COMMANDE MJ)
        
        <id> ID de la tâche à annuler (accessible via !taches)
        """
        
        id = int(id)
        tache = Taches.query.get(id)
        if tache:
            message = await ctx.send(f"Annuler la tâche {tools.code(tache.timestamp.strftime('%d/%m/%Y %H:%M:%S'))} > {tools.code(tache.commande)} ?")
            if await tools.yes_no(ctx.bot, message):
                ctx.bot.tasks[id].cancel()
                db.session.delete(tache)
                db.session.commit()
                await ctx.send("Tâche annulée.")
            else:
                await ctx.send("Mission aborted.")
        else:
            await ctx.send(f"Tâche {id} non trouvée.")