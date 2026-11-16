# data.py
"""
Base de données commune de l'Agent DMFI.

TOUTES les tables (grades, rôles, colonnes du recensement, diplômes...) sont ici.
Les Cogs n'ont plus de matrice en dur : ils importent ce fichier et passent par
les fonctions de requête en bas (grade_suivant, get_diplome, lettre_colonne...).

Pour ajouter un tableau : le déclarer ici, puis l'importer dans le Cog
(`from data import MON_TABLEAU`).
"""
from __future__ import annotations

# =====================================================================
# 1. PERMISSIONS
# =====================================================================

ADMIN_MASTER_ID = 1350570903917826059

# Rôles Formateur : autorisés sur /fgi et /brevet en plus des administrateurs
# (ajoute un ID dans les accolades pour un nouveau rôle formateur)
ROLE_FORMATEUR_IDS: set[int] = {1507793936905928725, 1508576880201175061}

# =====================================================================
# 2. GRADES
# =====================================================================

# Grade actuel -> (Prochain grade, Points ou Condition par défaut)
GRADES_PROGRESSION: dict[str, tuple[str, str]] = {
    "EVAT": ("SDT", "FMI"),
    "SDT": ("1CL", "1"),
    "1CL": ("CPL", "2"),
    "CPL": ("CCH", "3"),
    "CCH": ("CC1", "4"),
    "CC1": ("SGT", "Dossier"),
    "SGT": ("SCH", "Test compétences"),
    "SCH": ("ADJ", "5"),
    "ADJ": ("ADC", "Test instructeur"),
    "ADC": ("MAJ", "6"),
    "MAJ": ("ASP", "Dossier"),
    "ASP": ("SLT", "École Officier"),
    "SLT": ("LTN", "École Officier"),
    "LTN": ("CNE", "Accord"),
    "CNE": ("CDT", "Accord"),
    "CDT": ("LCL", "Accord"),
    "LCL": ("COL", "Accord"),
    "COL": ("GDB", "Accord"),
    "GDB": ("Max", "Grade sommital"),
}

# Ordre hiérarchique (du plus bas au plus haut), déduit de la table ci-dessus
GRADES_ORDRE: list[str] = list(GRADES_PROGRESSION.keys())

# Grade -> (Nom complet affiché dans les annonces, nom exact de l'émoji sur le serveur)
GRADES_META: dict[str, tuple[str, str | None]] = {
    "EVAT": ("Engagé Volontaire", "DMFI_Formation"),
    "SDT": ("Soldat", "soldat"),
    "1CL": ("Soldat 1ère Classe", "Soldat_1er_Classe"),
    "CPL": ("Caporal", "Caporal"),
    "CCH": ("Caporal Chef", "CaporalChef"),
    "CC1": ("Caporal Chef 1ère Classe", "CaporalChef_1er_Classe"),
    "SGT": ("Sergent", "Sergent"),
    "SCH": ("Sergent Chef", "Sergent_Chef"),
    "ADJ": ("Adjudant", "Adjudant"),
    "ADC": ("Adjudant Chef", "Adjudant_Chef"),
    "MAJ": ("Major", "Major"),
    "ASP": ("Aspirant", "Aspirant"),
    "SLT": ("Sous-Lieutenant", "Sous_Lieutenant"),
    "LTN": ("Lieutenant", "Lieutenant"),
    "CNE": ("Capitaine", "Capitaine"),
    "CDT": ("Commandant", "Commandant"),
    "LCL": ("Lieutenant-Colonel", "Lieutenant_Colonel"),
    "COL": ("Colonel", "Colonel"),
    "GDB": ("Général de Brigade", "General_de_Brigade"),
}

# Grade -> ID du rôle Discord
GRADE_ROLES: dict[str, int | None] = {
    "EVAT": 1507786024653291751,  # Rôle recrue/EVAT retiré à la FGI
    "SDT": 1507794729029337118,
    "1CL": 1507794729742500061,
    "CPL": 1507794728350126170,
    "CCH": 1507794727725170709,
    "CC1": 1507794725606789202,
    "SGT": 1507795079753105469,
    "SCH": 1507795074321219685,
    "ADJ": 1507795081040494632,
    "ADC": 1507795080482914304,
    "MAJ": 1507795267456467014,
    "ASP": 1507795346804179136,
    "SLT": 1507795347823530116,
    "LTN": 1507795348746403840,
    "CNE": 1507795565554172105,
    "CDT": 1507795568112566352,
    "LCL": 1507795576882729071,
    "COL": 1507795578761777222,
    "GDB": 1528074538473226380,
}

