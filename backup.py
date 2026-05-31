import os
import json
import zipfile
import io
from datetime import datetime
from Crypto.Cipher import AES
from crypto import generiere_schluessel
from kivy.logger import Logger

def create_backup(data_path, salt_path, full_path, zip_pwd, user_data_dir, logo_pfad=None, app_data=None, target_os=None):
    mem_zip_buffer = io.BytesIO()
    with zipfile.ZipFile(mem_zip_buffer, 'w', zipfile.ZIP_DEFLATED) as mem_zip:
        mem_zip.write(data_path, "rechnung_daten.enc")
        mem_zip.write(salt_path, "rechnung_daten.salt")
        
        if app_data and "rechnungen_db" in app_data:
            from platform_io import read_file_native
            for rn, r_daten in app_data["rechnungen_db"].items():
                pfad = r_daten.get("pfad")
                if pfad:
                    try:
                        file_bytes = read_file_native(pfad, target_os)
                        if file_bytes:
                            datum = r_daten.get("datum", "")
                            try:
                                dt = datetime.fromisoformat(datum)
                                ordner = dt.strftime("%Y_%m")
                            except Exception:
                                ordner = "Unbekannt"
                                
                            import urllib.parse
                            filename = urllib.parse.unquote(str(pfad).replace('\\', '/').split('/')[-1])
                            if not filename.lower().endswith(".pdf"):
                                kunde = r_daten.get("kunde", "")
                                sicherer_kunde = "".join(c for c in kunde if c.isalnum() or c in " _-")
                                filename = f"{sicherer_kunde}_Rechnung_{rn}.pdf"
                                
                            arcname = f"Rechnungen/{ordner}/{filename}"
                            mem_zip.writestr(arcname, file_bytes)
                    except Exception as e:
                        Logger.error(f"Backup: Konnte PDF {pfad} nicht ins Backup schreiben: {e}")
        else:
            rechnungen_dir = os.path.join(user_data_dir, "Rechnungen")
            if os.path.exists(rechnungen_dir):
                for root, dirs, files in os.walk(rechnungen_dir):
                    for file in files:
                        if file.endswith('.pdf'):
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, rechnungen_dir).replace('\\', '/')
                            arcname = f"Rechnungen/{rel_path}"
                            mem_zip.write(file_path, arcname)
                        
        if logo_pfad and os.path.exists(logo_pfad):
            ext = os.path.splitext(logo_pfad)[1].lower()
            mem_zip.write(logo_pfad, f"logo{ext}")

    mem_zip_bytes = mem_zip_buffer.getvalue()
    mem_zip_buffer.close()
    
    salt = os.urandom(16)
    schluessel = generiere_schluessel(zip_pwd, salt)
    
    iv = os.urandom(12)
    cipher = AES.new(schluessel, AES.MODE_GCM, nonce=iv)
    chiffretext, tag = cipher.encrypt_and_digest(mem_zip_bytes)
    
    final_crypto_data = salt + iv + tag + chiffretext
    
    with zipfile.ZipFile(full_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("backup_secure.dat", final_crypto_data)

def restore_backup(quell_zip, pwd, user_data_dir, custom_pdf_dir=None, target_os=None):
    with zipfile.ZipFile(quell_zip, 'r') as zf:
        final_crypto_data = zf.read("backup_secure.dat")
        
    salt, iv, tag, ct = final_crypto_data[:16], final_crypto_data[16:28], final_crypto_data[28:44], final_crypto_data[44:]
    schluessel = generiere_schluessel(pwd, salt)
    
    cipher = AES.new(schluessel, AES.MODE_GCM, nonce=iv)
    dec = cipher.decrypt_and_verify(ct, tag)
    
    restored_pdfs = {}
    try:
        paket = json.loads(dec.decode('utf-8'))
        enc_bytes = bytes.fromhex(paket["enc"])
        salt_bytes = bytes.fromhex(paket["salt"])
        with open(os.path.join(user_data_dir, "rechnung_daten.enc"), "wb") as f: f.write(enc_bytes)
        with open(os.path.join(user_data_dir, "rechnung_daten.salt"), "wb") as f: f.write(salt_bytes)
    except Exception:
        mem_zip_buffer = io.BytesIO(dec)
        with zipfile.ZipFile(mem_zip_buffer, 'r') as mem_zip:
            for file_info in mem_zip.infolist():
                # Verhindert Directory Traversal Angriffe (../) und leere Ordner
                if ".." in file_info.filename or file_info.filename.startswith("/") or file_info.filename.endswith('/'):
                    continue
                    
                if file_info.filename in ["rechnung_daten.enc", "rechnung_daten.salt"]:
                    with open(os.path.join(user_data_dir, file_info.filename), "wb") as f:
                        f.write(mem_zip.read(file_info.filename))
                elif file_info.filename.startswith("Rechnungen/"):
                    new_uri = None
                    if custom_pdf_dir and custom_pdf_dir != "STANDARD":
                        from platform_io import write_to_custom_dir
                        parts = file_info.filename.split('/')
                        filename = parts[-1]
                        
                        # Wir nehmen immer nur den unmittelbaren Eltern-Ordner (z.B. 2026_05),
                        # um alte, versehentlich doppelt verschachtelte Backups zu glätten
                        rel_folder = parts[-2] if len(parts) >= 2 else ""
                            
                        new_uri = write_to_custom_dir(mem_zip.read(file_info.filename), rel_folder, filename, target_os, custom_pdf_dir)
                        if new_uri:
                            restored_pdfs[file_info.filename] = new_uri
                            
                    if not new_uri:
                        # Fallback: Speichere intern, falls SAF fehlschlägt oder nicht gesetzt ist
                        target_path = os.path.join(user_data_dir, os.path.normpath(file_info.filename))
                        os.makedirs(os.path.dirname(target_path), exist_ok=True)
                        with open(target_path, "wb") as f: 
                            f.write(mem_zip.read(file_info.filename))
                        restored_pdfs[file_info.filename] = target_path
                elif file_info.filename.startswith("logo."):
                    ext = os.path.splitext(file_info.filename)[1].lower()
                    target_path = os.path.join(user_data_dir, f"restored_logo{ext}")
                    # Alte Logos löschen, falls Erweiterung sich geändert hat (png <-> jpg)
                    for old_ext in [".png", ".jpg", ".jpeg"]:
                        old_path = os.path.join(user_data_dir, f"restored_logo{old_ext}")
                        if os.path.exists(old_path):
                            try: os.remove(old_path)
                            except: pass
                    with open(target_path, "wb") as f: 
                        f.write(mem_zip.read(file_info.filename))
        mem_zip_buffer.close()
        
    return restored_pdfs
