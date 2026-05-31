import os, json, sys, zipfile, re, webbrowser, urllib.parse, shutil, io

# PyInstaller / Kivy Pfad-Fix (Findet Dateien in der .exe)
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# Füge den 'libs' Ordner zum Python-Suchpfad hinzu (für Vendoring), ABER NICHT auf Android
if not hasattr(sys, 'getandroidapilevel'):
    sys.path.insert(0, os.path.join(base_path, 'libs'))

# 'vendor'-Ordner für reine Python-Pakete (z.B. fpdf2 und fonttools) laden
vendor_path = os.path.join(base_path, 'vendor')
if vendor_path not in sys.path: sys.path.insert(0, vendor_path)

from datetime import datetime
import kivy
from kivy.utils import platform
from kivy.config import Config

# Desktop-spezifische UI-Hacks (verhindert Bugs auf Android)
if platform in ('win', 'linux', 'macosx'):
    Config.set('input', 'mouse', 'mouse,disable_multitouch')
    
    if Config.has_option('input', 'wm_touch'): Config.remove_option('input', 'wm_touch')
    if Config.has_option('input', 'wm_pen'): Config.remove_option('input', 'wm_pen')
    
    # Scroll-Verzögerung für flüssigeres Klicken mit der PC-Maus anpassen
    Config.set('widgets', 'scroll_timeout', '55')
    Config.set('widgets', 'scroll_distance', '20')

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.logger import Logger
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.spinner import Spinner
from kivy.uix.checkbox import CheckBox
from kivy.lang import Builder
from kivy.clock import Clock, mainthread
from kivy.properties import DictProperty, StringProperty, NumericProperty, ListProperty, BooleanProperty
from kivy.core.window import Window
from kivy.uix.behaviors import ButtonBehavior
from kivy.factory import Factory

class NumericFloatInput(TextInput):
    def insert_text(self, substring, from_undo=False):
        s = substring.replace(',', '.')
        return super().insert_text(s, from_undo=from_undo)
Factory.register('NumericFloatInput', cls=NumericFloatInput)

class ClickableRow(ButtonBehavior, BoxLayout):
    pass

class PassiveCheckBox(CheckBox):
    # Diese Checkbox ignoriert Berührungen komplett.
    # So kann die übergeordnete ClickableRow den Touch fehlerfrei verarbeiten!
    def on_touch_down(self, touch): return False
    def on_touch_move(self, touch): return False
    def on_touch_up(self, touch): return False

# Lokale Module importieren (aufgespaltene Architektur)
from crypto import encrypt_data, decrypt_data
from dsgvo import cleanup_database
from pdf_gen import baue_pdf_im_ram, export_kunden_dsgvo_pdf, export_datenschutzerklaerung_pdf
from backup import create_backup, restore_backup
from platform_io import open_pdf, print_pdf, save_pdf_native, send_email_native, save_zip_native, choose_image_native, choose_zip_native, choose_directory_native, write_to_custom_dir, read_file_native

class InfoPopup(Popup):
    message = StringProperty("")

class BackupPasswordPopup(Popup):
    pass

class BackupFileChooserPopup(Popup):
    pass

class RestoreFileChooserPopup(Popup):
    pass

class RestorePasswordPopup(Popup):
    pass

class RechnungenExportPopup(Popup):
    zip_daten = None

class AppResetPopup(Popup):
    def reset_app(self):
        app = App.get_running_app()
        app.reset_app_database()
        self.dismiss()

Builder.load_string('''
<ExitConfirmPopup>:
    title: "App beenden?"
    size_hint: 0.8, 0.3
    auto_dismiss: False
    BoxLayout:
        orientation: 'vertical'
        padding: '10dp'
        spacing: '10dp'
        Label:
            text: "Möchtest du die App wirklich beenden?"
            halign: 'center'
            valign: 'middle'
        BoxLayout:
            size_hint_y: None
            height: '50dp'
            spacing: '10dp'
            Button:
                text: "Abbrechen"
                on_release: root.dismiss()
            Button:
                text: "Beenden"
                background_color: (0.8, 0.2, 0.2, 1)
                on_release: root.exit_app()
''')

class ExitConfirmPopup(Popup):
    def exit_app(self):
        App.get_running_app().stop()

Builder.load_string('''
<SpeicherOrdnerPopup>:
    title: "Speicherort für Autosave festlegen"
    size_hint: 0.9, 0.5
    auto_dismiss: False
    BoxLayout:
        orientation: 'vertical'
        spacing: '15dp'
        padding: '10dp'
        Label:
            text: "Möchtest du einen eigenen Ordner festlegen, in dem automatisch alle PDFs und Backups gespeichert werden?\\n\\nDies vereinfacht das spätere Teilen und Verwalten deiner Rechnungen."
            text_size: self.width, None
            halign: 'center'
            valign: 'middle'
        BoxLayout:
            size_hint_y: None
            height: '50dp'
            spacing: '10dp'
            Button:
                text: "Später / Standard"
                on_release: root.ueberspringen()
            Button:
                text: "Ordner wählen"
                background_color: 0.2, 0.7, 0.3, 1
                on_release: root.wahlen()
''')

class SpeicherOrdnerPopup(Popup):
    def wahlen(self):
        app = App.get_running_app()
        def callback(path):
            if path:
                if "meine_daten" not in app.data: app.data["meine_daten"] = {}
                app.data["meine_daten"]["speicher_ordner"] = path
                app.daten_speichern()
                app.show_info("Erfolg", "Der Autosave-Ordner wurde erfolgreich festgelegt!")
            self.dismiss()
        choose_directory_native(callback, app.target_os)
        
    def ueberspringen(self):
        app = App.get_running_app()
        if "meine_daten" not in app.data: app.data["meine_daten"] = {}
        app.data["meine_daten"]["speicher_ordner"] = "STANDARD"
        app.daten_speichern()
        self.dismiss()

class AboutPopup(Popup):
    pass

Builder.load_string('''
<RechnungenVerwaltenScreen>:
    BoxLayout:
        orientation: 'vertical'
        padding: '20dp'
        spacing: '10dp'
        Label:
            text: 'Rechnungen verwalten'
            font_size: '24sp'
            size_hint_y: None
            height: '40dp'
        BoxLayout:
            size_hint_y: None
            height: '45dp'
            spacing: '10dp'
            TextInput:
                id: search_input
                hint_text: 'Suche (Kunde, Jahr_Monat, RN)...'
                multiline: False
                on_text: root.filter_rechnungen(self.text)
            Button:
                text: 'Zurück'
                size_hint_x: 0.3
                on_release: app.root.current = 'main'
        ScrollView:
            BoxLayout:
                id: rechnungen_liste
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height
                spacing: '5dp'
''')

class RechnungenVerwaltenScreen(Screen):
    def on_pre_enter(self, *args):
        self.ids.search_input.text = ""
        self.filter_rechnungen("")

    def filter_rechnungen(self, text):
        app = App.get_running_app()
        container = self.ids.rechnungen_liste
        container.clear_widgets()
        db = app.data.get("rechnungen_db", {})
        sorted_rn = sorted(db.keys(), key=lambda x: int(x) if x.isdigit() else 0, reverse=True)
        
        for rn in sorted_rn:
            daten = db[rn]
            kunde = daten.get("kunde", "")
            datum_str = daten.get("datum", "")
            
            try:
                dt = datetime.fromisoformat(datum_str)
                anzeige_datum = dt.strftime("%d.%m.%Y")
                such_datum = dt.strftime("%Y_%m")
            except Exception:
                anzeige_datum = datum_str
                such_datum = datum_str
                
            if text:
                text_lower = text.lower()
                if text_lower not in kunde.lower() and text_lower not in such_datum and text_lower not in str(rn):
                    continue
                    
            from kivy.metrics import dp
            box = BoxLayout(orientation='horizontal', size_hint_y=None, height=dp(45), spacing=dp(10))
            lbl_info = Label(text=f"RN: {rn} | {anzeige_datum} | {kunde}", text_size=(None, None), halign='left', valign='middle')
            lbl_info.bind(size=lbl_info.setter('text_size'))
            btn_open = Button(text="Öffnen", size_hint_x=0.2)
            btn_open.bind(on_release=lambda btn, pfad=daten.get("pfad"): self.oeffne_rechnung(pfad))
            
            box.add_widget(lbl_info)
            box.add_widget(btn_open)
            container.add_widget(box)
            
    def oeffne_rechnung(self, pfad):
        app = App.get_running_app()
        if pfad and (str(pfad).startswith("content://") or os.path.exists(pfad)):
            try: open_pdf(pfad, app.target_os)
            except Exception as e: app.show_info("Fehler", f"Konnte PDF nicht öffnen:\n{e}")
        else:
            app.show_info("Fehler", "PDF-Datei wurde nicht gefunden oder gelöscht.")

