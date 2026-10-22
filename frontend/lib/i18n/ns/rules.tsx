// Textes : page Règles et situations de jeu interactives. Le français est la référence ;
// l'anglais a les mêmes clés. Fichier en .tsx : les paragraphes gardent leur mise en
// valeur (<b>) sans être découpés en morceaux.
import type { ReactNode } from "react";

type Situation = { title: string; text: ReactNode };

const fr = {
  metaTitle: "Règles — Traversal",
  title: "Comment jouer",
  glance: {
    title: "En un coup d’œil",
    players: "joueurs",
    piecesEach: "pièces chacun",
    board: "plateau en relief",
    exits: "sorties = fin",
    intro: (
      <>
        Fais <b>traverser</b> le plateau à tes pièces et fais-les <b>sortir par le bord opposé</b>. Chaque pièce sortie
        rapporte sa <b>Force</b>. Dès que <b>deux pièces au total</b> (des deux camps) sont sorties, le meilleur score gagne.
      </>
    ) as ReactNode,
    sides: "Rouge part de la rangée 1 et sort par la rangée 10 ; Bleu fait l’inverse. Rouge commence.",
  },
  pieces: {
    title: "Les pièces",
    intro: (
      <>
        Le nombre de <b>coins de la base</b> donne le <b>Mouvement</b>, le nombre de <b>pointes au sommet</b> donne la
        <b> Force</b>. Mouvement + Force = 6 : plus une pièce est rapide, plus elle est fragile.
      </>
    ) as ReactNode,
    setup: "Chaque joueur a 2 pièces de chaque type, placées sur les colonnes c à h de sa rangée de départ : les plus rapides au centre (Explorateurs), puis les Avant-gardes, les plus lentes sur les côtés (Sentinelles).",
  },
  move: {
    title: "Se déplacer",
    items: [
      <>À ton tour, déplace <b>une</b> pièce, case par case, en ligne droite (avant, arrière, gauche, droite). Tu peux tourner.</>,
      <>Case de même hauteur : <b>1</b> point de Mouvement. Monter ou descendre : <b>différence de hauteur + 1</b> (de 2 à 4 : 3 points ; de 4 à 2 : 3 points aussi).</>,
      <>On ne traverse <b>aucune pièce</b>, alliée ou ennemie. Et on ne peut pas finir sur sa case de départ.</>,
      <>Deux cases voisines ne diffèrent jamais de plus de 2 niveaux : tout le plateau est franchissable.</>,
    ] as ReactNode[],
  },
  combat: {
    title: "Combattre",
    items: [
      <>Pour attaquer, termine ton déplacement <b>sur la case d’une pièce ennemie</b> (son coût d’entrée compte).</>,
      <>
        <b>Attaque</b> = Force de base, <b>+1</b> si ta pièce a commencé le tour plus haut que la cible (<b>−1</b> si plus bas),
        <b> + la Force</b> de chacune de tes autres pièces voisines de la cible.
      </>,
      <><b>Défense</b> = Force de base <b>+1</b> par pièce alliée voisine du défenseur.</>,
      <>Si l’attaque est <b>supérieure ou égale</b> à la défense, la pièce attaquée <b>sort du plateau</b> (sans marquer) et tu prends sa case. Sinon, l’attaque est interdite.</>,
      <>Attaquer termine ton tour. Le jeu te montre l’aperçu du combat avant de valider.</>,
    ] as ReactNode[],
  },
  end: {
    title: "Fin de partie",
    items: [
      <>Une pièce sur ta dernière rangée avec <b>au moins 1 point de Mouvement</b> restant peut sortir. Elle rapporte sa Force.</>,
      <>Dès que <b>2 pièces</b> sont sorties (tous camps confondus), le meilleur score gagne ; égalité = nulle.</>,
      <><b>Sentinelle</b> : si c’est la <b>toute première</b> pièce à sortir, son camp gagne immédiatement.</>,
      <>Après 200 coups, la partie s’arrête : le meilleur score gagne ; sinon la pièce la plus avancée, puis la plus forte.</>,
    ] as ReactNode[],
  },
  situations: {
    title: "Situations de jeu",
    intro:
      "Des positions réelles, calculées par le moteur du jeu : clique sur les pièces, essaie les coups, fais tourner le plateau.",
    replay: "↺ Recommencer",
    hintMoved: "Continue d’explorer, ou recommence la situation.",
    hintStart: "Clique sur une case en surbrillance pour jouer le coup.",
    list: {
      relief: {
        title: "Le relief coûte du Mouvement",
        text: (
          <>
            La <b>Sentinelle</b> a 3 points de Mouvement. Sur le plat, chaque pas coûte 1. Pour monter sur la colline (de
            1 à 3), il faut <b>l’écart + 1 = 3 points</b> : elle peut y grimper… mais n’ira pas plus loin ce tour-ci.
          </>
        ),
      },
      explorer: {
        title: "Les coups spéciaux de l’Explorateur",
        text: (
          <>
            Coincé au fond d’une cuvette, l’<b>Explorateur</b> peut faire <b>1 pas en diagonale</b> ou <b>bondir de 2 cases</b>{" "}
            en ligne droite, <b>sans payer la hauteur</b> (cases violettes). Mais jamais par-dessus une pièce : à gauche,
            l’Avant-garde bloque le bond.
          </>
        ),
      },
      hill: {
        title: "Combat : l’avantage de la colline",
        text: (
          <>
            Pour attaquer, termine ton déplacement <b>sur la pièce ennemie</b>. L’Avant-garde rouge (Force 2) part{" "}
            <b>plus haut</b> que sa cible : <b>+1</b>. L’Avant-garde bleue (Force 2) a un allié collé à elle : <b>+1</b> en
            défense. <b>3 contre 3</b> : l’attaque passe (il suffit d’égaler), la pièce bleue est éjectée.
          </>
        ),
      },
      assault: {
        title: "Combat : l’assaut allié",
        text: (
          <>
            Seul, l’Explorateur (Force 1) ne peut rien contre une Sentinelle (Force 3). Mais chaque pièce alliée{" "}
            <b>voisine de la cible</b> ajoute sa Force : avec l’Avant-garde à côté, <b>1 + 2 = 3</b> contre 3. À toi de
            jouer !
          </>
        ),
      },
      charge: {
        title: "La charge de l’Avant-garde",
        text: (
          <>
            Quand le <b>plus court chemin</b> vers sa cible coûte <b>exactement 4</b>, l’Avant-garde gagne <b>+1</b> :{" "}
            2 + 1 = 3, elle peut renverser la Sentinelle du haut. Celle de droite n’est qu’à 3 pas : pas de charge, 2 contre 3,
            attaque impossible.
          </>
        ),
      },
      exit: {
        title: "Sortir du plateau (et gagner)",
        text: (
          <>
            Une pièce sur la dernière rangée qui garde <b>au moins 1 point</b> de Mouvement peut <b>sortir</b> (flèche
            dorée) et marque sa Force. Ici c’est une <b>Sentinelle</b> : si elle est la toute <b>première pièce à sortir</b>,
            Rouge gagne immédiatement.
          </>
        ),
      },
    } as Record<string, Situation>,
  },
  cta: {
    train: "S’entraîner contre un bot",
    ranks: "Rangs et classement : comment monter de l’Ardoise à la Légende",
  },
};

