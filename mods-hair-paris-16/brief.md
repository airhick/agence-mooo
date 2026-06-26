# BRIEF CRÉATIF — mod's hair Paris 16

## 1. Concept & positionnement
« **Le studio, pas la vitrine** » — On abandonne le discours de marque mondialisé pour offrir une expérience radicalement locale : un salon de coiffure-studio du 16ᵉ arrondissement, où l’ADN du « coiffé-décoiffé » rencontre la précision architecturale d’un atelier contemporain. On ne vend pas une collection saisonnière, on ouvre la porte du 156 Avenue Victor Hugo avec une transparence totale — plans, gestes, lumière réelle — pour ceux qui cherchent un coiffeur, pas une publicité.

## 2. Direction artistique
**Minimalisme optique, chaleur matérielle** — Un parti pris esthétique tiré directement des photos réelles du salon : l’espace est structuré par un dialogue entre la froideur lumineuse des miroirs LED et des surfaces chromées, et la présence apaisante du bois naturel clair. On traduit cette tension en design : la page respire comme un plan d’architecte élégant — fonds blancs purs, noirs d’encre typographique, zones de respiration généreuses — mais on réchauffe par la matière : textures de bois photographiées en macro, ombres portées douces, et une séquence visuelle qui imite la progression physique dans le salon (de l’entrée sobre au fauteuil, puis au bac). L’ambition : que le site soit aussi net et précis qu’un miroir sans traces, et aussi tangible que le grain du bois sous la main.

## 3. Palette
Ancrée dans les teintes réelles du salon du 16ᵉ, sans concession générique.

| Rôle | Hex | Nom | Usage |
|------|-----|-----|-------|
| Encre | `#0F0F0C` | Noir absolu | Textes, logos, filets fins |
| Fond principal | `#FBFAF7` | Blanc coquille | Arrière-plan, respirations |
| Accent structurel | `#D4C5B2` | Bois de hêtre | Blocs de fond chauds, séparateurs, hover |
| Métal froid | `#8A9597` | Acier brossé | Icônes, bordures, éléments UI secondaires |
| Signal | `#2B3A3C` | Vert ardoise profond | Boutons CTA, liens, accent fort (tiré des plantes d’intérieur visibles en photo) |
| Lumière | `#FFFFFF` | Blanc pur | Cartes services, highlights, contraste maximal |

Fond dominant clair pour incarner la luminosité vive du salon et laisser respirer la typographie ; l’accent vert ardoise remplace un banal noir pour les appels à l’action, injectant une note organique dans l’univers froid chromé/minéral.

## 4. Ton éditorial
**Sobre, direct, adulte** — On s’adresse à une clientèle du 16ᵉ qui sait ce qu’elle veut. Pas de superlatifs, pas de complicité forcée. Un français précis, presque factuel, avec juste assez d’élégance pour rappeler qu’on est Avenue Victor Hugo. Les phrases décrivent le geste, le service, le lieu. On tutoie avec parcimonie, on vouvoie sur les pages de service. Aucun jargon « beauté » creux — on parle coupe, couleur, technique, temps, soin.

## 5. Accroche héro
*(Titre display en Instrument Serif, sur fond blanc coquille avec une photo pleine largeur du salon réel : plan large de l’espace vide après la fermeture, lumière LED allumée, bois et chromes nets.)*

**Titre :** Vos cheveux ont rendez-vous Avenue Victor Hugo.

**Sous-titre :** Studio moderne au cœur du 16ᵉ — coupes, balayage Air Touch, glossing et soins Kérastase en salon lumineux. Prenez place, on s’occupe du reste.

## 6. Sections
*Chaque section répond aux lacunes identifiées par l’audit : informations locales, offre concrète, réservation fluide, photos réelles, adresse et horaires explicites.*

---

### A. Le studio
*Titre :* 156 Avenue Victor Hugo, Paris 16
*Contenu :* Dans un écrin de bois clair et de lumière froide, à deux pas de la place Victor Hugo, notre salon incarne l’esprit studio cher à mod’s hair depuis 45 ans : des gestes maîtrisés, un décor qui s’efface devant le savoir-faire, et cette science du « coiffé-décoiffé » qui ne se démode pas. Une équipe de [nombre] coiffeurs-stylistes vous reçoit du mardi au samedi, sur rendez-vous ou au dernier moment.

### B. La carte des services
*Titre :* Nos gestes & signatures
*Contenu :* [Liste en deux colonnes : une colonne courte « Coupes & Coiffage », une colonne « Couleurs & Soins » avec des intitulés réels — coupe femme, coupe homme, brushing, balayage Air Touch, glossing, extensions, soin profond Kérastase, rituel sur mesure. Chaque service est accompagné d’un prix de base ou d’une fourchette indiquée clairement, et d’une durée estimée.]

### C. Le regard de l’équipe
*Titre :* Un salon, des mains
*Contenu :* Galerie plein écran en carrousel lent — photos réelles de l’équipe au travail, portraits posés devant les miroirs LED, clichés de textures de cheveux travaillées (balayage lumière, boucles, brushing). Pas de mannequins de stock. Chaque photo est légendée d’un prénom et d’une spécialité. Le visiteur voit qui coiffera ses cheveux.

### D. Prendre place
*Titre :* Votre fauteuil vous attend
*Contenu :* Bloc de réservation intégré (widget Planity ou Booksy) ou bouton proéminent « Réserver en ligne » renvoyant vers le partenaire de prise de rendez-vous du salon, avec le numéro de téléphone cliquable `01 47 27 76 83` en alternative directe. Texte de réassurance : « Téléphone ou en ligne, votre réservation est immédiate. Ouvert du mardi au samedi de 9h30 à 19h30 [vérifier horaires exacts]. Station de métro Victor Hugo à 200 mètres. »

### E. L’adresse et les horaires (pied de page permanent)
*Titre :* mod’s hair Paris 16
*Contenu :* `156 Avenue Victor Hugo, 75116 Paris` — `01 47 27 76 83` — `contact@modshair.com`. Horaires listés jour par jour. Lien Google Maps pour itinéraire. Ce bloc est présent en footer fixe sur toutes les pages, plus une mention en haut à droite dans la navigation.

## 7. Signature visuelle
**Le miroir-cadre** — Chaque image du salon (photos réelles, galerie équipe, portrait produit) est présentée dans un conteneur blanc bordé d’un mince filet acier brossé de `1px`, évoquant le miroir lumineux du salon. Au hover, le filet s’éclaire légèrement (transition `box-shadow` vers une lueur froide), comme un jeu de LED autour d’une glace. Sur les photos noir et blanc, une texture subtile de grain de bois apparaît en surimpression des ombres (effet de blending mode `multiply` avec une photo macro de la matière du salon), ancrant chaque visuel dans le lieu réel.

**Animation typographique** — Sur le titre principal, Instrument Serif s’affiche avec un effet de révélation caractère par caractère (animation `clip-path` ou `overflow`), rythme lent mais sûr, comme un peigne qui trace une raie parfaite. Pas d’effet superflu ailleurs : l’animation épouse le geste coiffant.