class LongPressButton(Button):
    def __init__(self, **kwargs):
        self.register_event_type('on_long_press')
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if getattr(self, '_long_press', None):
                self._long_press.cancel()
            self._long_press = Clock.schedule_once(self.do_long_press, 2.0)
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if getattr(self, '_long_press', None):
            self._long_press.cancel()
        return super().on_touch_up(touch)

    def do_long_press(self, dt):
        if self.state == 'down':
            self.dispatch('on_long_press')

    def on_long_press(self, *args):
        pass

class LogoAuswahlPopup(Popup):
    target_input = None
    def auswaehlen(self, selection):
        if selection and self.target_input:
            self.target_input.text = selection[0]
        self.dismiss()

class OSSelectionPopup(Popup):
    def select_os(self, os_name):
        app = App.get_running_app()
        app.set_target_os(os_name)
        self.dismiss()

class LoginScreen(Screen):
    def on_pre_enter(self, *args):
        from kivy.metrics import dp
        app = App.get_running_app()
        self.ids.pwd_input.text = ""
        self.ids.pwd_confirm.text = ""
        if 'dsgvo_checkbox' in self.ids:
            self.ids.dsgvo_checkbox.active = False
            
        if not os.path.exists(app.data_path):
            self.is_setup = True
            self.ids.error_lbl.text = "Ersteinrichtung: Bitte neues Master-Passwort festlegen"
            self.ids.error_lbl.color = (0.3, 1, 0.3, 1)
            self.ids.pwd_confirm.opacity = 1
            self.ids.pwd_confirm.size_hint_y = None
            self.ids.pwd_confirm.height = dp(45)
            self.ids.dsgvo_box.opacity = 1
            self.ids.dsgvo_box.size_hint_y = None
            self.ids.dsgvo_box.height = dp(120)
            self.ids.btn_login.text = "Datenbank verschlüsseln & Speichern"
            
            if not hasattr(self, 'btn_restore'):
                self.btn_restore = Button(text="Oder: Aus Backup wiederherstellen", size_hint_y=None, height=dp(45), background_color=(0.2, 0.6, 0.8, 1))
                self.btn_restore.bind(on_release=lambda x: app.backup_einspielen_erststart())
                self.ids.btn_login.parent.add_widget(self.btn_restore)
        else:
            self.is_setup = False
            self.ids.error_lbl.text = "Datenbank gefunden. Bitte entsperren:"
            self.ids.error_lbl.color = (1, 1, 1, 1)
            self.ids.pwd_confirm.opacity = 0
            self.ids.pwd_confirm.size_hint_y = None
            self.ids.pwd_confirm.height = 0
            self.ids.dsgvo_box.opacity = 0
            self.ids.dsgvo_box.size_hint_y = None
            self.ids.dsgvo_box.height = 0
            self.ids.btn_login.text = "Entsperren"
            
            if hasattr(self, 'btn_restore') and self.btn_restore.parent:
                self.btn_restore.parent.remove_widget(self.btn_restore)

    def do_login(self):
        app = App.get_running_app()
        pwd = self.ids.pwd_input.text.strip()
        if not pwd:
            self.ids.error_lbl.text = "Passwort darf nicht leer sein!"
            self.ids.error_lbl.color = (1, 0.3, 0.3, 1)
            return
            
        if getattr(self, 'is_setup', False):
            if pwd != self.ids.pwd_confirm.text.strip():
                self.ids.error_lbl.text = "Passwörter stimmen nicht überein!"
                self.ids.error_lbl.color = (1, 0.3, 0.3, 1)
                return
            if not self.ids.dsgvo_checkbox.active:
                self.ids.error_lbl.text = "Bitte den DSGVO-Hinweis bestätigen!"
                self.ids.error_lbl.color = (1, 0.3, 0.3, 1)
                return
            app.show_folder_popup_after_main_info = True
            app.do_ersteinrichtung(pwd)
        else:
            data = decrypt_data(pwd, app.data_path, app.salt_path)
            if data:
                app.data = data
                app.master_password = pwd
                
                restored_logo_found = False
                for ext in [".png", ".jpg", ".jpeg"]:
                    old_path = os.path.join(app.user_data_dir, f"restored_logo{ext}")
                    if os.path.exists(old_path):
                        if "meine_daten" not in app.data: app.data["meine_daten"] = {}
                        app.data["meine_daten"]["logo_pfad"] = old_path
                        restored_logo_found = True
                        break

                db_changed = False
                rechnungen_dir = os.path.join(app.user_data_dir, "Rechnungen")
                
                if hasattr(app, 'temp_restored_pdfs') and app.temp_restored_pdfs:
                    if "rechnungen_db" in app.data:
                        for rn, r_daten in app.data["rechnungen_db"].items():
                            old_pfad = r_daten.get("pfad", "")
                            if old_pfad:
                                parts = old_pfad.replace('\\', '/').split('/')
                                if len(parts) >= 2:
                                    folder_name = parts[-2]
                                    file_name = parts[-1]
                                    rel_path = f"Rechnungen/{folder_name}/{file_name}"
                                    if rel_path in app.temp_restored_pdfs:
                                        r_daten["pfad"] = app.temp_restored_pdfs[rel_path]
                                        db_changed = True
                    app.temp_restored_pdfs = None
                    
                if hasattr(app, 'temp_erststart_ordner'):
                    if app.temp_erststart_ordner:
                        if "meine_daten" not in app.data: app.data["meine_daten"] = {}
                        app.data["meine_daten"]["speicher_ordner"] = app.temp_erststart_ordner
                        db_changed = True
                    del app.temp_erststart_ordner
                    
                if "rechnungen_db" in app.data:
                    for rn, r_daten in app.data["rechnungen_db"].items():
                        old_pfad = r_daten.get("pfad", "")
                        if old_pfad and not str(old_pfad).startswith("content://"):
                            # Pfade nur reparieren, wenn die Datei an ihrem aktuellen Ort nicht mehr existiert
                            if not os.path.exists(old_pfad):
                                parts = old_pfad.replace('\\', '/').split('/')
                                if len(parts) >= 2:
                                    folder_name = parts[-2]
                                    file_name = parts[-1]
                                    
                                    speicher_ordner = app.data.get("meine_daten", {}).get("speicher_ordner")
                                    found = False
                                    if speicher_ordner and speicher_ordner != "STANDARD" and not str(speicher_ordner).startswith("content://"):
                                        test_pfad = os.path.join(speicher_ordner, folder_name, file_name)
                                        if os.path.exists(test_pfad):
                                            r_daten["pfad"] = test_pfad
                                            db_changed = True
                                            found = True
                                            
                                    if not found:
                                        test_pfad = os.path.join(app.user_data_dir, "Rechnungen", folder_name, file_name)
                                        if os.path.exists(test_pfad) and test_pfad != old_pfad:
                                            r_daten["pfad"] = test_pfad
                                            db_changed = True

                app.cleanup_database()
                if restored_logo_found or db_changed:
                    app.daten_speichern()
                
                speicher_ordner = app.data.get("meine_daten", {}).get("speicher_ordner")
                valid_ordner = False
                if speicher_ordner == "STANDARD":
                    valid_ordner = True
                elif speicher_ordner and isinstance(speicher_ordner, str):
                    if speicher_ordner.startswith("content://") or os.path.exists(speicher_ordner):
                        valid_ordner = True
                        
                if not valid_ordner:
                    app.show_folder_popup_after_main_info = True
                self.manager.current = 'main'
            else:
                self.ids.pwd_input.text = ""
                self.ids.error_lbl.text = "Falsches Passwort!"
                self.ids.error_lbl.color = (1, 0.3, 0.3, 1)

class MainScreen(Screen):
    def on_enter(self, *args):
        app = App.get_running_app()
        info_text = (
            "Willkommen im Hauptmenü!\n\n"
            "Von hier aus steuerst du alle Hauptfunktionen:\n\n"
            "[b]Neue Rechnung:[/b] Starte den Prozess zur Erstellung einer neuen Rechnung.\n"
            "[b]Rechnungen verwalten:[/b] Durchsuche und öffne bereits erstellte Rechnungen.\n"
            "[b]Einstellungen:[/b] Hinterlege deine Firmendaten, Logo und passe die App an.\n"
            "[b]Datenbank & Backup:[/b] Erstelle Sicherheitskopien deiner Daten."
        )
        
        def check_and_show_folder_popup(*args_event):
            if getattr(app, 'show_folder_popup_after_main_info', False):
                app.show_folder_popup_after_main_info = False
                SpeicherOrdnerPopup().open()

        popup = app.show_first_visit_info('main', 'Info: Hauptmenü', info_text)
        if popup:
            popup.bind(on_dismiss=check_and_show_folder_popup)
        else:
            check_and_show_folder_popup()

