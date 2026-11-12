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

ADMIN_MASTER_ID = 602585381120114698

# Rôle Formateur : autorisé sur /fgi et /brevet en plus des administrateurs
ROLE_FORMATEUR_ID = 1507793936905928725

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
    "EVAT": ("Engagé Volontaire", None),
    "SDT": ("Soldat", "soldat"),
    "1CL": ("Soldat 1ère Classe", "Soldat_1er_Classe"),
    "CPL": ("Caporal", "Caporal"),
    "CCH": ("Caporal Chef", "CaporalChef"),
    "CC1": ("Caporal Chef de Première Classe", "CaporalChef_1er_Classe"),
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
    "GDB": ("Général de Brigade", None),
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
    "FGI":     {"role_id": None, "col_index": 18},  # R
    "SC1":     {"role_id": None, "col_index": 19},  # S
    "SC2":     {"role_id": None, "col_index": 20},  # T
    "CE":      {"role_id": None, "col_index": 21},  # U
    "VG":      {"role_id": None, "col_index": 22},  # V
    "MIT":     {"role_id": None, "col_index": 23},  # W
    "SAPPEUR": {"role_id": None, "col_index": 24},  # X
    "COM":     {"role_id": None, "col_index": 25},  # Y
    "TAP":     {"role_id": None, "col_index": 26},  # Z
    "VBL":     {"role_id": None, "col_index": 27},  # AA
    "PL":      {"role_id": None, "col_index": 28},  # AB
    "CDS":     {"role_id": None, "col_index": 29},  # AC
    "MH-6":    {"role_id": None, "col_index": 30},  # AD
    "UH-60V":  {"role_id": None, "col_index": 31},  # AE
    "CH-53D":  {"role_id": None, "col_index": 32},  # AF
    "NH-90":   {"role_id": None, "col_index": 33},  # AG
    "TE":      {"role_id": None, "col_index": 34},  # AH
    "TP":      {"role_id": None, "col_index": 35},  # AI
    "SPTR":    {"role_id": None, "col_index": 36},  # AJ
    "BACGN":   {"role_id": None, "col_index": 37},  # AK
    "BACPN":   {"role_id": None, "col_index": 38},  # AL
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
LIGNE_FIN_DONNEES = 2000


# =====================================================================
# 6. REQUÊTES
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