# Grade -> (Numéro, Catégorie, Requis) : copie de l'onglet "DATA" du Sheet
GRADE_DATA_INFO: dict[str, tuple[int, str, str]] = {
    "GDB": (1, "Officier Général", "Grade sommital"),
    "COL": (2, "Officier Supérieur", "Accord"),
    "LCL": (3, "Officier Supérieur", "Accord"),
    "CDT": (4, "Officier Supérieur", "Accord"),
    "CNE": (5, "Officier Supérieur", "Accord"),
    "LTN": (6, "Officier Subalterne", "Accord"),
    "SLT": (7, "Officier Subalterne", "École Officier"),
    "ASP": (8, "Officier Subalterne", "École Officier"),
    "MAJ": (9, "Sous-Officier", "Dossier"),
    "ADC": (10, "Sous-Officier", "6"),
    "ADJ": (11, "Sous-Officier", "Test instructeur"),
    "SCH": (12, "Sous-Officier", "5"),
    "SGT": (13, "Sous-Officier", "Test compétences"),
    "CC1": (14, "Militaire du Rang", "Dossier"),
    "CCH": (15, "Militaire du Rang", "4"),
    "CPL": (16, "Militaire du Rang", "3"),
    "1CL": (17, "Militaire du Rang", "2"),
    "SDT": (18, "Militaire du Rang", "1"),
    "EVAT": (19, "Militaire du Rang", "FMI"),
}

# Groupe de grade (colonne B de l'onglet "DATA") -> ID du rôle Discord
# Le groupe suit le grade tout seul (cogs/roles.py) : à chaque changement de rôle de grade,
# le bot retire l'ancien rôle de groupe et donne le nouveau (CC1 -> SGT : HDR retiré, SO ajouté).
# >>> À COMPLÉTER : remplace None par l'ID du rôle Discord <<<
GROUPE_ROLES: dict[str, int | None] = {
    "Militaire du Rang": 1507794276820717608,    # HDR  : EVAT, SDT, 1CL, CPL, CCH, CC1
    "Sous-Officier": 1507794369799917588,        # SO   : SGT, SCH, ADJ, ADC, MAJ
    "Officier Subalterne": 1507794476813385738,  # OSUB : ASP, SLT, LTN
    "Officier Supérieur": 1507794551505551560,   # OSUP : CNE, CDT, LCL, COL
    "Officier Général": 1528075661988597810,     # OGEN : GDB
}

# Mets False pour couper la mise à jour automatique (la commande /sync_groupes reste utilisable).
GROUPES_AUTO = True

# =====================================================================
# 3. RÔLES D'INTÉGRATION ET DE FGI
# =====================================================================

# Validation d'une demande d'intégration
INTEGRATION_ROLE_ADD_ID = 1507786024653291751     # Rôle EVAT / membre recensé
INTEGRATION_ROLE_REMOVE_ID = 1508421388552245409  # Rôle d'attente

# Passage de la FGI (EVAT -> SDT)
FGI_ROLE_REMOVE_ID = 1507786024653291751
FGI_ROLES_ADD_IDS: list[int] = [
    1507794729029337118,  # Rôle SDT
    1507794276820717608,
    1508212512133353582,
    1507883337295986781,
    1508202657377161438,
]

# =====================================================================
# 4. SPÉCIALISATIONS, BREVETS ET RÉGIMENTS
#    col_index = numéro de colonne dans l'onglet Recensement (A=1, B=2...)
#    role_id   = ID du rôle Discord (None = pas encore renseigné -> ignoré
#                par /sync, et /brevet coche le Sheet sans donner de rôle)
# =====================================================================

# Colonnes N à Q
SPECIALITE_ROLES: dict[str, dict] = {
    "MECA":   {"role_id": 1508213186212528339, "col_index": 14},  # N
    "MEDIC":  {"role_id": 1508213181493809162, "col_index": 15},  # O
    "R&P":    {"role_id": 1508213083397689404, "col_index": 16},  # P
    "PILOTE": {"role_id": 1508212787820888175, "col_index": 17},  # Q
}

