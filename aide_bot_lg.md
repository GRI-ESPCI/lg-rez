# Petit fichier d'aide vis à vis de la structure du code pour savoir quoi chercher ou en vue de modifications légères (non exhaustif) et protocol de MAJ

## start_bot.py

start_bot.py : à modifier depuis la griway (propre à chaque localisation du bot), contient notamment la définition de certains roles, la chambre MJ, la date de début, les réactions automatiques du bot, la restriction des emojis suricates aux MJ...

## dossier lgrez
Contient les fichiers du bot : 
ici seul __init__.py sera globalement modifié (sauf si on veut vraiment modifier le bot en profondeur) je pense
	
	- __init__.py : contient notamment la version du bot **à modifier avant de git push et d'update le bot**
			
	- bot.py : fonctionnement de base du bot
	- commands.py : définit globalement toutes les commandes
	- commons.py : définit des erreurs
	- config.py : fichier de configuration du serveur (roles, chan, emojis, variables utilisées par le bot)
	- __init__.py : contient notamment la version du bot **à modifier avant de git push et d'update le bot**
	- __main__.py : fait tourner le bot
	- server_structure.json : structure du serveur
	
## dossier bdd :
	setup et utilisation de la bdd, des réactions ..., je n'y ai jamais touché, meme chose que précédememnt probablement à ne pas modifier
			
## dossier blocs : 
	globalement encore fichiers de fonctionnement du blocs et de définitions de fonctions/commandes utiles à son bon fonctionnementle seul fichier qui pourra vraiment servir est tools.py : 
	- contient tout un tas de fonctions et outils utiles pour le bon fonctionnement des commandes, notamment comment les haros et candid sont gérés, comment les MJ sont pings, 
	- est assez utile pour comprendre les problèmes comme beaucoup de commandes ou fonctions y font appel,
	- sera en soit assez peu probablement modifié mais est assez utile pour régler les petits problèmes ou changer des commandes.
				
## dossier features : 
	parties la plus utilisées du code, contient toutes les défintions de commandes (avec une petite liste par fichier, pour plus d'informations se référer au code ou à la doc github directement)
			
	- actions-publiques.py : 
		contient globalement les commandes aux conséquences publiques : '/haro', '/candid', '/imprimeur', '/haroparmj' et leur fonctionnement
		
	- annexe.py : 
		commandes diverses qui ne se rangeaient pas ailleurs : '/roll', '/coinflip', '/ping', '/heure', '/akinator' (cassée pour le moment), '/xkcd'
		
	- chan.py : 
		commandes de création, ajout, suppression de membres : '/boudoir' (et toutes les annexes (list, create, invite ...), '/addhere', '/purge', '/mp' 
			
	- communications.py : 
		commandes de communications MJ -> Joueurs : '/send', '/plot', '/annoncemort', '/plot_int', '/lore', '/modif', '/post', '/embed'
			
	- gestions_actions.py : 
		commandes de liste, création, suppression, ouverture, fermeture d'actions : '/open_action', '/close_action' et autres commandes de gestions d'actions
			
	- gestions_ia.py : 
		diverses commandes d'appel et de gestions de l'ia notamment : '/stfu', '/fals', '/react', '/addIA', '/listIA', '/modifIA' 
			
	- informations.py : 
		commandes pour que les joueurs (ou les MJ) recoivent des informations sur le jeu : '/roles', '/camps', '/info', '/menu', '/morts', '/vivants', '/camps', '/rolede', '/quiest', '/actions'
			
	- __init__.py : 
		implémente les fonctions au bot (contrairement à tous les fichiers ici sera probablement pas à modifier)
			
	- inscription.py : 
		étapes préliminaires d'incriptions et quelques commandes associées ('/co' par exemple)
		
	- open_close.py : 
		ouverture/fermeture des votes et rappels : '/openvote', '/closevote', '/openactions' (en cours de réparation), '/closeactions' (en cours de réparation)
			
	- special.py : 
		commandes spéciales (méta-commandes et/ou expériementations) : '/panik', '/do', '/shell', '/co', '/doas' (potentielement en cours de réparation), '/setup', '/apropos', '/command' 
			
	- sync.py :
		gestion du lien avec le Gsheet et la BDD : '/sync', '/fillroles'
			 
	- taches.py : 
		planification, gestion des taches : '/taches', '/planif', '/planif_command' (en cours de réparation), '/planif_post', '/cancel'
			
	- voter_agir.py : 
		gestion des votes et actions : '/vote', '/votemaire', '/voteloups', '/action' 
		
		
## Mise à jour github et du bot : 
	- avant de commit et push, vérifier que la version dans __init__.py du dossier lgrez est bien la bonne (incrémmentée ou non au besoin)
	- créer un nouvelle Release sur Github avec le numéro de version correspondant le cas échéant
	- se connecter à la griway puis faire 'source env/bin/activate' dans '/home/lgrez' (à vérifier pour si l'user doit etre lgrez ou griuser)
	- puis 'pip install git+https://github.com/GRI-ESPCI/lg-rez@master'