class DatenbankScreen(Screen):
    def on_enter(self, *args):
        app = App.get_running_app()
        info_text = (
            "Hier verwaltest du die Datensicherheit.\n\n"
            "[b]WICHTIG: Erstelle regelmäßig Backups![/b]\n\n"
            "- [b]Backup erstellen:[/b] Sichert deine komplette Datenbank in einer verschlüsselten ZIP-Datei.\n\n"
            "- [b]Backup einspielen:[/b] Stellt einen früheren Datenstand wieder her.\n\n"
            "- [b]Rechnungen exportieren:[/b] Erstellt ein ZIP-Archiv mit allen PDF-Rechnungen."
        )
        app.show_first_visit_info('datenbank', 'Info: Datenbank & Backup', info_text)

class EinstellungenScreen(Screen):
    fields = [
        ("firma", "Firmenname:", "text"), ("strasse", "Straße / Hausnr:", "text"), ("plz_ort", "PLZ / Ort:", "text"),
        ("email", "E-Mail-Adresse:", "text"), ("tel", "Telefonnummer:", "text"), ("uid", "Deine UID-Nummer:", "text"),
        ("iban", "IBAN:", "text"), ("bic", "BIC:", "text"), ("steuersatz", "Standard Steuersatz (%):", "text"),
        ("zahlungsziel", "Standard Zahlungsziel (Tage):", "text"), 
        ("skonto_prozent", "Globaler Skonto-Satz (%):", "text"), ("skonto_tage", "Globale Skonto-Frist (Tage):", "text"),
        ("custom_footer", "Eigener Rechnungs-Footer (optional):", "text_multi"),
        ("anonymisieren_nach_jahren", "Kunden mit Umsatz anonymisieren (Jahre, 0 für AUS):", "text"),
        ("interessenten_loeschen_monate", "Interessenten ohne Umsatz löschen (Monate, 0 für AUS):", "text"),
        ("auto_lock_minuten", "Autom. App-Sperre nach (Minuten, 0 für AUS):", "text"),
        ("qr_aktiv", "QR-Code auf Rechnung:", "toggle"),
        ("logo_aktiv", "Logo auf Rechnung:", "toggle"),
        ("logo_pfad", "Logo Dateipfad:", "file"),
        ("logo_width", "Logo Breite (px):", "text"),
        ("logo_height", "Logo Höhe (px):", "text"),
        ("logo_margin_top", "Logo Abstand von oben (px):", "text"),
        ("logo_margin_right", "Logo Abstand von rechts (px):", "text"),
        ("speicher_ordner", "Speicherordner (Autosave & Backup):", "dir_auswahl"),
        ("os_auswahl", "Betriebssystem (PDF & Druck):", "os_spinner"),
        ("naechste_nummer", "Nächste Rechnungsnummer:", "text")
    ]
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.inputs = {}
        Clock.schedule_once(self.build_ui)

    def build_ui(self, dt):
        from kivy.metrics import dp, sp
        container = self.ids.fields_container
        for item in self.fields:
            key = item[0]
            label_text = item[1]
            ftype = item[2] if len(item) > 2 else "text"
            
            # Vertikales Layout pro Element: Oben das Label, darunter das Eingabefeld (ideal für mobile Screens)
            box = BoxLayout(orientation='vertical', size_hint_y=None, spacing=dp(2))
            
            lbl = Label(text=label_text, size_hint_y=None, height=dp(20), halign='left', valign='bottom', font_size=sp(13), color=(0.8, 0.8, 0.8, 1))
            lbl.bind(size=lbl.setter('text_size'))
            box.add_widget(lbl)
            
            input_height = dp(70) if ftype == 'text_multi' else dp(35)
            box.height = dp(20) + input_height + dp(2)
            
            input_box = BoxLayout(orientation='horizontal', size_hint_y=None, height=input_height, spacing=dp(5))
            
            if ftype == 'text':
                ti = TextInput(size_hint_x=1, multiline=False, font_size=sp(14))
                input_box.add_widget(ti)
                self.inputs[key] = ti
            elif ftype == 'text_multi':
                ti = TextInput(size_hint_x=1, multiline=True, font_size=sp(14))
                input_box.add_widget(ti)
                self.inputs[key] = ti
            elif ftype == 'password':
                ti = TextInput(size_hint_x=1, multiline=False, password=True, font_size=sp(14))
                input_box.add_widget(ti)
                self.inputs[key] = ti
            elif ftype == 'toggle':
                ti = Spinner(text='Ja', values=('Ja', 'Nein'), size_hint_x=1, font_size=sp(14))
                input_box.add_widget(ti)
                self.inputs[key] = ti
            elif ftype == 'file':
                ti = TextInput(size_hint_x=0.7, multiline=False, font_size=sp(14))
                btn = Button(text="...", size_hint_x=0.3, font_size=sp(14))
                btn.bind(on_release=lambda btn_instance, t=ti: self.oeffne_logo_auswahl(t))
                input_box.add_widget(ti)
                input_box.add_widget(btn)
                self.inputs[key] = ti
            elif ftype == 'dir_auswahl':
                ti = TextInput(size_hint_x=0.7, multiline=False, font_size=sp(14))
                btn = Button(text="Wählen", size_hint_x=0.3, font_size=sp(14))
                btn.bind(on_release=lambda btn_instance, t=ti: self.oeffne_ordner_auswahl(t))
                input_box.add_widget(ti)
                input_box.add_widget(btn)
                self.inputs[key] = ti
            elif ftype == 'os_spinner':
                ti = Spinner(text='windows', values=('windows', 'unix', 'mobile'), size_hint_x=1, font_size=sp(14))
                input_box.add_widget(ti)
                self.inputs[key] = ti

            box.add_widget(input_box)
            container.add_widget(box)
            
    def oeffne_logo_auswahl(self, target_input):
        app = App.get_running_app()
        
        def on_selection(selection):
            if selection and len(selection) > 0 and selection[0] is not None and str(selection[0]) != "None":
                Clock.schedule_once(lambda dt: setattr(target_input, 'text', str(selection[0])))
                
        res = choose_image_native(on_selection, app.target_os)
        if res == "KIVY_FALLBACK":
            popup = LogoAuswahlPopup()
            popup.target_input = target_input
            popup.open()

    def oeffne_ordner_auswahl(self, target_input):
        app = App.get_running_app()
        def callback(path):
            if path:
                Clock.schedule_once(lambda dt: setattr(target_input, 'text', path))
        choose_directory_native(callback, app.target_os)

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        meine_daten = app.data.get("meine_daten", {})
        for key, ti in self.inputs.items():
            if key == "naechste_nummer":
                val = str(app.data.get("naechste_nummer", 1))
            elif key == "os_auswahl":
                val = app.target_os
            else:
                val = str(meine_daten.get(key, ""))
                
            if not val:
                if key == "anonymisieren_nach_jahren": val = "7"
                elif key == "interessenten_loeschen_monate": val = "12"
                elif key == "auto_lock_minuten": val = "5"
                elif key == "steuersatz": val = "20"

            if isinstance(ti, Spinner):
                if not val: ti.text = 'Ja'
                else: ti.text = val
            else:
                ti.text = val
            
    def speichern(self):
        app = App.get_running_app()
        if "meine_daten" not in app.data:
            app.data["meine_daten"] = {}
        for key, ti in self.inputs.items():
            if key == "naechste_nummer":
                try:
                    app.data["naechste_nummer"] = int(ti.text.strip())
                except ValueError:
                    app.show_info("Fehler", "Die Rechnungsnummer muss eine gültige Zahl sein!")
                    return
            elif key == "os_auswahl":
                app.set_target_os(ti.text)
            else:
                app.data["meine_daten"][key] = ti.text.strip()
        app.daten_speichern()
        app.show_info("Erfolg", "Einstellungen wurden gespeichert!")