# Colonnes R à AL ("Diplômes officiel de la DMFI")
# >>> À COMPLÉTER : remplace None par l'ID du rôle Discord <<<
BREVET_ROLES: dict[str, dict] = {
    "FGI":     {"role_id": 1507883337295986781, "col_index": 18},  # R
    "SC1":     {"role_id": 1507883337933393941, "col_index": 19},  # S
    "SC2":     {"role_id": 1507883338529243156, "col_index": 20},  # T
    "CE":      {"role_id": 1507885184366678147, "col_index": 21},  # U
    "VG":      {"role_id": 1561328412323356792, "col_index": 22},  # V
    "MIT":     {"role_id": 1507883248804429964, "col_index": 23},  # W
    "SAPPEUR": {"role_id": 1507884691943067849, "col_index": 24},  # X
    "COM":     {"role_id": 1507883772937375784, "col_index": 25},  # Y
    "TAP":     {"role_id": 1509163339366924409, "col_index": 26},  # Z
    "VBL":     {"role_id": 1507884169055699034, "col_index": 27},  # AA
    "PL":      {"role_id": 1507883775101632603, "col_index": 28},  # AB
    "CDS":     {"role_id": 1524020504904601680, "col_index": 29},  # AC
    "MH-6":    {"role_id": 1524020095414833172, "col_index": 30},  # AD
    "UH-60V":  {"role_id": 1524019948240896100, "col_index": 31},  # AE
    "CH-53D":  {"role_id": 1524019788119146607, "col_index": 32},  # AF
    "NH-90":   {"role_id": 1524019293220769946, "col_index": 33},  # AG
    "TE":      {"role_id": 1526971675982168074, "col_index": 34},  # AH
    "TP":      {"role_id": 1526971791904608396, "col_index": 35},  # AI
    "SPTR":    {"role_id": 1526971929591025764, "col_index": 36},  # AJ
    "BACGN":   {"role_id": 1560982272927076463, "col_index": 37},  # AK
    "BACPN":   {"role_id": 1560643128921301032, "col_index": 38},  # AL
}

# Diplômes qui ne se donnent PAS via /brevet (le FGI passe par /fgi, qui promeut aussi SDT)
DIPLOMES_HORS_COMMANDE: set[str] = {"FGI"}

# Colonne M. Laisse None pour ne pas vérifier ce régiment dans /sync.
REGIMENT_ROLES: dict[str, int | None] = {
    "152e RI": 1508212512133353582,
    "1er RPIMa": 1543689871518859336,
    "4e RHFS": 1524002973619982356,
}

# =====================================================================
# 5. STRUCTURE DE L'ONGLET "Recensement" (A=1, B=2, ...)
# =====================================================================

SPREADSHEET_ID_DEFAUT = "1j8Z5PrqQwMfRE9aFLaQ7VA-ZwUvJqnPeFXAP9ybhvR8"  # si SPREADSHEET_ID absent du .env
WORKSHEET_NAMES = ("Recensement", "Recensement ")  # noms d'onglet essayés dans l'ordre

COL_DISCORD_ID = 1   # A
COL_DISCORD_TAG = 2  # B
COL_ROBLOX = 3       # C
COL_NOM_USAGE = 4    # D
COL_NUMERO = 5       # E (formule)
COL_CATEGORIE = 6    # F (formule)
COL_GRADE = 7        # G
COL_DATE_IN = 8      # H
COL_POINTS = 9       # I
COL_REQUIS = 10      # J (formule)
COL_POURCENT = 11    # K (formule)
COL_COMPORTEMENT = 12  # L
COL_REGIMENT = 13    # M
COL_DERNIERE = 38    # AL

LIGNE_DEBUT_DONNEES = 3  # Lignes 1 et 2 = en-têtes
LIGNE_FIN_DONNEES = 9999

# Quand un membre quitte le serveur (départ, kick ou ban), sa ligne du recensement
# est supprimée automatiquement. Une sauvegarde est postée dans le salon défini par
# LOG_RECENSEMENT_CHANNEL_ID dans le .env. Mets False pour désactiver.
SUPPRESSION_AUTO_DEPART = True


# =====================================================================
# 6. RECOMMANDATIONS (cogs/recommandations.py)
# =====================================================================

# >>> À COMPLÉTER <<<
# Forum où le bot publie les recommandations (un post par membre recommandé).
# (peut aussi se régler dans le .env avec RECO_FORUM_CHANNEL_ID, qui est alors prioritaire)
RECO_FORUM_ID: int | None = 1571238284003385505

