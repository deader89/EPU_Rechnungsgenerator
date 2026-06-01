import os
import json
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from kivy.logger import Logger

def generiere_schluessel(pwd, salt):
    return PBKDF2(pwd.encode('utf-8'), salt, dkLen=32, count=100000, hmac_hash_module=SHA256)

def encrypt_data(data, pwd, data_file, salt_file=None):
    salt = os.urandom(16)
    key = generiere_schluessel(pwd, salt)
    iv = os.urandom(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    ct, tag = cipher.encrypt_and_digest(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    temp_file = data_file + ".tmp"
    try:
        with open(temp_file, "wb") as f: 
            f.write(salt + iv + tag + ct)
        os.replace(temp_file, data_file)
    except Exception as e:
        Logger.error(f"Crypto: Fehler beim Schreiben der verschluesselten Datei: {e}")
        if os.path.exists(temp_file):
            try: os.remove(temp_file)
            except Exception: pass

def decrypt_data(pwd, data_file, salt_file=None):
    if not os.path.exists(data_file): 
        return {"naechste_nummer": 1, "kunden_db": {}, "positionen_db": {}, "meine_daten": {"auto_lock_minuten": "5"}}
    with open(data_file, "rb") as f: pkg = f.read()
    
    # Lokale Migration: Altes Format erkennen
    if salt_file and os.path.exists(salt_file):
        with open(salt_file, "rb") as sf: salt = sf.read()
        iv, tag, ct = pkg[:12], pkg[12:28], pkg[28:]
    else:
        salt, iv, tag, ct = pkg[:16], pkg[16:28], pkg[28:44], pkg[44:]
        
    try:
        key = generiere_schluessel(pwd, salt)
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        dec = cipher.decrypt_and_verify(ct, tag)
        
        # Alte Datei aufräumen, da der nächste Save im neuen Format passiert
        if salt_file and os.path.exists(salt_file):
            try: os.remove(salt_file)
            except: pass
            
        return json.loads(dec.decode('utf-8'))
    except ValueError:
        Logger.error("Crypto: Falsches Passwort oder Datei beschädigt.")
        return "WRONG_PASSWORD"
    except Exception as e:
        Logger.error(f"Crypto: Fehler bei der Entschlüsselung: {e}")
        return None