class DatenschutzerklaerungPopup(Popup):
    def on_open(self):
        app = App.get_running_app()
        meine_daten = app.data.get("meine_daten", {})
        standard_text = meine_daten.get("datenschutzerklaerung", "")
        
        if not standard_text:
            firma = meine_daten.get("firma", "[Dein Firmenname]")
            strasse = meine_daten.get("strasse", "")
            plz_ort = meine_daten.get("plz_ort", "")
            adresse = f"{strasse}, {plz_ort}".strip(', ')
            if not adresse: adresse = "[Adresse]"
            email = meine_daten.get("email", "[E-Mail]")
            tel = meine_daten.get("tel", "[Telefon – optional]")
            
            standard_text = f""" Datenschutzerklärung

Verantwortlicher
{firma}
{adresse}
{email}
{tel}

 Zweck der Datenverarbeitung

Im Rahmen unserer Geschäftstätigkeit verarbeiten wir personenbezogene Daten zur:

Erstellung von Angeboten und Rechnungen
Abwicklung von Kundenaufträgen
Erfüllung gesetzlicher Aufbewahrungspflichten

 Rechtsgrundlage

Die Verarbeitung erfolgt auf Grundlage von:

Art. 6 Abs. 1 lit. b DSGVO (Vertragserfüllung)
zur Durchführung vorvertraglicher Maßnahmen und zur Erfüllung von Verträgen
Art. 6 Abs. 1 lit. c DSGVO (rechtliche Verpflichtung)
insbesondere steuerrechtliche Aufbewahrungspflichten

 Verarbeitete Daten

Folgende Daten können verarbeitet werden:

Name / Firmenname
Adresse
UID-Nummer (falls vorhanden)
E-Mail-Adresse (optional)
Zahlungsinformationen (z. B. IBAN/BIC)
Rechnungs- und Leistungsdaten

 Speicherung und Sicherheit

Die Daten werden:

lokal auf einem geschützten System gespeichert
verschlüsselt (AES-basierte Verschlüsselung) verarbeitet
nach dem Prinzip der Datenminimierung behandelt

Zusätzlich werden:

automatische Sperrmechanismen (Inaktivität) eingesetzt
personenbezogene Daten nach Ablauf gesetzlicher Fristen anonymisiert oder gelöscht

 Speicherdauer
Rechnungsdaten: 7 Jahre (gemäß BAO, Österreich)
Interessenten ohne Geschäftsabschluss: max. 12 Monate

Nach Ablauf dieser Fristen werden Daten:

gelöscht oder
anonymisiert

 Weitergabe von Daten

Eine Weitergabe erfolgt nur wenn erforderlich, z. B.:

an Steuerberater
an Behörden (Finanzamt)

Es erfolgt keine Weitergabe zu Marketingzwecken.

 E-Mail-Kommunikation

Rechnungen können per E-Mail versendet werden.

Dabei werden PDF-Dokumente optional passwortgeschützt übertragen
Es wird darauf hingewiesen, dass E-Mail-Kommunikation Sicherheitsrisiken bergen kann

 Backups

Zur Datensicherung können verschlüsselte Backups erstellt werden.

Diese enthalten personenbezogene Daten und sind entsprechend sicher aufzubewahren.

 Rechte der betroffenen Personen

Sie haben das Recht auf:

Auskunft (Art. 15 DSGVO)
Berichtigung (Art. 16 DSGVO)
Löschung (Art. 17 DSGVO)
Einschränkung der Verarbeitung (Art. 18 DSGVO)
Datenübertragbarkeit (Art. 20 DSGVO)
Kontakt

Anfragen richten Sie bitte an:

{email}"""
        
        self.ids.txt_dsgvo.text = standard_text

    def speichern(self):
        app = App.get_running_app()
        if "meine_daten" not in app.data:
            app.data["meine_daten"] = {}
        app.data["meine_daten"]["datenschutzerklaerung"] = self.ids.txt_dsgvo.text.strip()
        app.daten_speichern()
        app.show_info("Gespeichert", "Datenschutzerklärung wurde in der verschlüsselten Datenbank gespeichert.")
        self.dismiss()

    def als_pdf_exportieren(self):
        app = App.get_running_app()
        if "meine_daten" not in app.data:
            app.data["meine_daten"] = {}
        app.data["meine_daten"]["datenschutzerklaerung"] = self.ids.txt_dsgvo.text.strip()
        app.daten_speichern()
        self.dismiss()
        app.export_datenschutzerklaerung_pdf()

class PositionItem(ButtonBehavior, BoxLayout):
    index = NumericProperty(-1)
    beschr = StringProperty("")
    menge = StringProperty("")
    einh = StringProperty("")
    mwst = StringProperty("")
    ep = StringProperty("")
    ges = StringProperty("")
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if getattr(self, '_long_press', None):
                self._long_press.cancel()
            self._long_press = Clock.schedule_once(self.do_long_press, 0.8)
        return super().on_touch_down(touch)
        
    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            if hasattr(self, '_long_press'):
                self._long_press.cancel()
        return super().on_touch_up(touch)
        
    def do_long_press(self, dt):
        app = App.get_running_app()
        rs = app.root.get_screen('rechnung')
        rs.zeige_loesch_popup(self.index)

class KundeVerwaltenPopup(Popup):
    def on_open(self):
        app = App.get_running_app()
        kunden = list(app.data.get("kunden_db", {}).keys())
        self.ids.kv_spinner.values = kunden

    def lade_kunden_daten(self, name):
        app = App.get_running_app()
        db = app.data.get("kunden_db", {})
        if name in db:
            daten = db[name]
            self.ids.kv_name.text = name
            self.ids.kv_einmalig.active = False
            self.ids.kv_adresse.text = daten.get("adresse", "")
            self.ids.kv_uid.text = daten.get("uid", "")
            self.ids.kv_email.text = daten.get("email", "")
            self.ids.kv_zz.text = str(daten.get("zahlungsziel", ""))
            self.ids.kv_sk_prozent.text = str(daten.get("skonto_prozent", ""))
            self.ids.kv_sk_tage.text = str(daten.get("skonto_tage", ""))
            self.ids.kv_pdf_pwd.text = daten.get("pdf_passwort", "")
            
    def check_existing(self, text):
        if 'btn_dsgvo' not in self.ids: return
        app = App.get_running_app()
        if app.data and "kunden_db" in app.data and text.strip() in app.data["kunden_db"]:
            self.ids.btn_dsgvo.disabled = False
            self.ids.btn_delete_kunde.disabled = False
        else:
            self.ids.btn_dsgvo.disabled = True
            self.ids.btn_delete_kunde.disabled = True

    def speichern(self):
        app = App.get_running_app()
        name = self.ids.kv_name.text.strip()
        adresse = self.ids.kv_adresse.text.strip()
        einmalig = self.ids.kv_einmalig.active
        
        if not name or not adresse:
            app.show_info("Fehler", "Name und Adresse sind Pflichtfelder!")
            return
            
        daten = {
            "adresse": adresse, "uid": self.ids.kv_uid.text.strip(), "email": self.ids.kv_email.text.strip(),
            "zahlungsziel": self.ids.kv_zz.text.strip(), "skonto_prozent": self.ids.kv_sk_prozent.text.strip(),
            "skonto_tage": self.ids.kv_sk_tage.text.strip(), "pdf_passwort": self.ids.kv_pdf_pwd.text.strip()
        }
        
        rs = app.root.get_screen('rechnung')
        
        if not einmalig:
            if "kunden_db" not in app.data:
                app.data["kunden_db"] = {}
            existing = app.data["kunden_db"].get(name, {})
            daten["erstellt_am"] = existing.get("erstellt_am", datetime.now().isoformat())
            if "letzte_rechnung_datum" in existing:
                daten["letzte_rechnung_datum"] = existing["letzte_rechnung_datum"]
                
            app.data["kunden_db"][name] = daten
            app.daten_speichern()
            rs.filter_kunden(rs.ids.kunde_suche.text)
            rs.ids.kunde_spinner.text = name
            app.show_info("Erfolg", f"Kunde '{name}' gespeichert.")
        else:
            rs.set_einmaligen_kunden(name, daten)
            app.show_info("Info", f"Kunde '{name}' wird nur für diese Rechnung verwendet.")
        self.dismiss()

    def dsgvo_auskunft(self):
        app = App.get_running_app()
        name = self.ids.kv_name.text.strip()
        db = app.data.get("kunden_db", {})
        if name in db:
            app.export_kunden_dsgvo_pdf(name, db[name])

    def kunde_loeschen_abfrage(self):
        name = self.ids.kv_name.text.strip()
        if name:
            app = App.get_running_app()
            kunden_db = app.data.get("kunden_db", {})
            warn_text = ""
            if name in kunden_db:
                daten = kunden_db[name]
                if "letzte_rechnung_datum" in daten:
                    try:
                        dt_letzte = datetime.fromisoformat(daten["letzte_rechnung_datum"])
                        jahre_vergangen = (datetime.now() - dt_letzte).days / 365.25
                        if jahre_vergangen < 7:
                            warn_text = f"WARNUNG: Gemäß Steuerrecht müssen Rechnungsdaten 7 Jahre aufbewahrt werden!\nLetzte Rechnung: {dt_letzte.strftime('%d.%m.%Y')}"
                    except Exception: pass

            popup = KundeLoeschenPopup()
            popup.kunden_name = name
            popup.warn_text = warn_text
            popup.parent_popup = self
            popup.open()

class KundeLoeschenPopup(Popup):
    kunden_name = StringProperty("")
    warn_text = StringProperty("")
    parent_popup = None
    
    def loeschen(self):
        app = App.get_running_app()
        if "kunden_db" in app.data and self.kunden_name in app.data["kunden_db"]:
            del app.data["kunden_db"][self.kunden_name]
            app.daten_speichern()
            rs = app.root.get_screen('rechnung')
            rs.filter_kunden(rs.ids.kunde_suche.text)
            rs.ids.kunde_spinner.text = 'Kunde wählen'
            app.show_info("Erfolg", f"Kunde '{self.kunden_name}' wurde dauerhaft gelöscht.")
            if self.parent_popup:
                self.parent_popup.dismiss()
        self.dismiss()

class PositionLoeschenPopup(Popup):
    index = NumericProperty(-1)
    def loeschen(self):
        app = App.get_running_app()
        rs = app.root.get_screen('rechnung')
        if 0 <= self.index < len(rs.aktuelle_positionen):
            del rs.aktuelle_positionen[self.index]
            rs.update_positions_liste()
        self.dismiss()

