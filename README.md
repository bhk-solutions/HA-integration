Dans Home Assistant :

Menu latéral → Paramètres

Modules complémentaires

Boutique des modules complémentaires

Cherche : Terminal & SSH (addon officiel)

Installe-le

Lance-le

Clique ** OPEN WEB UI **


### Pré-requis passerelle

Chaque passerelle doit répondre au broadcast UDP de découverte (`DISCOVER_GATEWAY` sur le port 50000) avec un JSON sur le port 50002 :

```
{
  "Device": "NETWORK-GATEWAY",
  "MAC": "AA:BB:CC:DD:EE:FF",
  "IP": "192.168.1.42",
  "Type": "UDP-BRIDGE",
  "Version": "1.0.1"
}
```

Les clés ne sont pas sensibles à la casse.

Une phase de découverte dure ~30 secondes : pendant ce laps de temps, toutes les passerelles répondant sont collectées. Au moment de l'ajout, vous pouvez sélectionner une passerelle précise ou cocher l'option « Ajouter les autres » afin que Home Assistant crée automatiquement les entrées restantes à partir de cette même session.

Après l'appairage, Home Assistant écoute en permanence les messages UDP entrants (port 50002) pour créer/mettre à jour les appareils. Aucun WebSocket n'est requis.

#### Format des messages UDP vers Home Assistant

##### Lumières

1. **Inscription d'un appareil (création de l'entité)**

   ```json
   {
     "type": "light_register",
     "unique_id": "AA1122FF",        // identifiant unique de l'appareil
     "name": "Lampe Salon",
     "gateway_mac": "AA:BB:CC:DD:EE:FF" // optionnel, permet d'associer la lampe à la passerelle
   }
   ```

   L'envoi de ce message crée (ou met à jour) l'entité lumière correspondante dans Home Assistant. `unique_id` doit rester stable dans le temps et doit être unique par appareil.

2. **Mise à jour d'état d'un appareil**

   ```json
   {
     "type": "light_state",
     "unique_id": "AA1122FF",
     "state": "ON" // ON ou OFF (insensible à la casse)
   }
   ```

   Ce message met à jour l'état de la lumière dans Home Assistant. Envoyez `"state": "OFF"` pour l'éteindre.

##### Volets roulants

1. **Inscription d'un volet**

   ```json
   {
     "type": "cover_register",
     "unique_id": "VR445566",
     "name": "Volet Salon",
     "gateway_mac": "AA:BB:CC:DD:EE:FF"
   }
   ```

   Comme pour les lumières, ce message crée l'entité cover correspondante.

2. **Mise à jour d'état / position**

   ```json
   {
     "type": "cover_state",
     "unique_id": "VR445566",
     "state": "OPEN",        // OPEN, CLOSED, OPENING, CLOSING… (insensible à la casse)
     "position": 42            // optionnel, 0-100
   }
   ```

   `state` renseigne l'état logique (ou `OPENING`/`CLOSING`), `position` met à jour la position en pourcentage.

#### Commandes envoyées depuis Home Assistant

Lorsque l'utilisateur interagit avec l'entité, Home Assistant envoie un datagramme UDP au gateway (`IP` découverte, port 50000 par défaut) contenant :

```json
{
  "type": "light_command",
  "unique_id": "AA1122FF",
  "state": "ON" // ou OFF
}
```

Les volets reçoivent des commandes similaires :

```json
{
  "type": "cover_command",
  "unique_id": "VR445566",
  "command": "OPEN" // OPEN ou CLOSE
}
```

Pour une position donnée (0-100%), encodez-la toujours dans `command` (même schéma JSON) :

```json
{
  "type": "cover_command",
  "unique_id": "VR445566",
  "command": "P:30" // ici 30%
}
```

Le gateway peut ainsi relayer tel quel la commande.

> Pour la phase de test, l'intégration accepte les messages provenant de n'importe quelle source. Un filtrage par passerelle sera ajouté plus tard.


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