# Salon PRIVÉ de l'état-major où le bot note qui a fait chaque recommandation (pour repérer
# les abus). Laisse None pour que l'auteur ne soit enregistré nulle part.
# (.env : RECO_LOG_CHANNEL_ID)
RECO_LOG_STAFF_ID: int | None = None

# True  = le post public affiche « Anonyme » à la place de l'auteur.
# False = l'auteur est mentionné dans le post (pense alors à retirer « anonymement » du texte ci-dessous).
RECO_ANONYME = True

# Fichier local qui retient « membre -> son post » pour regrouper ses recommandations.
# Aucun auteur n'y est écrit. Ne pas le supprimer, sinon de nouveaux posts seront créés.
RECO_FICHIER = "storage/recommandations.json"

# Panneau posté par /setup_recommandation (1er encadré)
RECO_PANNEAU_FONCTIONNEMENT = (
    "## ℹ️・Fonctionnement des recommandations\n\n"
    ">>> Les recommandations seront étudiées **régulièrement** par l’encadrement afin d’identifier "
    "les membres qui se démarquent par leur **comportement**, leur **implication** et leurs **compétences**.\n\n"
    "Un membre recevant plusieurs recommandations sérieuses pourra se voir attribuer "
    "**des points supplémentaires**, ou éventuellement être proposé à **une promotion** si "
    "__son niveau, son attitude et les besoins du serveur le permettent__.\n\n"
    "Les recommandations ne garantissent donc **pas automatiquement une récompense** ou une montée "
    "en grade. Elles servent avant tout **d’indicateur** pour mieux repérer les "
    "__membres méritants et valoriser ceux qui s’investissent réellement dans le D.M.F.I__.\n\n"
    "_L’objectif est de renforcer la méritocratie au sein du serveur, en prenant davantage en compte "
    "les efforts visibles, la progression, la discipline et la qualité du travail fourni par chacun._"
)

# Panneau (2e encadré). {forum} est remplacé par la mention du forum.
RECO_PANNEAU_MODE_EMPLOI = (
    "# <:DMFI_Membre1:1497987652409098261>  Comment recommander un membre ?\n\n"
    "1. Clique sur **Faire une recommandation** ci-dessous.\n"
    "2. Choisis le membre que tu recommandes.\n"
    "3. Indique la **raison** et, si tu le souhaites, ton **avis / tes remarques**.\n\n"
    "Ta recommandation est publiée **anonymement** dans {forum} : chaque membre recommandé y a "
    "son propre post, où chacun peut donner son avis. Tu peux recommander autant de membres que "
    "tu le souhaites, mais pas toi-même.\n\n"
    "## <:DMFI_Rules:1495507431684309133>  Merci de fournir des recommandations claires et justifiées "
    "afin de faciliter leur étude par l'état-major."
)


# =====================================================================
# 7. INTER-SERVEUR (cogs/interserveur.py)
#    Le serveur principal fait foi : les 3 autres serveurs suivent ses rôles.
# =====================================================================

SERVEUR_PRINCIPAL_ID = 1229869738352574484
SERVEUR_SPECIALITES_ID = 1508409641154117732   # D.M.F.I. | Spécialités & Régiments
SERVEUR_RPIMA_ID = 1535020258837008656         # 1er RPIMA DMFI
SERVEUR_ENSEIGNEMENT_ID = 1544046845049970729  # Département de l'Enseignement Militaire DMFI

# Interrupteurs (False = fonction coupée)
INTERSERVEUR_ACTIF = True              # Copie des rôles du principal vers les autres serveurs
FILTRAGE_ENTREE = True                 # Expulse à l'arrivée qui n'est pas recensé + présent sur le principal
EXPULSION_DEPART_PRINCIPAL = True      # Quitter le principal = expulsé des 3 autres serveurs
EXPULSION_SI_GROUPE_INTERDIT = True    # Ex : un sous-officier rétrogradé militaire du rang quitte l'enseignement

# Commandes utilisables ailleurs que sur le serveur principal (toutes les autres y sont bloquées)
COMMANDES_HORS_PRINCIPAL: set[str] = {"progression", "question"}

# --- Qui n'est jamais expulsé (les modérateurs) ---
# Rôles DU SERVEUR PRINCIPAL qui dispensent du recensement et de la règle de grade
# >>> À COMPLÉTER : ID des rôles de modération du principal (ex : Perm lvl...) <<<
ROLES_MODERATION_PRINCIPAL_IDS: set[int] = set()
# ID de MEMBRES jamais expulsés, même absents du principal (les propriétaires des serveurs le sont déjà)
MEMBRES_EXEMPTES_IDS: set[int] = {ADMIN_MASTER_ID}