class GespeichertePositionLoeschenPopup(Popup):
    position_name = StringProperty("")
    def loeschen(self):
        app = App.get_running_app()
        if "positionen_db" in app.data and self.position_name in app.data["positionen_db"]:
            del app.data["positionen_db"][self.position_name]
            app.daten_speichern()
            rs = app.root.get_screen('rechnung')
            rs.filter_positionen(rs.ids.pos_suche.text)
            rs.ids.pos_spinner.text = 'Position wählen'
            rs.ids.einheit_input.text = "Stk"
            rs.ids.preis_input.text = ""
        self.dismiss()

class ZeitraumPopup(Popup):
    mode = StringProperty("Pauschal Monat")
    
    def on_open(self):
        now = datetime.now()
        if self.mode == "Jahr":
            self.ids.jahr_input.text = now.strftime("%Y")
            self.ids.monat_input.opacity = 0
            self.ids.monat_input.disabled = True
            self.ids.monat_input.size_hint_x = None
            self.ids.monat_input.width = 0
        else:
            self.ids.monat_input.text = now.strftime("%m")
            self.ids.jahr_input.text = now.strftime("%y")
            self.ids.monat_input.opacity = 1
            self.ids.monat_input.disabled = False
            self.ids.monat_input.size_hint_x = 1

    def uebernehmen(self):
        app = App.get_running_app()
        rs = app.root.get_screen('rechnung')
        monat = self.ids.monat_input.text.strip()
        jahr = self.ids.jahr_input.text.strip()
        
        if jahr:
            if self.mode == "Jahr":
                if len(jahr) == 2: jahr = "20" + jahr
                zeitraum = jahr
            else:
                if len(monat) == 1: monat = "0" + monat
                if len(jahr) == 4: jahr = jahr[2:]
                elif len(jahr) == 1: jahr = "0" + jahr
                zeitraum = f"{monat}/{jahr}"
                
            beschr = rs.ids.pos_suche.text.strip()
            if not beschr:
                beschr = rs.ids.pos_spinner.text.strip()
                if beschr == "Position wählen":
                    beschr = ""
            
            # Entfernt alte Datumsanhänge (wie 05/23, 05/2023 oder 2024) vor dem neu Setzen
            beschr = re.sub(r'\s*(\d{2}/\d{2,4}|\d{4})$', '', beschr).strip()
            
            if beschr:
                rs.ids.pos_suche.text = f"{beschr} {zeitraum}"
            else:
                rs.ids.pos_suche.text = zeitraum
                
        self.dismiss()

class PdfAktionPopup(Popup):
    pdf_daten = None
    pdf_pfad = StringProperty("")
    kunde_name = StringProperty("")
    kunde_daten = DictProperty({})
    has_email = BooleanProperty(False)
    rechnungsnummer = NumericProperty(0)
    positionen = ListProperty([])

    def save_temp_pdf(self):
        if not self.pdf_daten: return None
        app = App.get_running_app()
        temp_path = os.path.join(app.user_data_dir, f"temp_rechnung.pdf")
        with open(temp_path, "wb") as f: f.write(self.pdf_daten)
        return temp_path

    def anzeigen(self):
        path = self.pdf_pfad if self.pdf_pfad and (str(self.pdf_pfad).startswith("content://") or os.path.exists(self.pdf_pfad)) else self.save_temp_pdf()
        if not path: return
        app = App.get_running_app()
        try: open_pdf(path, app.target_os)
        except Exception as e: app.show_info("Fehler", f"Konnte PDF nicht öffnen:\n{e}")

    def drucken(self):
        path = self.pdf_pfad if self.pdf_pfad and (str(self.pdf_pfad).startswith("content://") or os.path.exists(self.pdf_pfad)) else self.save_temp_pdf()
        if not path: return
        app = App.get_running_app()
        try: print_pdf(path, app.target_os)
        except Exception as e: app.show_info("Fehler", f"Konnte Druck nicht starten:\n{e}")

    def speichern(self):
        app = App.get_running_app()
        default_fn = f"Rechnung_{self.rechnungsnummer}.pdf"
        custom_dir = app.data.get("meine_daten", {}).get("speicher_ordner")
        res = save_pdf_native(self.pdf_daten, default_fn, app.target_os, custom_dir)
        if res != "KIVY_FALLBACK":
            if res:
                app.show_info("Erfolg", f"PDF gespeichert unter:\n{res}")
        else:
            popup = PdfSpeichernPopup()
            popup.default_filename = default_fn
            popup.pdf_daten = self.pdf_daten
            popup.open()
        self.dismiss()

    def speichern_pw(self):
        popup = PdfPasswortPopup()
        popup.kunde_name = self.kunde_name
        popup.kunde_daten = self.kunde_daten
        popup.rechnungsnummer = self.rechnungsnummer
        popup.positionen = self.positionen
        pw = self.kunde_daten.get('pdf_passwort', '')
        popup.has_kunden_pw = bool(pw)
        popup.ids.pdf_pw.text = pw
        popup.open()
        self.dismiss()

    def send_email(self):
        self._prepare_and_open_email(pw_geschuetzt=False)
        
    def send_email_pw(self):
        self._prepare_and_open_email(pw_geschuetzt=True)
        
    def _prepare_and_open_email(self, pw_geschuetzt):
        email = self.kunde_daten.get('email', '')
        if not email: return
        app = App.get_running_app()
        
        attachment_path = self.pdf_pfad
        
        if pw_geschuetzt:
            pw = self.kunde_daten.get('pdf_passwort', '')
            if not pw:
                app.show_info("Fehler", "Kein PDF-Passwort beim Kunden hinterlegt!\nBitte im Kundenprofil einstellen.")
                return
            pdf_daten_pw = baue_pdf_im_ram(
                app.data.get("meine_daten", {}), 
                self.kunde_name, 
                self.kunde_daten, 
                self.rechnungsnummer, 
                self.positionen, 
                passwort=pw
            )
            attachment_path = os.path.join(app.user_data_dir, f"Rechnung_{self.rechnungsnummer}_verschluesselt.pdf")
            with open(attachment_path, "wb") as f: f.write(pdf_daten_pw)
        elif not (attachment_path and (str(attachment_path).startswith("content://") or os.path.exists(attachment_path))):
            attachment_path = os.path.join(app.user_data_dir, f"Rechnung_{self.rechnungsnummer}.pdf")
            with open(attachment_path, "wb") as f: f.write(self.pdf_daten)

        subject = f"Rechnung {self.rechnungsnummer}"
        body = f"Sehr geehrte Damen und Herren,\n\nanbei erhalten Sie die Rechnung {self.rechnungsnummer} als PDF-Dokument.\n\n"
        if pw_geschuetzt:
            body += "Das Dokument ist mit Ihrem persönlichen Kunden-Passwort geschützt.\n\n"
        body += "Mit freundlichen Grüßen,\n" + app.data.get("meine_daten", {}).get("firma", "")
        
        try:
            is_mobile = send_email_native(email, subject, body, attachment_path, app.target_os)
            if not is_mobile:
                app.show_info("E-Mail vorbereitet", "Dein E-Mail-Programm sowie der Ordner mit der Rechnung wurden geöffnet.\n\nBitte ziehe die PDF-Datei nun einfach per Drag & Drop als Anhang in die E-Mail!")
        except Exception as e:
            app.show_info("Fehler", str(e))
        self.dismiss()

class PdfSpeichernPopup(Popup):
    default_filename = StringProperty("")
    pdf_daten = None
    def save_pdf(self, path, filename):
        if not filename.lower().endswith('.pdf'): filename += '.pdf'
        full_path = os.path.join(path, filename)
        try:
            with open(full_path, "wb") as f: f.write(self.pdf_daten)
            App.get_running_app().show_info("Erfolg", f"PDF gespeichert unter:\n{full_path}")
            self.dismiss()
        except Exception as e:
            App.get_running_app().show_info("Fehler", f"Konnte PDF nicht speichern:\n{str(e)}")

class PdfPasswortPopup(Popup):
    kunde_name = StringProperty("")
    kunde_daten = DictProperty({})
    rechnungsnummer = NumericProperty(0)
    positionen = ListProperty([])
    has_kunden_pw = BooleanProperty(False)
    
    def weiter(self):
        pw = self.ids.pdf_pw.text.strip()
        if not pw: return App.get_running_app().show_info("Fehler", "Passwort darf nicht leer sein!")
        app = App.get_running_app()
        pdf_daten = baue_pdf_im_ram(app.data.get("meine_daten", {}), self.kunde_name, self.kunde_daten, self.rechnungsnummer, self.positionen, passwort=pw)
        if pdf_daten:
            default_fn = f"Rechnung_{self.rechnungsnummer}_verschluesselt.pdf"
            custom_dir = app.data.get("meine_daten", {}).get("speicher_ordner")
            res = save_pdf_native(pdf_daten, default_fn, app.target_os, custom_dir)
            if res != "KIVY_FALLBACK":
                if res:
                    app.show_info("Erfolg", f"PDF gespeichert unter:\n{res}")
            else:
                popup = PdfSpeichernPopup()
                popup.default_filename = default_fn
                popup.pdf_daten = pdf_daten
                popup.open()
        self.dismiss()

