Dans Home Assistant :

Menu latéral → Paramètres

Modules complémentaires

Boutique des modules complémentaires

Cherche : Terminal & SSH (addon officiel)

Installe-le

Lance-le

Clique ** OPEN WEB UI **


### Pré-requis passerelle

Chaque passerelle doit exposer un serveur WebSocket et renvoyer les détails dans la réponse UDP de découverte :

```
{
  "Device": "NETWORK-GATEWAY",
  "MAC": "AA:BB:CC:DD:EE:FF",
  "IP": "192.168.1.42",
  "Type": "UDP-BRIDGE",
  "Version": "1.0.1",
  "ws_port": 50001,
  "ws_path": "/ws"
}
```

Les clés ne sont pas sensibles à la casse. `ws_port` et `ws_path` restent optionnels : s'ils sont absents, l'intégration utilise par défaut `50001` et `/ws`.

Au démarrage de Home Assistant, l'intégration ouvre automatiquement un client WS pour chaque passerelle enregistrée et écoute les états remontés. Aucune dépendance MQTT n'est nécessaire.


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
