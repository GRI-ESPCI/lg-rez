import random
import traceback
import datetime

from discord import Embed
from discord.ext import commands

import tools
from bdd_connect import db, Joueurs


class Annexe(commands.Cog):
    """Annexe - commandes annexes aux usages divers"""
    
    current_embed = None

    @commands.command()
    async def roll(self, ctx, *, XdY):
        """Lance un ou plusieurs dés
        
        <XdY> dés à lancer + modifieurs, au format {XdY + XdY + ... + Z - Z ... } avec X le nombre de dés, Y le nombre de faces et Z les modifieurs (constants).
        
        Ex. !roll 1d6           -> lance un dé à 6 faces
            !roll 1d20 +3       -> lance un dé à 20 faces, ajoute 3 au résultat
            !roll 1d20 + 2d6 -8 -> lance un dé 20 plus deux dés 6, enlève 8 au résultat
        """
        dices = XdY.replace(' ','').replace('-','+-').split('+')        # "1d6 + 5 - 2" -> ["1d6", "5", "-2"]
        r = ""
        s = 0
        try:
            for dice in dices:
                if 'd' in dice:
                    nb, faces = dice.split('d', maxsplit=1)
                    for i in range(int(nb)):
                        v = random.randrange(int(faces)) + 1
                        s += v
                        r += f" + {v}₍{tools.sub_chiffre(int(faces), True)}₎"
                else:
                    v = int(dice)
                    s += v
                    r += f" {'-' if v < 0 else '+'} {abs(v)}"
            r += f" = {tools.emoji_chiffre(s, True)}"
        except Exception:
            await ctx.send(f"Pattern non reconu. Utilisez {tools.code('!help roll')} pour plus d'informations.")
        else:
            await ctx.send(r[3:])


    @commands.command(aliases=["cf", "pf"])
    async def coinflip(self, ctx):
        """Renvoie le résultat d'un tirage à Pile ou Face (aléatoire)

        Pile je gagne, face tu perds.
        """
        await ctx.send(random.choice(["Pile", "Face"]))


    @commands.command()
    async def ping(self, ctx):
        """Envoie un ping au bot

        Pong
        """
        delta = datetime.datetime.utcnow() - ctx.message.created_at
        await ctx.send(f"!pong ({delta.total_seconds():.2}s)")


    @commands.command()
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def embed(self, ctx, key=None, *, val=None):
        """J'adore les docstrings"""
        
        if val is None:
            val = Embed.Empty
            
        elif key == "color":        # Conversion couleur en int
            try:
                val = eval(val.replace("#", "0x"))
                if not isinstance(val, int):
                    raise ValueError()
            except Exception:
                await ctx.send("Couleur invalide")
                return
                
        emb = self.current_embed
        
        # !do ctx.send(embed=discord.Embed(title="Mort de Clément Neytard", color=0xff0000).set_footer(text="- Votes contre Clément Neytard : Robert, Roberta, Roberto, Cestsuperlong, Jailaflemme, Yaunelimiteenplus, Elle Estpas SiGrande, Jojo, Ouistiti, Nombril Velu, Mais Pourquoi, Corbeau \n- Votes contre Laetitia Furno : Quelqu'un").set_image(url="https://imgup.nl/images/2020/06/06/chart.png").set_author(name="Bûcher du jour",icon_url=tools.emoji(ctx,"bucher").url))
                
        d = {"footer": ("set_footer", "text"),              # d[key] = (<met>, <attr>)
             "footer_icon": ("set_footer", "icon_url"),
             "image": ("set_image", "url"),
             "thumb": ("set_thumbnail", "url"),
             "author_url": ("set_author", "url"),
             "author_icon": ("set_author", "icon_url"),
            }
            
            
        if not emb:
            if key == "create" and val:
                emb = Embed(title=val)
            else:
                await ctx.send(f"Pas d'embed en préparation. {tools.code('!embed create <titre>')} pour en créer un.")
                return

        elif key in ["title", "description", "url", "color"]:      # Attributs modifiables directement
            setattr(emb, key, val)
            
        elif key in d:                                      # Attributs à modifier en appelant une méthode
            getattr(emb, d[key][0])(**{d[key][1]: val})         # emb.<met>(<attr>=val) 

        elif key == "author":                               # Cas particulier
            emb.set_author(name=val) if val else emb.remove_author()

        elif key == "field":                                # Cas encore plus particulier
            i_max = len(emb.fields)         # N fields ==> i_max = N+1
            try:
                i, skey, val = val.split(" ", maxsplit=2)
                i = int(i)
                if i < 0 or i > i_max:
                    await ctx.send("Numéro de field invalide")
                    return
                if skey not in ["name", "value", "delete"]:
                    raise ValueError()
            except Exception:
                await ctx.send("Syntaxe invalide")
                return
                
            if i == imax:
                if skey == "name":
                    emb.add_field(name=val or Embed.Empty, value="Valeur")
                elif skey == "value":
                    emb.add_field(value=val or Embed.Empty, name="Nom")
                # emb.add_field(*, name, value, inline=True)

            else:
                if skey in ["name", "value"]:
                    emb.set_field_at(i, **{skey:val or Embed.Empty})
                else:
                    emb.remove_field(i)
                # emb.set_field_at(i, *, name, value, inline=True)    
                
        elif key == "delete":
            await ctx.send(f"Supprimé. {tools.code('!embed create <titre>')} pour en créer un.")
            
        elif key == "create":
            await ctx.send(f"Déjà un embed en cours de création. Utiliser {tools.code('!embed delete')} pour le supprimer.")
            
        else:
            await ctx.send(f"Option {key} incorrecte : utiliser {tools.code('!help embed')} pour en savoir plus.")
            return

        # insert_field_at(index, *, name, value, inline=True)
        # Inserts a field before a specified index to the embed.
        
        # clear_fields()
        # Removes all fields from this embed.

        # if val == "preview":
        
        await ctx.send("Embed en préparation", embed=emb)
        await ctx.send(f"Utiliser {tools.code('!embed preview')} pour prévisualiser l'embed.")        
        
        
        
        
        self.current_embed = emb
        




    @commands.command(enabled=False)
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def test(self, ctx, *, arg):
        """Test : test !"""

        # arg = tools.command_arg(ctx)    # Arguments de la commande (sans le !test) --> en fait c'est faisable nativement, zrtYes
        auteur = ctx.author.display_name
        salon = ctx.channel.name if hasattr(ctx.channel, "name") else f"DMChannel de {ctx.channel.recipient.name}"
        serveur = ctx.guild.name if hasattr(ctx.guild, "name") else "(DM)"
        # pref = ctx.prefix
        # com = ctx.command
        # ivkw = ctx.invoked_with

        await tools.log(ctx, "Alors, ça log ?")

        await ctx.send(tools.code_bloc(
            f"arg = {arg}\n"
            f"auteur = {auteur}\n"
            f"salon = {salon}\n"
            f"serveur = {serveur}"
        ))


    @commands.command(enabled=False)
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def testreact(self, ctx, *reacts):
        message = await ctx.send(tools.code_bloc(f"REACT TO THAT!\nReacts: {' - '.join(reacts)}"))
        react = await tools.wait_for_react_clic(ctx.bot, message, ["🔴", "🟠", "🟢"])
        await ctx.send(tools.code_bloc(f"REACTED : {react}"))


    @commands.command(enabled=False)
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def testbdd(self, ctx):
        """Test BDD"""

        tous = Joueurs.query.all()
        ret = '\n - '.join([u.nom for u in tous])
        message = await ctx.send(tools.code_bloc(f"Liste des joueurs :\n - {ret}"))


    @commands.command(enabled=False)
    @commands.check_any(commands.check(lambda ctx:ctx.message.webhook_id), commands.has_role("MJ"))
    async def rename(self, ctx, id: int, nom: str):
        """Renommer quelqu'un à partir de son ID"""

        try:
            u = Joueurs.query.filter_by(discord_id=id).one()
        except:
            await ctx.send(tools.code_bloc(f"Cible {id} non trouvée\n{traceback.format_exc()}"))
        else:
            oldnom = u.nom
            u.nom = nom
            db.session.commit()
            await ctx.send(tools.code_bloc(f"Joueur {oldnom} renommé en {nom}."))


    @commands.command(enabled=False)
    @tools.private
    async def private_test(self, ctx, *, arg):
        """Test PRIVÉ"""

        # arg = tools.command_arg(ctx)    # Arguments de la commande (sans le !test) --> en fait c'est faisable nativement, zrtYes
        auteur = ctx.author.display_name
        salon = ctx.channel.name if hasattr(ctx.channel, "name") else f"DMChannel de {ctx.channel.recipient.name}"
        serveur = ctx.guild.name if hasattr(ctx.guild, "name") else "(DM)"
        # pref = ctx.prefix
        # com = ctx.command
        # ivkw = ctx.invoked_with

        await tools.log(ctx, "Alors, ça log ?")

        await ctx.send(tools.code_bloc(
            f"arg = {arg}\n"
            f"auteur = {auteur}\n"
            f"salon = {salon}\n"
            f"serveur = {serveur}"
        ))