class RechnungScreen(Screen):
    aktuelle_positionen = ListProperty([])
    temp_kunden_daten = DictProperty({})

    def on_enter(self, *args):
        app = App.get_running_app()
        info_text = (
            "Hier erstellst du neue Rechnungen.\n\n"
            "[b]Workflow:[/b]\n"
            "1. [b]Kunde wählen:[/b] Lade einen Kunden. Über [b]'Kunde verwalten'[/b] kannst du neue Kunden anlegen, bearbeiten oder löschen.\n\n"
            "2. [b]Positionen hinzufügen:[/b] Füge Rechnungs-Positionen hinzu.\n"
            "[b]Tipp:[/b] Halte eine hinzugefügte Position unten in der Liste [b]lange gedrückt[/b], um sie wieder zu entfernen!\n\n"
            "3. [b]PDF Erstellen:[/b] Generiert die finale Rechnung."
        )
        app.show_first_visit_info('rechnung', 'Info: Neue Rechnung erstellen', info_text)

    def on_pre_enter(self, *args):
        app = App.get_running_app()
        self.ids.rn_label.text = f"Rechnungsnummer: {app.data.get('naechste_nummer', 1)}"
        default_mwst = str(app.data.get("meine_daten", {}).get("steuersatz", "20"))
        self.ids.mwst_input.text = f"{default_mwst}%" if not default_mwst.endswith("%") else default_mwst
        self.filter_kunden("")
        self.filter_positionen("")
        self.ids.kunde_spinner.text = "Kunde wählen"
        self.ids.kunde_suche.text = ""
        self.temp_kunden_daten = {}
        self.aktuelle_positionen = []
        self.update_positions_liste()
        self.ids.pos_suche.text = ""
        self.ids.pos_spinner.text = "Position wählen"
        self.ids.menge_input.text = ""
        self.ids.preis_input.text = ""
        self.ids.einheit_input.text = "Stk"

    def filter_kunden(self, text):
        app = App.get_running_app()
        kunden = list(app.data.get("kunden_db", {}).keys())
        if text:
            kunden = [k for k in kunden if text.lower() in k.lower()]
        self.ids.kunde_spinner.values = kunden

    def filter_positionen(self, text):
        app = App.get_running_app()
        pos_db = app.data.get("positionen_db", {})
        pos_namen = list(pos_db.keys())
        if text:
            pos_namen = [p for p in pos_namen if text.lower() in p.lower()]
        self.ids.pos_spinner.values = pos_namen
        
    def fuelle_position(self, text):
        app = App.get_running_app()
        db = app.data.get("positionen_db", {})
        if text in db:
            alte_einheit = self.ids.einheit_input.text
            neue_einheit = db[text].get("einheit", "Stk")
            
            self.ids.einheit_input.text = neue_einheit
            self.ids.preis_input.text = str(db[text].get("preis", ""))
            
            if "mwst" in db[text]:
                self.ids.mwst_input.text = str(db[text]["mwst"])
                
            if alte_einheit == neue_einheit:
                self.check_einheit(neue_einheit)
            
    def check_einheit(self, text):
        if text in ["Pauschal Monat", "Jahr"]:
            popup = ZeitraumPopup()
            popup.mode = text
            popup.open()

    def set_einmaligen_kunden(self, name, daten):
        self.temp_kunden_daten = daten
        self.ids.kunde_spinner.values = [name]
        self.ids.kunde_spinner.text = name

    def position_hinzufuegen(self):
        app = App.get_running_app()
        beschr = self.ids.pos_suche.text.strip()
        if not beschr:
            beschr = self.ids.pos_spinner.text.strip()
        if not beschr or beschr == "Position wählen":
            app.show_info("Fehler", "Bitte eine Beschreibung eingeben oder wählen.")
            return
            
        try:
            menge = float(self.ids.menge_input.text.strip())
            ep = float(self.ids.preis_input.text.strip())
        except ValueError:
            app.show_info("Fehler", "Menge und Preis müssen gültige Zahlen sein!")
            return
            
        einh = self.ids.einheit_input.text.strip()
        mwst_str = self.ids.mwst_input.text.replace('%', '').strip()
        try: mwst = float(mwst_str)
        except ValueError: mwst = 20.0
        
        ges = menge * ep
        
        self.aktuelle_positionen.append({
            "beschr": beschr, "menge": menge, "einheit": einh, "ep": ep, "mwst": mwst
        })
        
        # Position in Datenbank merken
        # Wir schneiden das Datum beim Speichern in der DB ab, damit die Vorlage sauber bleibt
        db_beschr = re.sub(r'\s*(\d{2}/\d{2,4}|\d{4})$', '', beschr).strip()
        if not db_beschr: db_beschr = beschr  # Fallback, falls der Text nur aus dem Datum bestand
        
        if "positionen_db" not in app.data: app.data["positionen_db"] = {}
        app.data["positionen_db"][db_beschr] = {"einheit": einh, "preis": ep, "mwst": f"{mwst:g}%"}
        app.daten_speichern()
        
        self.update_positions_liste()
        self.ids.menge_input.text = ""
        self.ids.preis_input.text = ""
        self.ids.pos_suche.text = ""
        self.ids.pos_spinner.text = "Position wählen"
        self.ids.einheit_input.text = "Stk"
        self.filter_positionen("")

    def update_positions_liste(self):
        container = self.ids.positionen_liste
        container.clear_widgets()
        for idx, p in enumerate(self.aktuelle_positionen):
            item = PositionItem()
            item.index = idx
            item.beschr = p["beschr"]
            item.menge = f'{p["menge"]:g}'
            item.einh = "Pauschal" if p["einheit"] == "Pauschal Monat" else p["einheit"]
            item.mwst = f'{p.get("mwst", 20):g}%'
            item.ep = f'{p["ep"]:.2f} €'
            item.ges = f'{(p["menge"] * p["ep"]):.2f} €'
            container.add_widget(item)

    def zeige_loesch_popup(self, index):
        popup = PositionLoeschenPopup()
        popup.index = index
        popup.open()

    def pdf_erstellen(self):
        app = App.get_running_app()
        kunde_name = self.ids.kunde_spinner.text.strip()
        if not kunde_name or kunde_name == "Kunde wählen":
            return app.show_info("Fehler", "Bitte einen Kunden wählen.")
        if not self.aktuelle_positionen:
            return app.show_info("Fehler", "Die Rechnung hat keine Positionen.")
            
        db = app.data.get("kunden_db", {})
        if kunde_name in db:
            kunde_daten = db[kunde_name]
        else:
            kunde_daten = self.temp_kunden_daten
            
        rn = app.data.get("naechste_nummer", 1)
        
        pdf_daten = baue_pdf_im_ram(
            app.data.get("meine_daten", {}),
            kunde_name,
            kunde_daten,
            rn,
            self.aktuelle_positionen
        )
        
        if pdf_daten:
            if kunde_name in db:
                app.data["kunden_db"][kunde_name]["letzte_rechnung_datum"] = datetime.now().isoformat()
            app.data["naechste_nummer"] = rn + 1
            
            now = datetime.now()
            ordner_name = now.strftime("%Y_%m")
            
            sicherer_kunde = "".join(c for c in kunde_name if c.isalnum() or c in " _-")
            pdf_filename = f"{sicherer_kunde}_Rechnung_{rn}.pdf"
            
            speicher_ordner = app.data.get("meine_daten", {}).get("speicher_ordner")
            pdf_pfad = None
            if speicher_ordner and speicher_ordner != "STANDARD":
                pdf_pfad = write_to_custom_dir(pdf_daten, ordner_name, pdf_filename, app.target_os, speicher_ordner)
                
            if not pdf_pfad:
                rechnungen_dir = os.path.join(app.user_data_dir, "Rechnungen", ordner_name)
                os.makedirs(rechnungen_dir, exist_ok=True)
                pdf_pfad = os.path.join(rechnungen_dir, pdf_filename)
                try:
                    with open(pdf_pfad, "wb") as f:
                        f.write(pdf_daten)
                except Exception as e:
                Logger.error(f"Rechnung: Fehler beim Speichern im internen Rechnungsordner: {e}")

            if "rechnungen_db" not in app.data:
                app.data["rechnungen_db"] = {}
            app.data["rechnungen_db"][str(rn)] = {"datum": now.isoformat(), "kunde": kunde_name, "pfad": pdf_pfad}
            
            app.daten_speichern()
            self.ids.rn_label.text = f"Rechnungsnummer: {app.data['naechste_nummer']}"
            
            popup = PdfAktionPopup()
            popup.pdf_daten = pdf_daten
            popup.pdf_pfad = pdf_pfad
            popup.kunde_name = kunde_name
            popup.kunde_daten = kunde_daten
            popup.has_email = bool(kunde_daten.get("email", "").strip())
            popup.rechnungsnummer = rn
            popup.positionen = self.aktuelle_positionen.copy()
            popup.open()
            
            # Formular nach erfolgreicher Erstellung komplett zurücksetzen
            default_mwst = str(app.data.get("meine_daten", {}).get("steuersatz", "20"))
            self.ids.mwst_input.text = f"{default_mwst}%" if not default_mwst.endswith("%") else default_mwst
            self.ids.kunde_spinner.text = "Kunde wählen"
            self.ids.kunde_suche.text = ""
            self.temp_kunden_daten = {}
            self.aktuelle_positionen = []
            self.update_positions_liste()
            self.ids.pos_suche.text = ""
            self.ids.pos_spinner.text = "Position wählen"
            self.ids.menge_input.text = ""
            self.ids.preis_input.text = ""
            self.ids.einheit_input.text = "Stk"

    def gespeicherte_position_loeschen(self):
        app = App.get_running_app()
        pos_suche = self.ids.pos_suche.text.strip()
        pos_spinner = self.ids.pos_spinner.text.strip()
        
        db = app.data.get("positionen_db", {})
        pos_name = None
        
        if pos_suche in db:
            pos_name = pos_suche
        elif pos_spinner in db and pos_spinner != "Position wählen":
            pos_name = pos_spinner
            
        if pos_name:
            popup = GespeichertePositionLoeschenPopup()
            popup.position_name = pos_name
            popup.open()
        else:
            app.show_info("Info", "Bitte wähle zuerst eine gespeicherte Position aus, um sie zu löschen.")

