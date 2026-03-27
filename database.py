import sqlite3
import json

DB_NAME = "id_system.db"

def setup_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Table ID existante
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_carte (
            guild_id INTEGER,
            user_id INTEGER,
            nom TEXT,
            prenom TEXT,
            sexe TEXT,
            nationalite TEXT,
            date_naiss TEXT,
            lieu_naiss TEXT,
            nom_usage TEXT,
            date_validation TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, user_id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS server_config (
            guild_id INTEGER PRIMARY KEY
        )
    ''')
    
    columns_to_add = {
        "role_valide_id": "INTEGER",
        "role_non_valide_id": "INTEGER",
        "salon_admin_id": "INTEGER",
        "salon_annonce_id": "INTEGER",
        "autoroles": "TEXT",
        "fmi_add_roles": "TEXT",
        "fmi_remove_roles": "TEXT",
        "event_voice_id": "INTEGER",
        "event_report_id": "INTEGER",
        "webhook_name": "TEXT",
        "module_rp_active": "INTEGER DEFAULT 1",
        "module_mod_active": "INTEGER DEFAULT 1",
        "module_fmi_active": "INTEGER DEFAULT 1",
        "module_event_active": "INTEGER DEFAULT 1",
        "code_serveur": "TEXT",
        "rge_serveur": "TEXT DEFAULT '[0, 0, 0, 0, 0]'",
    }
    
    for col_name, col_type in columns_to_add.items():
        try:
            cursor.execute(f"ALTER TABLE server_config ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            pass 
            
    conn.commit()
    conn.close()

def set_server_config(guild_id, key, value):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO server_config (guild_id) VALUES (?)', (guild_id,))
    cursor.execute(f'UPDATE server_config SET {key} = ? WHERE guild_id = ?', (value, guild_id))
    conn.commit()
    conn.close()

def get_server_config(guild_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM server_config WHERE guild_id = ?', (guild_id,))
    result = cursor.fetchone()
    conn.close()
    return dict(result) if result else {}

# --- FONCTIONS ID EXISTANTES ---
def add_identity(guild_id, user_id, nom, prenom, sexe, nat, d_naiss, l_naiss, usage):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO id_carte 
        (guild_id, user_id, nom, prenom, sexe, nationalite, date_naiss, lieu_naiss, nom_usage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (guild_id, user_id, nom, prenom, sexe, nat, d_naiss, l_naiss, usage))
    # Création automatique du compte en banque vide
    cursor.execute('''
        INSERT OR IGNORE INTO rp_economie (guild_id, user_id) VALUES (?, ?)
    ''', (guild_id, user_id))
    conn.commit()
    conn.close()

def get_identity(guild_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM id_carte WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
    result = cursor.fetchone()
    conn.close()
    return result

def get_all_identities(guild_id=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if guild_id:
        cursor.execute('SELECT user_id, nom, prenom FROM id_carte WHERE guild_id = ?', (guild_id,))
    else:
        cursor.execute('SELECT user_id, nom, prenom FROM id_carte')
    results = cursor.fetchall()
    conn.close()
    return results

def update_player_data(guild_id, user_id, field, new_value):
    allowed_fields = ["nom", "prenom", "sexe", "nationalite", "date_naiss", "lieu_naiss", "nom_usage"]
    if field not in allowed_fields: return False
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        query = f"UPDATE id_carte SET {field} = ? WHERE guild_id = ? AND user_id = ?"
        cursor.execute(query, (new_value, guild_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

def delete_identity(guild_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('DELETE FROM id_carte WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        cursor.execute('DELETE FROM rp_economie WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()

# --- NOUVELLES FONCTIONS ÉCONOMIE / CITOYEN ---
def get_economy(guild_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM rp_economie WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
    result = cursor.fetchone()
    
    # --- CORRECTIF : Auto-création du compte pour les anciens joueurs ---
    if not result:
        # On vérifie si le joueur a bien une ID enregistrée
        cursor.execute('SELECT 1 FROM id_carte WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
        if cursor.fetchone():
            # Si oui, on lui crée un compte en banque à 0$ avec ses permis
            cursor.execute('INSERT INTO rp_economie (guild_id, user_id) VALUES (?, ?)', (guild_id, user_id))
            conn.commit()
            # On récupère ses nouvelles données toutes fraîches
            cursor.execute('SELECT * FROM rp_economie WHERE guild_id = ? AND user_id = ?', (guild_id, user_id))
            result = cursor.fetchone()
            
    conn.close()
    return dict(result) if result else None

def update_balance(guild_id, user_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('UPDATE rp_economie SET solde = solde + ? WHERE guild_id = ? AND user_id = ?', (amount, guild_id, user_id))
    conn.commit()
    conn.close()

def update_license(guild_id, user_id, permis_type, state, points=None):
    # permis_type = 'voiture', 'pl', ou 'helico'
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if points is not None:
        # On s'assure que les points restent entre 0 et 12
        cursor.execute(f'UPDATE rp_economie SET permis_{permis_type} = ?, points_{permis_type} = MAX(0, MIN(12, points_{permis_type} + ?)) WHERE guild_id = ? AND user_id = ?', (state, points, guild_id, user_id))
    else:
        cursor.execute(f'UPDATE rp_economie SET permis_{permis_type} = ? WHERE guild_id = ? AND user_id = ?', (state, guild_id, user_id))
    conn.commit()
    conn.close()