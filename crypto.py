import os
import json
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256
from kivy.logger import Logger

def generiere_schluessel(pwd, salt):
    return PBKDF2(pwd.encode('utf-8'), salt, dkLen=32, count=100000, hmac_hash_module=SHA256)

def encrypt_data(data, pwd, data_file, salt_file):
    salt = os.urandom(16)
    with open(salt_file, "wb") as sf: sf.write(salt)
    key = generiere_schluessel(pwd, salt)
    iv = os.urandom(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
    ct, tag = cipher.encrypt_and_digest(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    with open(data_file, "wb") as f: f.write(iv + tag + ct)

def decrypt_data(pwd, data_file, salt_file):
    if not os.path.exists(data_file): 
        return {"naechste_nummer": 1, "kunden_db": {}, "positionen_db": {}, "meine_daten": {"auto_lock_minuten": "5"}}
    with open(salt_file, "rb") as sf: salt = sf.read()
    with open(data_file, "rb") as f: pkg = f.read()
    try:
        key = generiere_schluessel(pwd, salt)
        iv, tag, ct = pkg[:12], pkg[12:28], pkg[28:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        dec = cipher.decrypt_and_verify(ct, tag)
        return json.loads(dec.decode('utf-8'))
    except Exception as e:
        Logger.error(f"Crypto: Fehler bei der Entschlüsselung: {e}")
        return None