class EPU_RechnungsgeneratorApp(App):
    data = DictProperty({})
    master_password = StringProperty("")
    target_os = StringProperty("windows")
    
    def build(self):
        self.title = "EPU_Rechnungsgenerator"
        self.icon = os.path.join(base_path, 'icon.png')
        
        if platform in ('win', 'linux', 'macosx'):
            Window.size = (1200, 800)
            Window.minimum_width, Window.minimum_height = (800, 600)
            
        self.data_path = os.path.join(self.user_data_dir, "rechnung_daten.enc")
        self.salt_path = os.path.join(self.user_data_dir, "rechnung_daten.salt")
        Window.bind(on_key_down=self.reset_timer)
        Window.bind(on_touch_down=self.reset_timer)
        Window.bind(on_request_close=self.on_request_close)
        self.last_activity = datetime.now()
        Clock.schedule_interval(self.check_lock, 1)
        
        Builder.load_file(os.path.join(base_path, 'layout.kv'))
        
        sm = ScreenManager()
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(MainScreen(name='main'))
        sm.add_widget(RechnungScreen(name='rechnung'))
        sm.add_widget(DatenbankScreen(name='datenbank'))
        sm.add_widget(EinstellungenScreen(name='einstellungen'))
        sm.add_widget(RechnungenVerwaltenScreen(name='rechnungen_verwalten'))
        return sm

    def on_pause(self):
        # Verhindert, dass die App geschlossen wird, wenn sie in den Hintergrund geht (z.B. PDF-Viewer offen)
        return True

    def on_request_close(self, *args, **kwargs):
        """
        Wird aufgerufen, wenn der Benutzer den Zurück-Button auf Android drückt.
        """
        # 1. Prüfen, ob ein Popup offen ist. Wenn ja, schließe es.
        # Popups werden dem Window als Child hinzugefügt. Das letzte ist an Index 0.
        if len(self.root_window.children) > 1:
            top_widget = self.root_window.children[0]
            if isinstance(top_widget, Popup):
                top_widget.dismiss()
                return True  # Ereignis behandelt, App nicht schließen

        # 2. Wenn kein Popup offen ist, navigiere zum Hauptmenü zurück
        current_screen = self.root.current
        if current_screen not in ['main', 'login']:
            self.root.current = 'main'
            return True  # Ereignis behandelt

        # 3. Wenn wir im Hauptmenü sind, frage nach, ob die App beendet werden soll
        if current_screen == 'main':
            self.show_exit_confirmation()
            return True  # Ereignis behandelt

        # 4. Wenn wir im Login-Screen sind, erlaube das Schließen der App
        return False

    def on_start(self):
        self.os_config_path = os.path.join(self.user_data_dir, "os_config.json")
        if os.path.exists(self.os_config_path):
            with open(self.os_config_path, "r") as f:
                self.target_os = json.load(f).get("os", "windows")
        else:
            # Automatisches Erkennen des Betriebssystems bei der Ersteinrichtung
            if platform in ('android', 'ios'):
                self.set_target_os('mobile')
            elif platform in ('linux', 'macosx'):
                self.set_target_os('unix')
            else:
                self.set_target_os('windows')
            
    def set_target_os(self, os_name):
        self.target_os = os_name
        with open(self.os_config_path, "w") as f: json.dump({"os": os_name}, f)

    def reset_timer(self, *args): self.last_activity = datetime.now()

    def check_lock(self, dt):
        if not self.data: return
        try:
            limit = int(self.data.get("meine_daten", {}).get("auto_lock_minuten", 5))
        except ValueError: limit = 0
            
        if self.root.current != 'login' and limit > 0 and hasattr(self, 'last_activity'):
            if (datetime.now() - self.last_activity).total_seconds() > (limit * 60):
                self.lock_app()

    def do_ersteinrichtung(self, pwd):
        self.data = {"naechste_nummer": 1, "kunden_db": {}, "positionen_db": {}, "meine_daten": {"auto_lock_minuten": "5"}}
        encrypt_data(self.data, pwd, self.data_path, self.salt_path)
        self.master_password = pwd
        self.root.current = 'main'

    def lock_app(self):
        self.data = {}
        if self.root.current == 'login':
            # Wechsle kurz den Screen, um ein vollständiges Neuzeichnen zu erzwingen
            self.root.current = 'main'
            Clock.schedule_once(lambda dt: setattr(self.root, 'current', 'login'), 0.05)
        else:
            self.root.current = 'login'
        
    def cleanup_database(self):
        if cleanup_database(self.data):
            self.daten_speichern()

    def daten_speichern(self):
        if self.data and self.master_password:
            encrypt_data(self.data, self.master_password, self.data_path, self.salt_path)

    def show_first_visit_info(self, screen_name, title, msg):
        if "visited_screens" not in self.data:
            self.data["visited_screens"] = []
        
        if screen_name not in self.data["visited_screens"]:
            popup = self.show_info(title, msg)
            self.data["visited_screens"].append(screen_name)
            self.daten_speichern()
            return popup
        return None

    def show_exit_confirmation(self):
        """Zeigt ein Bestätigungs-Popup zum Beenden der App."""
        ExitConfirmPopup().open()

    def show_info(self, title, msg):
        popup = InfoPopup(title=title, message=msg)
        popup.open()
        return popup
        
    def backup_einspielen_erststart(self):
        def on_dir_selected(path):
            self.temp_erststart_ordner = path if path else "STANDARD"
            self.backup_einspielen()

        box = BoxLayout(orientation='vertical', spacing='15dp', padding='10dp')
        lbl = Label(text="Bitte wähle zuerst den Ordner aus, in dem die Rechnungen aus dem Backup entpackt werden sollen (z.B. 'Dokumente' oder 'Downloads').", halign='center', valign='middle')
        lbl.bind(size=lbl.setter('text_size'))
        box.add_widget(lbl)
        
        btn_box = BoxLayout(size_hint_y=None, height='50dp', spacing='10dp')
        
        btn_skip = Button(text="Intern speichern")
        btn_choose = Button(text="Ordner wählen", background_color=(0.2, 0.7, 0.3, 1))
        
        btn_box.add_widget(btn_skip)
        btn_box.add_widget(btn_choose)
        box.add_widget(btn_box)
        
        popup = Popup(title="Speicherort für Rechnungen", size_hint=(0.9, 0.5), auto_dismiss=False, content=box)
        
        btn_skip.bind(on_release=lambda x: [popup.dismiss(), on_dir_selected("STANDARD")])
        btn_choose.bind(on_release=lambda x: [popup.dismiss(), choose_directory_native(on_dir_selected, self.target_os)])
        
        popup.open()

    def backup_erstellen(self):
        BackupPasswordPopup().open()

    def generiere_rechnung(self):
        self.root.current = 'rechnung'

    def oeffne_kunde_verwalten(self):
        KundeVerwaltenPopup().open()
        
    def oeffne_rechnungen_verwalten(self):
        self.root.current = 'rechnungen_verwalten'

    def backup_einspielen(self):
        def on_selection(selection):
            if selection and len(selection) > 0 and selection[0] is not None and str(selection[0]) != "None":
                Clock.schedule_once(lambda dt: self.open_restore_password(selection, None))
            else:
                if hasattr(self, 'temp_erststart_ordner'):
                    del self.temp_erststart_ordner
                
        res = choose_zip_native(on_selection, self.target_os)
        if res == "KIVY_FALLBACK":
            RestoreFileChooserPopup().open()

    def rechnungen_exportieren(self):
        db = self.data.get("rechnungen_db", {})
        if not db:
            self.show_info("Info", "Es gibt noch keine gespeicherten Rechnungen zum Exportieren.")
            return
            
        zip_buffer = io.BytesIO()
        try:
            import urllib.parse
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for rn, r_daten in db.items():
                    pfad = r_daten.get("pfad")
                    if pfad:
                        file_bytes = read_file_native(pfad, self.target_os)
                        if file_bytes:
                            datum = r_daten.get("datum", "")
                            try:
                                dt = datetime.fromisoformat(datum)
                                ordner = dt.strftime("%Y_%m")
                            except Exception:
                                ordner = "Unbekannt"
                                
                            filename = urllib.parse.unquote(str(pfad).replace('\\', '/').split('/')[-1])
                            if not filename.lower().endswith(".pdf"):
                                kunde = r_daten.get("kunde", "")
                                sicherer_kunde = "".join(c for c in kunde if c.isalnum() or c in " _-")
                                filename = f"{sicherer_kunde}_Rechnung_{rn}.pdf"
                                
                            arcname = f"Rechnungen/{ordner}/{filename}"
                            zf.writestr(arcname, file_bytes)
        except Exception as e:
            self.show_info("Fehler", f"Konnte ZIP nicht erstellen:\n{e}")
            return
            
        zip_daten = zip_buffer.getvalue()
        zip_buffer.close()
        
        custom_dir = self.data.get("meine_daten", {}).get("speicher_ordner")
        res = save_zip_native(zip_daten, "Rechnungen_Export.zip", self.target_os, custom_dir)
        if res != "KIVY_FALLBACK":
            if res:
                self.show_info("Erfolg", f"Rechnungen erfolgreich exportiert nach:\n{res}")
        else:
            popup = RechnungenExportPopup()
            popup.zip_daten = zip_daten
            popup.open()

    def process_rechnungen_export(self, target_path, filename, popup):
        if not filename.lower().endswith('.zip'): filename += '.zip'
        full_target_path = os.path.join(target_path, filename)
        try:
            with open(full_target_path, "wb") as f:
                f.write(popup.zip_daten)
            popup.dismiss()
            self.show_info("Erfolg", f"Rechnungen erfolgreich exportiert nach:\n{full_target_path}")
        except Exception as e:
            self.show_info("Fehler", f"Fehler beim Exportieren:\n{str(e)}")

    def open_backup_filechooser(self, zip_pwd, popup):
        if not zip_pwd:
            self.show_info("Fehler", "Passwort darf nicht leer sein!")
            return
        self.temp_zip_pwd = zip_pwd
        popup.dismiss()
        
        default_fn = self.get_default_backup_name()
        
        temp_path = os.path.join(self.user_data_dir, "temp_backup_gen.zip")
        try:
            logo_pfad = self.data.get("meine_daten", {}).get("logo_pfad")
            create_backup(self.data_path, self.salt_path, temp_path, self.temp_zip_pwd, self.user_data_dir, logo_pfad, app_data=self.data, target_os=self.target_os)
            with open(temp_path, "rb") as f:
                self.temp_backup_bytes = f.read()
            os.remove(temp_path)
        except Exception as e:
            self.show_info("Fehler", f"Backup-Erstellung fehlgeschlagen:\n{str(e)}")
            return
            
        custom_dir = self.data.get("meine_daten", {}).get("speicher_ordner")
        res = save_zip_native(self.temp_backup_bytes, default_fn, self.target_os, custom_dir)
        if res != "KIVY_FALLBACK":
            if res:
                self.show_info("Backup erfolgreich", f"Erweitertes verschlüsseltes ZIP erstellt:\n{res}")
        else:
            BackupFileChooserPopup().open()

    def get_default_backup_name(self):
        return f"Backup_RechnungsAPP_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"

    def open_restore_password(self, selection, popup):
        if not selection:
            return
        self.temp_restore_file = selection[0]
        if popup:
            popup.dismiss()
        RestorePasswordPopup().open()

    def process_restore(self, zip_pwd, popup):
        if not zip_pwd:
            self.show_info("Fehler", "Passwort darf nicht leer sein!")
            return
        popup.dismiss()
        loading_popup = InfoPopup(title="Backup wird eingespielt...", message="Bitte warten, dies kann einen Moment dauern...")
        loading_popup.auto_dismiss = False
        loading_popup.open()

        import threading

        def restore_thread():
            try:
                custom_dir = getattr(self, 'temp_erststart_ordner', None)
                restored_pdfs = restore_backup(self.temp_restore_file, zip_pwd, self.user_data_dir, custom_dir, self.target_os)
                
                @mainthread
                def on_success():
                    self.temp_restored_pdfs = restored_pdfs
                    loading_popup.dismiss()
                    self.show_info("Erfolg", "Backup erfolgreich eingespielt.\nAlle Rechnungen und dein Logo wurden wiederhergestellt.\nBitte mit dem Master-Passwort des Backups entsperren.")
                    self.lock_app()
                on_success()
            except Exception as e:
                @mainthread
                def on_error():
                    loading_popup.dismiss()
                    self.show_info("Fehler", f"Backup konnte nicht eingespielt werden (Falsches ZIP-Passwort?):\n{str(e)}")
                on_error()

        Clock.schedule_once(lambda dt: threading.Thread(target=restore_thread).start(), 0.2)

    def open_datenschutzerklaerung(self):
        DatenschutzerklaerungPopup().open()

    def open_about(self):
        AboutPopup().open()

    def process_backup(self, path, filename, popup):
        full_path = os.path.join(path, filename)
        if not full_path.endswith('.zip'): full_path += '.zip'
        try:
            if hasattr(self, 'temp_backup_bytes') and self.temp_backup_bytes:
                with open(full_path, "wb") as f:
                    f.write(self.temp_backup_bytes)
            else:
                logo_pfad = self.data.get("meine_daten", {}).get("logo_pfad")
                create_backup(self.data_path, self.salt_path, full_path, self.temp_zip_pwd, self.user_data_dir, logo_pfad, app_data=self.data, target_os=self.target_os)
            popup.dismiss()
            self.temp_zip_pwd = None
            self.temp_backup_bytes = None
            self.show_info("Backup erfolgreich", f"Erweitertes verschlüsseltes ZIP erstellt:\n{full_path}")
        except Exception as e:
            self.show_info("Fehler", f"ZIP-Backup fehlgeschlagen:\n{str(e)}")

    def export_kunden_dsgvo_pdf(self, name, daten):
        try:
            pdf_daten = export_kunden_dsgvo_pdf(name, daten)
            default_fn = f"DSGVO_Auskunft_{name.replace(' ', '_')}.pdf"
            custom_dir = self.data.get("meine_daten", {}).get("speicher_ordner")
            res = save_pdf_native(pdf_daten, default_fn, self.target_os, custom_dir)
            if res != "KIVY_FALLBACK":
                if res:
                    self.show_info("Erfolg", f"DSGVO-PDF gespeichert unter:\n{res}")
            else:
                popup = PdfSpeichernPopup()
                popup.default_filename = default_fn
                popup.pdf_daten = pdf_daten
                popup.open()
        except Exception as e:
            self.show_info("Fehler", f"Fehler bei der DSGVO-PDF-Erstellung:\n{str(e)}")
            
    def export_datenschutzerklaerung_pdf(self):
        text = self.data.get("meine_daten", {}).get("datenschutzerklaerung", "")
        if not text: return
        try:
            pdf_daten = export_datenschutzerklaerung_pdf(text)
            default_fn = "Datenschutzerklaerung.pdf"
            custom_dir = self.data.get("meine_daten", {}).get("speicher_ordner")
            res = save_pdf_native(pdf_daten, default_fn, self.target_os, custom_dir)
            if res != "KIVY_FALLBACK":
                if res:
                    self.show_info("Erfolg", f"Datenschutzerklärung gespeichert unter:\n{res}")
            else:
                popup = PdfSpeichernPopup()
                popup.default_filename = default_fn
                popup.pdf_daten = pdf_daten
                popup.open()
        except Exception as e:
            self.show_info("Fehler", f"Fehler bei der PDF-Erstellung:\n{str(e)}")

    def zeige_reset_popup(self):
        AppResetPopup().open()
        
    def reset_app_database(self):
        if os.path.exists(self.data_path):
            try: os.remove(self.data_path)
            except Exception: pass
        if os.path.exists(self.salt_path):
            try: os.remove(self.salt_path)
            except Exception: pass
            
        self.data = {}
        self.master_password = ""
        self.root.current = 'login'
        self.show_info("App zurückgesetzt", "Die Datenbank wurde erfolgreich gelöscht.\nDu kannst nun ein neues Master-Passwort vergeben.")

if __name__ == '__main__':
    EPU_RechnungsgeneratorApp().run()