# Salon du principal où le bot note les expulsions et les erreurs (.env : INTERSERVEUR_LOG_CHANNEL_ID).
# None = le salon de logs du recensement (LOG_RECENSEMENT_CHANNEL_ID) est utilisé.
INTERSERVEUR_LOG_ID: int | None = None

# --- Fonctions (rôles du serveur principal) ---
# >>> À COMPLÉTER : ID des rôles sur le serveur principal <<<
FONCTION_ROLES: dict[str, int | None] = {
    "CEMA": 1508216018986729653,   # Chef d'État-Major de la DMFI
    "CEMAA": 1542986819585708053,  # Chef d'État-Major Adjoint de la DMFI
    "DDEM": 1542987031620358235,   # Directeur du Département de l'Enseignement Militaire
}


def _lien(nom: str, role_id: int | None, *sources: str, depart: bool = False) -> dict:
    """
    Une liaison : « ce rôle du serveur secondaire est porté si AU MOINS UNE source est vraie ».
    Sources possibles (lues sur les rôles du serveur principal) :
      "MEMBRE"                      toute personne admise sur le serveur
      "GRADE:SGT"                   grade exact (codes de GRADE_ROLES)
      "GROUPE:Sous-Officier"        groupe de grade (noms de GROUPE_ROLES)
      "SPECIALITE:MECA"             codes de SPECIALITE_ROLES
      "BREVET:SC1"                  codes de BREVET_ROLES
      "REGIMENT:4e RHFS"            noms de REGIMENT_ROLES
      "FONCTION:CEMA"               noms de FONCTION_ROLES
    depart=True : rôle « de départ », donné une seule fois quand la source apparaît (ou à l'arrivée
    sur le serveur). Le bot ne le redonne pas si un instructeur l'a retiré à la main, mais le retire
    quand la source disparaît.
    """
    return {"nom": nom, "role_id": role_id, "sources": set(sources), "depart": depart}


