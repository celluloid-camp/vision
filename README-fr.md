## Celluloid Vision

Celluloid Vision utilise deux technologies principales d'intelligence artificielle pour l'analyse vidéo: 

D'abord, MediaPipe, un framework open-source d'apprentissage automatique, assure la détection et le suivi des personnes et objets en temps réel. 
Il s'appuie sur l'architecture EfficientDet-Lite0 avec un backbone EfficientNet-Lite0, entraînée sur le dataset COCO contenant 1,5 million d'instances réparties en 80 catégories d'objets. 

Celluloid Vision implémente un système de box tracking qui combine l'inférence par réseaux de neurones avec des techniques classiques de vision par ordinateur : il extrait et suit des caractéristiques visuelles comme les coins à fort gradient à travers les images, les classifiant en éléments de premier plan et d'arrière-plan pour optimiser le suivi des objets. 

Ensuite, PySceneDetect permet d'identifier automatiquement les transitions et les coupes entre les scènes vidéo. 

L'application expose une API REST permettant le traitement asynchrone des vidéos avec un système de file d'attente, générant des résultats de détection au format JSON avec des données de suivi d'objets et des visualisations de timeline pour la plateforme celluloid.me.
