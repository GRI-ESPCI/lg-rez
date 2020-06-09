import datetime

from discord.ext import commands
from sqlalchemy.sql.expression import and_, or_, not_

from bdd_connect import db, Actions, BaseActions
import tools
from blocs import bdd_tools


async def get_actions(quoi, trigger, heure=None):
    """Renvoie la liste des actions déclenchées par trigger, dans le cas ou c'est temporel, les actions possibles à heure (objet de type time)
    """

    if trigger == "temporel":
        if not heure:
            raise ValueError("Merci de préciser une heure......\n https://tenor.com/view/mr-bean-checking-time-waiting-gif-11570520")

        if quoi == "open":
            criteres = and_(Actions.trigger_debut == trigger, Actions.heure_debut == heure,
                            Actions.charges != 0)    # charges peut être None, donc pas > 0
        elif quoi == "close":
            criteres = and_(Actions.trigger_fin == trigger, Actions.heure_fin == heure,
                            Actions._decision != None)
        elif quoi == "remind":
            criteres = and_(Actions.trigger_fin == trigger, Actions.heure_fin == heure,
                            Actions._decision == "rien")

    else:
        if quoi == "open":
            criteres = and_(Actions.trigger_debut == trigger, Actions.charges != 0)
        elif quoi == "close":
            criteres = and_(Actions.trigger_fin == trigger, Actions._decision != None)
        elif quoi == "remind":
            criteres = and_(Actions.trigger_fin == trigger, Actions._decision == "rien")


    actions = Actions.query.filter(criteres).all()

    if not actions:
        return []
    else:

        if quoi == "open":
            act_decrement = [action for action in actions if action.cooldown > 0]
            if act_decrement:
                for act in act_decrement:
                    bdd_tools.modif(act, "cooldown", act.cooldown - 1)

                db.session.commit()

        return([action for action in actions if action.cooldown == 0])