# Pour chaque serveur secondaire : qui peut entrer, et quels rôles le bot y gère.
# >>> À COMPLÉTER : remplace None par l'ID du rôle SUR LE SERVEUR SECONDAIRE <<<
# Tant qu'un ID vaut None, la liaison est ignorée. Les rôles absents de ces listes
# (postes des régiments, instructeurs, statuts SAS...) ne sont jamais touchés par le bot.
SERVEURS_LIES: dict[int, dict] = {

    SERVEUR_SPECIALITES_ID: {
        "nom": "Spécialités & Régiments",
        "groupes_autorises": None,  # None = tous les grades peuvent entrer
        "liens": [
            _lien("「DMFI」Soldat", 1508451157071368303, "GROUPE:Militaire du Rang"),
            _lien("「DMFI」Sous-Officier", 1508463945432699032, "GROUPE:Sous-Officier"),
            _lien("「DMFI」Officier", 1508463983873757395,
                  "GROUPE:Officier Subalterne", "GROUPE:Officier Supérieur", "GROUPE:Officier Général"),
            _lien("État-Major", 1508459765951365132, "FONCTION:CEMA", "FONCTION:CEMAA"),
            # Spécialités
            _lien("MECA | Mécanicien - Logisticien", 1508420569559859312, "SPECIALITE:MECA"),
            _lien("R&P | Reconnaissance et précision", 1531989996058185828, "SPECIALITE:R&P"),
            _lien("MEDIC | Médecin Militaire", 1508422608281014349, "SPECIALITE:MEDIC"),
            _lien("PILOTE (rôle de base des pilotes)", 1571790456554000454, "SPECIALITE:PILOTE"),
            # Brevets
            _lien("R&P | Tireur d'Élite", 1508422229975634042, "BREVET:TE"),
            _lien("R&P | Tireur de Précision", 1508422269213605969, "BREVET:TP"),
            _lien("R&P | Spotters", 1508422318379241522, "BREVET:SPTR"),
            _lien("4e RHFS | Pilote NH90TTH", 1508421198864973835, "BREVET:NH-90"),
            _lien("4e RHFS | Pilote CH-53D", 1524348841594323024, "BREVET:CH-53D"),
            # Exemples à activer si tu le souhaites (retire le # et mets l'ID) :
            # _lien("4e RHFS | HR 530F", None, "BREVET:MH-6"),
            # _lien("1er RPIMA | Opérateur", None, "REGIMENT:1er RPIMa"),
        ],
    },

    SERVEUR_RPIMA_ID: {
        "nom": "1er RPIMA",
        "groupes_autorises": None,
        "liens": [
            _lien("Membres DMFI", 1535631712753688576, "MEMBRE"),
            _lien("「GBR」Général de brigade", 1535322892844269568, "GRADE:GDB"),
            _lien("Pilote 4eRHFS", 1543114835653304440, "REGIMENT:4e RHFS"),
            # Spécialisations
            _lien("「R&P」Reconnaissance & Précision", 1536046844667502632, "SPECIALITE:R&P"),
            _lien("「MEDIC」Médecin militaire", 1536046847423156404, "SPECIALITE:MEDIC"),
            _lien("「MECA」Mécanicien - Logisticien", 1536046848769396736, "SPECIALITE:MECA"),
            _lien("「PILOTE」Pilote d'Hélicoptère", 1536046849432101005, "SPECIALITE:PILOTE"),
            # Diplômes
            _lien("「SC1」Secourisme au Combat de Niveau 1", 1536046850467962890, "BREVET:SC1"),
            _lien("「SC2」Secourisme au Combat de Niveau 2", 1536046850551976026, "BREVET:SC2"),
            _lien("「MIT」Mitrailleur", 1536046851134849186, "BREVET:MIT"),
            _lien("「COM」Radio", 1536046851860598804, "BREVET:COM"),
            _lien("「TAP」Parachutiste", 1536047418087571569, "BREVET:TAP"),
            _lien("「SAPEUR」Sapeur du Génie", 1536047419161059329, "BREVET:SAPPEUR"),
            _lien("「VBL」Véhicule Blindé Léger", 1536047419450593331, "BREVET:VBL"),
            _lien("「PL」Poids Lourd", 1536048007772905504, "BREVET:PL"),
            _lien("「TE」Brevet Tireur d'Elite", 1536048012554408086, "BREVET:TE"),
            _lien("「TP」Brevet Tireur de Précision", 1536048017101299732, "BREVET:TP"),
            _lien("「SPTR」Brevet Spotter", 1536048020301414531, "BREVET:SPTR"),
        ],
    },

    SERVEUR_ENSEIGNEMENT_ID: {
        "nom": "Enseignement",
        # Un militaire du rang ne peut pas entrer sur ce serveur
        "groupes_autorises": {"Sous-Officier", "Officier Subalterne", "Officier Supérieur", "Officier Général"},
        "liens": [
            # École de Sous-Officiers
            _lien("DESO | Département Ecole de Sous-Officier", 1546245598687006750, "GROUPE:Sous-Officier"),
            _lien("Test de compétences", 1546247187577573437, "GRADE:SGT"),
            _lien("Test Instructeur", 1546246342660071574, "GRADE:ADJ"),
            # École des Officiers
            _lien("ASP | En cours de phase", 1546246080319197294, "GRADE:ASP"),
            _lien("Attente phase théorique", 1546246127781937202, "GRADE:ASP", depart=True),
            _lien("SLT | En cours de phase", 1546245993211764828, "GRADE:SLT"),
            _lien("DEO | Département Ecole des Officiers", 1546244736044503071,
                  "GRADE:LTN", "GRADE:CNE", "GRADE:CDT", "GRADE:LCL", "GRADE:COL", "GRADE:GDB"),
            # Fonctions
            _lien("CEMA | Chef d'Etat-Major de la DMFI", 1546260264310153388, "FONCTION:CEMA", "FONCTION:CEMAA"),
            _lien("DDEM | Directeur du Département de l'Enseignement Militaire", 1546237516774903858, "FONCTION:DDEM"),
        ],
    },
}

# --- Message privé envoyé quand un membre est promu à l'un de ces grades ---
# >>> À COMPLÉTER : lien d'invitation PERMANENT du serveur de l'enseignement <<<
INVITATION_ENSEIGNEMENT = ""

