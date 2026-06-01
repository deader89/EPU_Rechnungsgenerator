import os
import io
import sys
from datetime import datetime
import qrcode
from fpdf import FPDF
from kivy.logger import Logger
from decimal import Decimal

# Konvertierungsfaktor von alten Layout-Einheiten (Points) zu Millimeter
PT_TO_MM = 25.4 / 72.0

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(base_path, "Roboto-Regular.ttf")
FONT_BOLD_PATH = os.path.join(base_path, "Roboto-Black.ttf")

def generiere_banking_qr_objekt(betrag, rechnungs_nummer, meine_daten):
    iban = meine_daten.get("iban", "").replace(" ", "").upper()
    bic = meine_daten.get("bic", "").replace(" ", "").upper()
    firma = meine_daten.get("firma", "")
    qr_text = f"BCD\n002\n1\nSCT\n{bic}\n{firma}\n{iban}\nEUR{betrag:.2f}\n\n\nRechnung {rechnungs_nummer}\n\n"
    qr = qrcode.QRCode(version=1, box_size=10, border=1)
    qr.add_data(qr_text)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert('RGB')

def baue_pdf_im_ram(meine_daten, kunde_name, kunde_daten, rechnungsnummer, positionen, passwort=None):
    pdf = FPDF(unit="mm", format="A4")
    
    if passwort:
        try:
            # PyCryptodome wird von fpdf2 intern verwendet für diese Operation
            pdf.set_encryption(user_password=passwort, owner_password=passwort)
        except Exception as e:
            Logger.error(f"PDF-Generator: Fehler bei der PDF-Verschlüsselung: {e}")
            
    pdf.add_page()
    pdf.add_font("Roboto", "", FONT_PATH)
    try: pdf.add_font("Roboto", "B", FONT_BOLD_PATH)
    except Exception: pass
    
    pdf.set_font("Roboto", size=10)
    pdf.set_margins(15, 15, 15)
    
    firma = meine_daten.get('firma', '')
    strasse = meine_daten.get('strasse', '')
    plz_ort = meine_daten.get('plz_ort', '')
    
    header_lines = [firma, strasse, plz_ort]
    if meine_daten.get('email'): header_lines.append(meine_daten['email'])
    if seine_tel := meine_daten.get('tel'): header_lines.append(f"Tel: {seine_tel}")
    if meine_daten.get('uid'): header_lines.append(f"UID: {meine_daten['uid']}")
    
    logo_pfad = meine_daten.get("logo_pfad", "")
    try: logo_w = float(meine_daten.get("logo_width", 130)) * PT_TO_MM
    except ValueError: logo_w = 130.0 * PT_TO_MM
    try: logo_h = float(meine_daten.get("logo_height", 50)) * PT_TO_MM
    except ValueError: logo_h = 50.0 * PT_TO_MM
    try: logo_mt = float(meine_daten.get("logo_margin_top", 0)) * PT_TO_MM
    except ValueError: logo_mt = 0.0 * PT_TO_MM
    try: logo_mr = float(meine_daten.get("logo_margin_right", 0)) * PT_TO_MM
    except ValueError: logo_mr = 0.0 * PT_TO_MM

    if meine_daten.get("logo_aktiv", "Ja") == "Ja" and logo_pfad and os.path.exists(logo_pfad):
        # A4 Breite = 210mm
        x = 210 - 15 - logo_w - logo_mr
        y = 15 + logo_mt
        try:
            pdf.image(logo_pfad, x=x, y=y, w=logo_w, h=logo_h)
        except Exception:
            pass

    pdf.set_y(15)
    for i, line in enumerate(header_lines):
        pdf.set_font("Roboto", "B" if i == 0 or line.startswith("UID:") else "", 10)
        align = "L" if (meine_daten.get("logo_aktiv", "Ja") == "Ja" and logo_pfad and os.path.exists(logo_pfad)) else "R"
        pdf.cell(0, 5, line, align=align, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(15)
    pdf.set_font("Roboto", "B", 24)
    pdf.cell(0, 10, "RECHNUNG", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    formatiert_adresse = str(kunde_daten.get('adresse', '')).split('\n')
    empfaenger_lines = ["Empfänger:", str(kunde_name)]
    empfaenger_lines.extend(formatiert_adresse)
    if kunde_daten.get('uid'): 
        empfaenger_lines.append(f"UID: {kunde_daten['uid']}")
        
    meta_lines = [
        f"Rechnungs-Nr: {rechnungsnummer}",
        f"Datum: {datetime.now().strftime('%d.%m.%Y')}"
    ]
    
    y_before = pdf.get_y()
    pdf.set_font("Roboto", "", 10)
    for i, line in enumerate(empfaenger_lines):
        pdf.set_font("Roboto", "B" if i <= 1 else "", 10)
        pdf.cell(105, 5, line, new_x="LMARGIN", new_y="NEXT")
    
    y_after_empfaenger = pdf.get_y()
    
    pdf.set_y(y_before)
    for line in meta_lines:
        pdf.set_x(15 + 105)
        if ":" in line:
            k, v = line.split(":", 1)
            pdf.set_font("Roboto", "B", 10)
            pdf.cell(pdf.get_string_width(k + ": "), 5, k + ": ")
            pdf.set_font("Roboto", "", 10)
            pdf.cell(0, 5, v, align="R", new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Roboto", "", 10)
            pdf.cell(0, 5, line, align="R", new_x="LMARGIN", new_y="NEXT")
            
    pdf.set_y(max(y_after_empfaenger, pdf.get_y()) + 10)
    
    col_widths = (10.5, 63.5, 14, 17.6, 14, 28, 32.4)
    headers = ["Pos", "Beschreibung", "Menge", "Einh.", "MwSt", "Einzelpreis", "Gesamtpreis"]
    aligns = ["L", "L", "R", "C", "C", "L", "L"]
    
    pdf.set_font("Roboto", "B", 10)
    pdf.set_fill_color(128, 128, 128)
    pdf.set_text_color(255, 255, 255)
    
    for i, h in enumerate(headers):
        if i == len(headers) - 1:
            pdf.cell(col_widths[i], 8, h, border=1, fill=True, align=aligns[i], new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.cell(col_widths[i], 8, h, border=1, fill=True, align=aligns[i])
            
    pdf.set_text_color(0, 0, 0)
    pdf.set_fill_color(245, 245, 245)
    
    netto_gesamt = Decimal('0.0')
    brutto_gesamt = Decimal('0.0')
    mwst_dict = {}
    
    fill = True
    for idx, p in enumerate(positionen, 1):
        pdf.set_font("Roboto", "", 10)
        menge = Decimal(str(p['menge']))
        brutto_preis = Decimal(str(p['ep']))
        
        try: mwst_prozent_val = float(str(p.get("mwst", meine_daten.get("steuersatz", 20))).replace(',', '.'))
        except ValueError: mwst_prozent_val = 20.0
        mwst_prozent = Decimal(str(mwst_prozent_val))
        
        netto_preis = brutto_preis / (Decimal('1') + (mwst_prozent / Decimal('100')))
        netto_gesamt_pos = menge * netto_preis
        brutto_gesamt_pos = menge * brutto_preis
        mwst_betrag_pos = brutto_gesamt_pos - netto_gesamt_pos
        
        netto_gesamt += netto_gesamt_pos
        brutto_gesamt += brutto_gesamt_pos
        
        if mwst_prozent not in mwst_dict:
            mwst_dict[mwst_prozent] = Decimal('0.0')
        mwst_dict[mwst_prozent] += mwst_betrag_pos
        
        einheit_anzeige = "Pauschal" if p['einheit'] == "Pauschal Monat" else p['einheit']
        
        row_data = [
            str(idx),
            str(p['beschr']),
            f"{p['menge']:g}",
            str(einheit_anzeige),
            f"{mwst_prozent:g}%",
            f"{brutto_preis:g} EUR",
            f"{brutto_gesamt_pos:.2f} EUR"
        ]
        
        for i, d in enumerate(row_data):
            if i == len(row_data) - 1:
                pdf.cell(col_widths[i], 8, str(d), border=1, fill=fill, align=aligns[i], new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.cell(col_widths[i], 8, str(d), border=1, fill=fill, align=aligns[i])
        fill = not fill
        
    total_mwst = sum(mwst_dict.values(), Decimal('0'))
    pdf.ln(4)
    offset = sum(col_widths[:5])

    if total_mwst > Decimal('0'):
        # Regulärer Modus: Volle Aufschlüsselung, wenn Steuern anfallen
        pdf.set_font("Roboto", "", 10)
        pdf.set_x(15 + offset)
        pdf.cell(col_widths[5], 8, "Netto Gesamt:", border=0, align="R")
        pdf.cell(col_widths[6], 8, f"{netto_gesamt:.2f} EUR", border=0, align="R", new_x="LMARGIN", new_y="NEXT")
        
        for mwst_p, mwst_b in sorted(mwst_dict.items()):
            pdf.set_x(15 + offset)
            pdf.cell(col_widths[5], 8, f"Zzgl. {mwst_p:g}% MwSt:", border=0, align="R")
            pdf.cell(col_widths[6], 8, f"{mwst_b:.2f} EUR", border=0, align="R", new_x="LMARGIN", new_y="NEXT")
            
        pdf.set_x(15 + offset)
        pdf.set_font("Roboto", "B", 10)
        pdf.cell(col_widths[5], 8, "Brutto Gesamt:", border="T", align="R")
        pdf.cell(col_widths[6], 8, f"{brutto_gesamt:.2f} EUR", border="T", align="R", new_x="LMARGIN", new_y="NEXT")
    else:
        # Kleinunternehmer-Modus: Nur eine Zeile ohne Netto/Brutto-Bezeichnung
        pdf.set_x(15 + offset)
        pdf.set_font("Roboto", "B", 10)
        pdf.cell(col_widths[5], 8, "Rechnungsbetrag:", border="T", align="R")
        pdf.cell(col_widths[6], 8, f"{brutto_gesamt:.2f} EUR", border="T", align="R", new_x="LMARGIN", new_y="NEXT")
    
    pdf.ln(10)
    
    Zziel = kunde_daten.get('zahlungsziel', '').strip()
    if not Zziel: Zziel = meine_daten.get('zahlungsziel', '').strip()
    
    infotext_lines = []
    if Zziel:
        betrag_wort = "Bruttobetrag" if total_mwst > Decimal('0') else "Rechnungsbetrag"
        infotext_lines.append(f"Bitte überweisen Sie den {betrag_wort} innerhalb von {Zziel} Tagen auf das unten angegebene Bankkonto.")
    
    skonto_p_str = str(kunde_daten.get("skonto_prozent", "")).strip()
    skonto_t_str = str(kunde_daten.get("skonto_tage", "")).strip()
    if not skonto_p_str: skonto_p_str = str(meine_daten.get("skonto_prozent", "0"))
    if not skonto_t_str: skonto_t_str = str(meine_daten.get("skonto_tage", "5"))
    try:
        skonto_p = float(skonto_p_str.replace(',', '.'))
        skonto_t = int(skonto_t_str)
    except ValueError: skonto_p, skonto_t = 0.0, 0
    if skonto_p > 0:
        skonto_abzug = brutto_gesamt * (Decimal(str(skonto_p)) / Decimal('100'))
        infotext_lines.append(f"Skonto-Option: Bei Zahlung innerhalb von {skonto_t} Tagen gewähren wir {skonto_p:.0f}% Skonto.")
        infotext_lines.append(f"Sie überweisen in diesem Fall einen reduzierten Betrag von {brutto_gesamt - skonto_abzug:.2f} EUR.")
        
    if total_mwst == Decimal('0'):
        infotext_lines.append("Umsatzsteuerbefreit aufgrund der Kleinunternehmerregelung gemäß § 6 Abs. 1 Z 27 UStG.")

    pdf.set_font("Roboto", "B", 10)
    pdf.cell(0, 6, "Vielen Dank für Ihren Auftrag!", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Roboto", "", 10)
    for line in infotext_lines:
        pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)
    
    if meine_daten.get("qr_aktiv", "Ja") == "Ja" and meine_daten.get("iban") and meine_daten.get("bic"):
        try:
            qr_img = generiere_banking_qr_objekt(brutto_gesamt, rechnungsnummer, meine_daten)
            y_qr = pdf.get_y()
            
            if y_qr + 32 > 280:
                pdf.add_page()
                y_qr = pdf.get_y()
                
            pdf.image(qr_img, x=15, y=y_qr, w=25, h=25)
            
            pdf.set_font("Roboto", "B", 8)
            pdf.set_xy(15, y_qr + 25)
            pdf.cell(25, 5, "Scan 2 Pay", align="C")
            
            pdf.set_y(y_qr + 32)
        except Exception as e:
            Logger.error(f"PDF-Generator: QR-Code Generierung Fehler: {e}")
        
    # Footer
    pdf.set_y(-30)
    pdf.set_font("Roboto", "", 8)
    pdf.set_text_color(128, 128, 128)
    custom_footer = meine_daten.get("custom_footer", "").strip()
    if custom_footer:
        for line in custom_footer.split('\n'):
            pdf.cell(0, 4, line, align="C", new_x="LMARGIN", new_y="NEXT")
    else:
        pdf.cell(0, 4, "Hinweis: Ihre Daten werden zur Vertragserfüllung verarbeitet.", align="C", new_x="LMARGIN", new_y="NEXT")
        
    if meine_daten.get('iban', '').strip() or meine_daten.get('bic', '').strip():
        pdf.cell(0, 4, f"Bankverbindung: IBAN: {meine_daten.get('iban', '')} | BIC: {meine_daten.get('bic', '')}", align="C", new_x="LMARGIN", new_y="NEXT")
    
    return bytes(pdf.output())

def export_kunden_dsgvo_pdf(name, daten):
    pdf = FPDF(unit="mm", format="A4")
    pdf.add_page()
    pdf.add_font("Roboto", "", FONT_PATH)
    try: pdf.add_font("Roboto", "B", FONT_BOLD_PATH)
    except Exception: pass
    
    pdf.set_margins(15, 15, 15)
    
    pdf.set_font("Roboto", "B", 18)
    pdf.cell(0, 10, "DSGVO Datenauskunft", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    pdf.set_font("Roboto", "", 12)
    pdf.cell(0, 6, f"Auskunft über gespeicherte personenbezogene Daten für: {name}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.multi_cell(0, 6, "Gemäß Art. 15 DSGVO teilen wir Ihnen hiermit mit, welche Daten wir in unserer Datenbank über Sie gespeichert haben:", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    pdf.set_font("Roboto", "B", 14)
    pdf.cell(0, 8, "Stammdaten:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Roboto", "", 12)
    pdf.cell(0, 6, f"Name/Firma: {name}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Adresse: {daten.get('adresse', 'Nicht hinterlegt')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"UID-Nummer: {daten.get('uid', 'Nicht hinterlegt')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"E-Mail: {daten.get('email', 'Nicht hinterlegt')}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    pdf.set_font("Roboto", "B", 14)
    pdf.cell(0, 8, "Zahlungskonditionen:", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Roboto", "", 12)
    pdf.cell(0, 6, f"Individuelles Zahlungsziel: {daten.get('zahlungsziel', 'Standard')}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Skonto: {daten.get('skonto_prozent', 'Standard')}% innerhalb von {daten.get('skonto_tage', 'Standard')} Tagen", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)
    
    pdf.set_font("Roboto", "B", 14)
    pdf.cell(0, 8, "Verarbeitungshistorie (Systemdaten):", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Roboto", "", 12)
    
    erstellt = daten.get('erstellt_am', '')
    if erstellt:
        try: erstellt = datetime.fromisoformat(erstellt).strftime('%d.%m.%Y %H:%M')
        except Exception: pass
    pdf.cell(0, 6, f"Kunde im System angelegt am: {erstellt if erstellt else 'Unbekannt'}", new_x="LMARGIN", new_y="NEXT")
    
    letzte_rn = daten.get('letzte_rechnung_datum', '')
    if letzte_rn:
        try: letzte_rn = datetime.fromisoformat(letzte_rn).strftime('%d.%m.%Y')
        except Exception: pass
    pdf.cell(0, 6, f"Letzte Rechnungsstellung: {letzte_rn if letzte_rn else 'Keine'}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(15)
    pdf.cell(0, 6, f"Datum der Auskunftserstellung: {datetime.now().strftime('%d.%m.%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT")
    
    return bytes(pdf.output())

def export_datenschutzerklaerung_pdf(text):
    pdf = FPDF(unit="mm", format="A4")
    pdf.add_page()
    pdf.add_font("Roboto", "", FONT_PATH)
    try: pdf.add_font("Roboto", "B", FONT_BOLD_PATH)
    except Exception: pass
    pdf.set_margins(15, 15, 15)
    pdf.set_font("Roboto", "", 11)
    
    for paragraph in text.split('\n'):
        for emoji in ['📄', '🧠', '⚖️', '📊', '💾', '🗑️', '📤', '📧', '🔐', '👤', '📩', '️']:
            paragraph = paragraph.replace(emoji, '')
        paragraph = paragraph.strip()
        if paragraph:
            pdf.multi_cell(0, 5, paragraph, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

    return bytes(pdf.output())