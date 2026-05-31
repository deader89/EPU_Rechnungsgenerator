from datetime import datetime
import random
import os

def cleanup_database(data):
    if not data or "kunden_db" not in data: 
        return False
    
    meine_daten = data.get("meine_daten", {})
    try: anonym_jahre = float(meine_daten.get("anonymisieren_nach_jahren", 7))
    except ValueError: anonym_jahre = 7
    
    try: delete_monate = float(meine_daten.get("interessenten_loeschen_monate", 12))
    except ValueError: delete_monate = 12
    
    now = datetime.now()
    changed = False
    kunden_db = data["kunden_db"]
    to_delete = []
    to_anonymize = []
    
    for name, daten in kunden_db.items():
        dt_letzte, dt_erstellt = None, None
        if "letzte_rechnung_datum" in daten:
            try: dt_letzte = datetime.fromisoformat(daten["letzte_rechnung_datum"])
            except Exception: pass
        if "erstellt_am" in daten:
            try: dt_erstellt = datetime.fromisoformat(daten["erstellt_am"])
            except Exception: pass
        else:
            kunden_db[name]["erstellt_am"] = now.isoformat()
            changed = True
            dt_erstellt = now
            
        if dt_letzte:
            if anonym_jahre > 0 and not name.startswith("Anonym_"):
                if now.year >= dt_letzte.year + int(anonym_jahre) + 1:
                    to_anonymize.append(name)
        else:
            if delete_monate > 0 and dt_erstellt:
                if (now - dt_erstellt).days / 30.44 >= delete_monate:
                    to_delete.append(name)
    
    for name in to_delete:
        del kunden_db[name]
        changed = True
    for name in to_anonymize:
        daten = kunden_db.pop(name)
        daten.update({"adresse": "ANONYMISIERT", "email": "", "uid": "", "pdf_passwort": "", "anonymisiert": True})
        kunden_db[f"Anonym_{int(now.timestamp())}_{random.randint(100, 999)}"] = daten
        changed = True
        
    if "rechnungen_db" in data:
        to_delete_rn = []
        for rn, r_daten in data["rechnungen_db"].items():
            if "datum" in r_daten:
                try:
                    dt_r = datetime.fromisoformat(r_daten["datum"])
                    if now.year >= dt_r.year + 8:
                        to_delete_rn.append(rn)
                except Exception: pass
        
        for rn in to_delete_rn:
            pfad = data["rechnungen_db"][rn].get("pfad", "")
            if pfad and os.path.exists(pfad):
                try: os.remove(pfad)
                except Exception: pass
                
                try:
                    ordner = os.path.dirname(pfad)
                    if not os.listdir(ordner): os.rmdir(ordner)
                except Exception: pass
                
            del data["rechnungen_db"][rn]
            changed = True

    return changed