# {mention} est remplacé par la mention du membre. Le lien ci-dessus est ajouté à la fin.
# >>> À ADAPTER : précise ce que le membre doit faire pour passer au grade suivant <<<
MESSAGES_PROMOTION: dict[str, str] = {
    "SGT": (
        "🎖️ Bien joué {mention}, vous êtes maintenant **Sergent** : vous entrez dans le corps des "
        "**sous-officiers** de la DMFI.\n\n"
        "Pour passer **Sergent-Chef**, vous devez réussir le **test de compétences** de l'École de "
        "Sous-Officiers. Tout se passe sur le serveur du Département de l'Enseignement Militaire."
    ),
    "ADJ": (
        "🎖️ Bien joué {mention}, vous êtes maintenant **Adjudant**.\n\n"
        "Pour passer **Adjudant-Chef**, vous devez réussir le **test instructeur** de l'École de "
        "Sous-Officiers. Tout se passe sur le serveur du Département de l'Enseignement Militaire."
    ),
    "SLT": (
        "🎖️ Bien joué {mention}, vous êtes maintenant **Sous-Lieutenant**.\n\n"
        "Pour passer **Lieutenant**, vous devez terminer votre phase à l'**École des Officiers**. "
        "Tout se passe sur le serveur du Département de l'Enseignement Militaire."
    ),
}

# =====================================================================
# 8. ANNONCES DE GRADE (promotions de 12h / 19h et /retrograder)
# =====================================================================

EMOJI_PROMOTION = "DMFI_Join"        # Émoji placé devant chaque promotion
EMOJI_RETROGRADATION = "DMFI_Leave"  # Émoji placé devant chaque rétrogradation

# Rétrogradations faites avec /retrograder, en attente de la prochaine annonce (12h ou 19h)
RETRO_FICHIER = "storage/retrogradations.json"


# =====================================================================
# 9. REQUÊTES
# =====================================================================

def lettre_colonne(index: int) -> str:
    """Numéro de colonne -> lettre(s) Google Sheets (1 -> 'A', 28 -> 'AB')."""
    lettres = ""
    while index > 0:
        index, reste = divmod(index - 1, 26)
        lettres = chr(65 + reste) + lettres
    return lettres


def cellule(col_index: int, ligne: int) -> str:
    """(18, 42) -> 'R42'."""
    return f"{lettre_colonne(col_index)}{ligne}"


def grade_suivant(grade: str) -> str | None:
    """Grade suivant, ou None si grade inconnu / sommital."""
    suivant = GRADES_PROGRESSION.get(grade, (None, None))[0]
    return suivant if suivant in GRADES_PROGRESSION else None


def requis_defaut(grade: str) -> str:
    """Points ou condition par défaut pour quitter ce grade."""
    return GRADES_PROGRESSION.get(grade, ("", "N/A"))[1]


def rang_grade(grade: str) -> int:
    """Position hiérarchique (EVAT=0 ... GDB=18), -1 si inconnu."""
    return GRADES_ORDRE.index(grade) if grade in GRADES_ORDRE else -1


def role_id_grade(grade: str) -> int | None:
    return GRADE_ROLES.get(grade)


def tous_les_roles_grade() -> set[int]:
    return {rid for rid in GRADE_ROLES.values() if rid is not None}


def groupe_grade(grade: str) -> str | None:
    """Groupe d'un grade ("SGT" -> "Sous-Officier"), None si grade inconnu."""
    info = GRADE_DATA_INFO.get(grade)
    return info[1] if info else None


def tous_les_roles_groupe() -> set[int]:
    return {rid for rid in GROUPE_ROLES.values() if rid is not None}


def grade_le_plus_haut(role_ids: set[int]) -> str | None:
    """Grade le plus élevé parmi les rôles d'un membre, None s'il n'a aucun rôle de grade."""
    grades = [code for code, rid in GRADE_ROLES.items() if rid is not None and rid in role_ids]
    return max(grades, key=rang_grade) if grades else None


def correction_groupe(role_ids: set[int]) -> tuple[int | None, set[int]]:
    """
    Compare les rôles d'un membre au groupe que son grade lui donne.
    Renvoie (rôle de groupe à ajouter ou None, rôles de groupe à retirer).
    Un membre sans grade ne garde aucun rôle de groupe.
    """
    grade = grade_le_plus_haut(role_ids)
    cible = GROUPE_ROLES.get(groupe_grade(grade)) if grade else None
    a_retirer = {rid for rid in tous_les_roles_groupe() if rid in role_ids and rid != cible}
    a_ajouter = cible if cible is not None and cible not in role_ids else None
    return a_ajouter, a_retirer


