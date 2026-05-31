# 🧾 EPU Rechnungsgenerator

Eine sichere, plattformübergreifende Open-Source-App zur Erstellung und Verwaltung von Rechnungen für Ein-Personen-Unternehmen (EPU), Freelancer und Kleinunternehmer.

Komplett **offline**, stark **verschlüsselt** und mit Fokus auf **Datenschutz (DSGVO)**.

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Kivy](https://img.shields.io/badge/Kivy-Cross--Platform-green.svg)
![Security](https://img.shields.io/badge/Security-AES--GCM-red.svg)
![License](https://img.shields.io/badge/License-GPLv3-blue.svg)

---

## ✨ Features

* **🔒 Absolute Datensicherheit:** Alle Kundendaten, Positionen und Einstellungen werden lokal gespeichert und mit **AES-256-GCM** und PBKDF2 (100.000 Iterationen) stark verschlüsselt. Keine Cloud, kein Abo-Zwang.
* **📄 Intelligente PDF-Generierung:** Erzeugt professionelle Rechnungen als PDF. Optional können Rechnungs-PDFs mit einem kundenindividuellen Passwort geschützt werden.
* **📱 Cross-Platform:** Läuft auf Windows, macOS, Linux und sogar nativ auf Android (inklusive Share-Sheet und MediaStore Integration).
* **💶 Scan2Pay (GiroCode):** Generiert automatisch EPC-QR-Codes auf der Rechnung, damit Kunden den Betrag bequem per Banking-App scannen und überweisen können.
* **⚖️ DSGVO-Konformität:** Integrierte Werkzeuge zur Erstellung von Datenauskünften als PDF und zur automatischen Löschung/Anonymisierung von Kunden nach Ablauf der Aufbewahrungsfrist.
* **💾 Backups:** Erstelle und importiere Backups deines gesamten Systems als stark verschlüsseltes ZIP-Archiv.

---

## 🛠️ Technologien

Dieses Projekt nutzt modernste Python-Bibliotheken:
* **GUI Framework:** [Kivy](https://kivy.org/)
* **Kryptografie:** [PyCryptodome](https://www.pycryptodome.org/)
* **PDF-Erstellung:** [fpdf2](https://pyfpdf.github.io/fpdf2/)
* **QR-Codes:** `qrcode`
* **Android-Integration:** `PyJnius` (für native Android-APIs wie SAF, MediaStore und Intents)

---

## 🚀 Installation & Start (Entwicklung)

### Voraussetzungen
* Python 3.8 oder höher
* pip (Python Package Installer)

### 1. Repository klonen
```bash
git clone https://github.com/DEIN_USERNAME/EPU_Rechnungsgenerator.git
cd EPU_Rechnungsgenerator
```

### 2. Abhängigkeiten installieren
Es wird empfohlen, eine virtuelle Umgebung (venv) zu verwenden.

```bash
# Erstellen und Aktivieren der venv
python -m venv venv
source venv/bin/activate  # Auf Windows: venv\Scripts\activate

# Pakete installieren
pip install -r requirements.txt
```
*(Hinweis: Falls noch nicht vorhanden, erstelle eine `requirements.txt` mit `kivy`, `fpdf2`, `pycryptodome`, `qrcode`, `Pillow`)*

### 3. App starten
```bash
python main.py
```

---

## 🏗️ Build (Executable / APK erstellen)

### 💻 Windows (PyInstaller)
Die Architektur ist bereits für PyInstaller vorbereitet. Kivy-Hooks und Vendor-Pfade werden in der `main.py` dynamisch erkannt.
```bash
pyinstaller --name "RechnungsAPP" --windowed --icon=icon.png main.py
```

### 🤖 Android (Buildozer)
Die Android-Builds erfordern Buildozer auf einem Linux-System (oder WSL).
Die App verwendet native Android-Klassen (MediaStore, Storage Access Framework). Stelle sicher, dass in deiner `buildozer.spec` folgende Berechtigungen gesetzt sind:
* `android.permissions = READ_EXTERNAL_STORAGE, WRITE_EXTERNAL_STORAGE, INTERNET`

```bash
buildozer android debug deploy run
```

---

## 📂 Wichtiger Hinweis zur Ordnerstruktur (`vendor` / `libs`)

Um Probleme mit PyInstaller und mobilen Deployments zu vermeiden, nutzt dieses Projekt teilweise das *Vendoring* von Modulen:
* `vendor/`: Dieser Ordner kann genutzt werden, um reine Python-Pakete (wie fpdf2) direkt im Projekt abzulegen, anstatt sie systemweit zu installieren.
* `libs/`: Zusätzliche Abhängigkeiten, die auf Desktop-Systemen in den `sys.path` geladen werden (nicht auf Android).

---

## 🤝 Contributing

Beiträge sind jederzeit willkommen! 
1. Forke das Projekt
2. Erstelle deinen Feature-Branch (`git checkout -b feature/NeuesFeature`)
3. Committe deine Änderungen (`git commit -m 'Füge ein großartiges neues Feature hinzu'`)
4. Pushe auf den Branch (`git push origin feature/NeuesFeature`)
5. Öffne einen Pull Request

---

## 📝 Lizenz

Dieses Projekt ist unter der GNU GPLv3 Lizenz lizenziert - siehe die `LICENSE` Datei für Details.

---
*Hinweis: Dieses Programm ersetzt keine rechtliche oder steuerliche Beratung. Die Verantwortung für die Richtigkeit der Rechnungen und die DSGVO-Konformität liegt beim Anwender.*