const en: typeof fr = {
  metaTitle: "Rules — Traversal",
  title: "How to play",
  glance: {
    title: "At a glance",
    players: "players",
    piecesEach: "pieces each",
    board: "3D terrain board",
    exits: "exits = game over",
    intro: (
      <>
        Get your pieces <b>across</b> the board and make them <b>exit over the opposite edge</b>. Each piece that exits
        scores its <b>Strength</b>. As soon as <b>two pieces in total</b> (from either side) have exited, the highest score wins.
      </>
    ),
    sides: "Red starts on row 1 and exits past row 10; Blue does the opposite. Red moves first.",
  },
  pieces: {
    title: "The pieces",
    intro: (
      <>
        The number of <b>corners on the base</b> gives the <b>Movement</b>; the number of <b>points on top</b> gives the
        <b> Strength</b>. Movement + Strength = 6: the faster a piece, the more fragile it is.
      </>
    ),
    setup: "Each player has 2 pieces of each type, set up on columns c to h of their starting row: the fastest in the centre (Explorers), then the Vanguards, the slowest on the sides (Sentinels).",
  },
  move: {
    title: "Moving",
    items: [
      <>On your turn, move <b>one</b> piece, square by square, in straight lines (forward, back, left, right). You can turn.</>,
      <>Square at the same height: <b>1</b> Movement point. Going up or down: <b>height difference + 1</b> (from 2 to 4: 3 points; from 4 to 2: 3 points too).</>,
      <>You can’t pass through <b>any piece</b>, friend or foe. And you can’t end on the square you started from.</>,
      <>Two neighbouring squares never differ by more than 2 levels: the whole board can be crossed.</>,
    ],
  },
  combat: {
    title: "Fighting",
    items: [
      <>To attack, end your move <b>on an enemy piece’s square</b> (its entry cost counts).</>,
      <>
        <b>Attack</b> = base Strength, <b>+1</b> if your piece started the turn higher than the target (<b>−1</b> if lower),
        <b> + the Strength</b> of each of your other pieces next to the target.
      </>,
      <><b>Defense</b> = base Strength <b>+1</b> per allied piece next to the defender.</>,
      <>If the attack is <b>greater than or equal to</b> the defense, the attacked piece is <b>knocked off the board</b> (without scoring) and you take its square. Otherwise, the attack isn’t allowed.</>,
      <>Attacking ends your turn. The game shows you a combat preview before you confirm.</>,
    ],
  },
  end: {
    title: "End of the game",
    items: [
      <>A piece on your last row with <b>at least 1 Movement point</b> left can exit. It scores its Strength.</>,
      <>As soon as <b>2 pieces</b> have exited (from either side), the highest score wins; a tie is a draw.</>,
      <><b>Sentinel</b>: if it is the <b>very first</b> piece to exit, its side wins immediately.</>,
      <>After 200 moves, the game stops: the highest score wins; failing that, the most advanced piece, then the strongest.</>,
    ],
  },
  situations: {
    title: "Game situations",
    intro:
      "Real positions, computed by the game engine: click the pieces, try the moves, rotate the board.",
    replay: "↺ Restart",
    hintMoved: "Keep exploring, or restart the situation.",
    hintStart: "Click a highlighted square to play the move.",
    list: {
      relief: {
        title: "Terrain costs Movement",
        text: (
          <>
            The <b>Sentinel</b> has 3 Movement points. On flat ground, each step costs 1. To climb the hill (from 1 to
            3), it needs <b>the difference + 1 = 3 points</b>: it can get up there… but won’t go any further this turn.
          </>
        ),
      },
      explorer: {
        title: "The Explorer’s special moves",
        text: (
          <>
            Stuck at the bottom of a basin, the <b>Explorer</b> can take <b>1 diagonal step</b> or <b>leap 2 squares</b>{" "}
            in a straight line, <b>ignoring height cost</b> (purple squares). But never over a piece: on the left, the
            Vanguard blocks the leap.
          </>
        ),
      },
      hill: {
        title: "Combat: the high ground",
        text: (
          <>
            To attack, end your move <b>on the enemy piece</b>. The red Vanguard (Strength 2) starts{" "}
            <b>higher</b> than its target: <b>+1</b>. The blue Vanguard (Strength 2) has an ally right next to it:{" "}
            <b>+1</b> on defense. <b>3 vs 3</b>: the attack succeeds (a tie is enough), and the blue piece is knocked off.
          </>
        ),
      },
      assault: {
        title: "Combat: the combined assault",
        text: (
          <>
            On its own, the Explorer (Strength 1) can do nothing against a Sentinel (Strength 3). But each allied piece{" "}
            <b>next to the target</b> adds its Strength: with the Vanguard alongside, <b>1 + 2 = 3</b> vs 3. Your move!
          </>
        ),
      },
      charge: {
        title: "The Vanguard’s charge",
        text: (
          <>
            When the <b>shortest path</b> to its target costs <b>exactly 4</b>, the Vanguard gets <b>+1</b>:{" "}
            2 + 1 = 3, enough to topple the Sentinel at the top. The one on the right is only 3 steps away: no charge,
            2 vs 3, attack impossible.
          </>
        ),
      },
      exit: {
        title: "Exiting the board (and winning)",
        text: (
          <>
            A piece on the last row that still has <b>at least 1 point</b> of Movement can <b>exit</b> (golden arrow)
            and scores its Strength. Here it’s a <b>Sentinel</b>: if it is the <b>very first piece to exit</b>, Red wins
            immediately.
          </>
        ),
      },
    },
  },
  cta: {
    train: "Practice against a bot",
    ranks: "Ranks and rating: how to climb from Slate to Legend",
  },
};

export default { fr, en };