def tous_les_diplomes(inclure_hors_commande: bool = True) -> dict[str, dict]:
    """
    Spécialisations + brevets dans un seul dictionnaire :
    {"MECA": {"type": "SPECIALITE", "role_id": ..., "col_index": 14}, ...}
    """
    resultat: dict[str, dict] = {}
    for code, cfg in SPECIALITE_ROLES.items():
        resultat[code] = {"type": "SPECIALITE", **cfg}
    for code, cfg in BREVET_ROLES.items():
        resultat[code] = {"type": "BREVET", **cfg}
    if not inclure_hors_commande:
        for code in DIPLOMES_HORS_COMMANDE:
            resultat.pop(code, None)
    return resultat


def get_diplome(code: str) -> dict | None:
    """Recherche insensible à la casse d'une spécialisation ou d'un brevet."""
    cible = code.strip().upper()
    for nom, cfg in tous_les_diplomes().items():
        if nom.upper() == cible:
            return {"code": nom, **cfg}
    return None

# ---------- Inter-serveur ----------

def sources_membre(role_ids: set[int]) -> set[str]:
    """
    Ce que les rôles d'un membre SUR LE SERVEUR PRINCIPAL disent de lui, sous forme de sources
    ("GRADE:SGT", "GROUPE:Sous-Officier", "SPECIALITE:MECA", "BREVET:SC1", "REGIMENT:4e RHFS"...).
    """
    sources = {"MEMBRE"}
    grade = grade_le_plus_haut(role_ids)
    if grade:
        sources.add(f"GRADE:{grade}")
        sources.add(f"GROUPE:{groupe_grade(grade)}")
    for prefixe, table in (("SPECIALITE", SPECIALITE_ROLES), ("BREVET", BREVET_ROLES)):
        for code, cfg in table.items():
            if cfg["role_id"] is not None and cfg["role_id"] in role_ids:
                sources.add(f"{prefixe}:{code}")
    for prefixe, table in (("REGIMENT", REGIMENT_ROLES), ("FONCTION", FONCTION_ROLES)):
        for nom, rid in table.items():
            if rid is not None and rid in role_ids:
                sources.add(f"{prefixe}:{nom}")
    return sources


def sources_valides() -> set[str]:
    """Toutes les sources qui existent (sert à repérer une faute de frappe dans SERVEURS_LIES)."""
    return (
        {"MEMBRE"}
        | {f"GRADE:{g}" for g in GRADE_ROLES}
        | {f"GROUPE:{g}" for g in GROUPE_ROLES}
        | {f"SPECIALITE:{c}" for c in SPECIALITE_ROLES}
        | {f"BREVET:{c}" for c in BREVET_ROLES}
        | {f"REGIMENT:{r}" for r in REGIMENT_ROLES}
        | {f"FONCTION:{f}" for f in FONCTION_ROLES}
    )


def groupe_autorise(serveur_id: int, grade: str | None) -> bool:
    """Le grade donne-t-il le droit d'être sur ce serveur secondaire ? (sans grade = non, s'il y a une règle)"""
    autorises = SERVEURS_LIES[serveur_id]["groupes_autorises"]
    if autorises is None:
        return True
    return grade is not None and groupe_grade(grade) in autorises


def correction_roles_lies(
    serveur_id: int,
    role_ids_locaux: set[int],
    sources: set[str],
    sources_avant: set[str] | None = None,
) -> tuple[set[int], set[int]]:
    """
    Compare les rôles d'un membre sur un serveur secondaire à ce que le principal lui donne.
    Renvoie (rôles à ajouter, rôles à retirer) sur ce serveur secondaire.
    sources_avant : sources avant le changement ; None = le membre vient d'arriver sur le serveur.
    Un rôle « de départ » n'est ajouté que si sa source vient d'apparaître (ou à l'arrivée).
    """
    voulus: set[int] = set()         # Rôles que le membre doit porter
    voulus_depart: set[int] = set()  # Rôles de départ à donner maintenant
    geres: set[int] = set()          # Tous les rôles que le bot gère sur ce serveur
    tolere: set[int] = set()         # Rôles de départ qu'on laisse en place sans les redonner
    for lien in SERVEURS_LIES[serveur_id]["liens"]:
        rid = lien["role_id"]
        if rid is None:
            continue
        geres.add(rid)
        if not (lien["sources"] & sources):
            continue
        if not lien["depart"]:
            voulus.add(rid)
        else:
            tolere.add(rid)
            if sources_avant is None or not (lien["sources"] & sources_avant):
                voulus_depart.add(rid)

    a_ajouter = (voulus | voulus_depart) - role_ids_locaux
    a_retirer = (geres & role_ids_locaux) - voulus - tolere
    return a_ajouter, a_retirer
