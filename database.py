import sqlite3

DB_NAME = "id_system.db"

def setup_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Utilisation du nom de table 'id_carte'
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS id_carte (
            user_id INTEGER PRIMARY KEY,
            nom TEXT,
            prenom TEXT,
            sexe TEXT,
            nationalite TEXT,
            date_naiss TEXT,
            lieu_naiss TEXT,
            nom_usage TEXT,
            date_validation TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def add_identity(user_id, nom, prenom, sexe, nat, d_naiss, l_naiss, usage):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO id_carte 
        (user_id, nom, prenom, sexe, nationalite, date_naiss, lieu_naiss, nom_usage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, nom, prenom, sexe, nat, d_naiss, l_naiss, usage))
    conn.commit()
    conn.close()

def get_identity(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM id_carte WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_all_identities():
    """Récupère la liste de toutes les ID enregistrées (pour check_db)."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id, nom, prenom FROM id_carte')
    results = cursor.fetchall()
    conn.close()
    return results

def update_identity_field(user_id, field, value):
    """Modifie une info précise d'un joueur."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    query = f"UPDATE id_carte SET {field} = ? WHERE user_id = ?"
    cursor.execute(query, (value, user_id))
    conn.commit()
    conn.close()