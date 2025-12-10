Dans Home Assistant :

Menu latéral → Paramètres

Modules complémentaires

Boutique des modules complémentaires

Cherche : Terminal & SSH (addon officiel)

Installe-le

Lance-le

Clique ** OPEN WEB UI **


### Pré-requis MQTT

Toujours via **Modules complémentaires → Boutique**, installe l'add-on **Mosquitto broker** (officiel).

1. Active « Démarrer au démarrage » et « Recréer automatiquement ».
2. Démarre l'add-on Mosquitto et vérifie dans les logs qu'il écoute sur le port 1883.
3. Dans Paramètres → Appareils & Services, vérifie que l'intégration MQTT est configurée (elle se configure automatiquement après l'installation de l'add-on).

Sans ce broker MQTT, l'intégration BHK refusera de démarrer.


Or just 
https://www.hacs.xyz/docs/use/download/download/#to-download-hacs



Va dans HACS à gauche

→ En haut à droite (3 points)

→ Dépôts personnalisés


Ajoute ton repo :
Dépôt: https://github.com/bhk-solutions/HA-integration
type : intégration


Maintenant, HACS te liste BHK Integration

Clique dessus → Install

Redémarre HA
