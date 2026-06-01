import os
import sys
import subprocess
from kivy.logger import Logger

def _get_shareable_uri(context, file_path, mime_type="application/pdf"):
    from jnius import autoclass
    import os, shutil
    VERSION = autoclass('android.os.Build$VERSION')
    Uri = autoclass('android.net.Uri')
    File = autoclass('java.io.File')
    
    if file_path.startswith("content://"):
        return Uri.parse(file_path)
        
    # Android 10+ (API 29+): Sicheres Teilen über MediaStore
    if VERSION.SDK_INT >= 29:
        try:
            ContentValues = autoclass('android.content.ContentValues')
            MediaStore_Downloads = autoclass('android.provider.MediaStore$Downloads')
            
            filename = os.path.basename(file_path)
            values = ContentValues()
            values.put("_display_name", filename)
            values.put("mime_type", mime_type)
            values.put("relative_path", "Download/AppRechnungen")
            
            resolver = context.getContentResolver()
            
            # Alte Einträge mit gleichem Namen löschen, um Dateimüll wie "Rechnung (1).pdf" zu verhindern
            try:
                selection = "_display_name = ?"
                StringArray = autoclass('[Ljava.lang.String;')
                sel_args = StringArray(1)
                sel_args[0] = filename
                resolver.delete(MediaStore_Downloads.EXTERNAL_CONTENT_URI, selection, sel_args)
            except Exception:
                pass
                
            uri = resolver.insert(MediaStore_Downloads.EXTERNAL_CONTENT_URI, values)
            
            if uri:
                pfd = resolver.openFileDescriptor(uri, "w")
                if pfd:
                    # Pure Python Schreibmethode (100% ausfallsicher)
                    fd = pfd.getFd()
                    fd_dup = os.dup(fd)
                    with open(file_path, 'rb') as in_f:
                        with os.fdopen(fd_dup, 'wb') as out_f:
                            shutil.copyfileobj(in_f, out_f)
                    try: pfd.close()
                    except: pass
                    return uri
        except Exception as e:
            Logger.error(f"PlatformIO: MediaStore URI Error: {e}")
            
    # Fallback für ältere Android-Versionen (< 10)
    Environment = autoclass('android.os.Environment')
    downloads_dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS).getAbsolutePath()
    public_path = os.path.join(downloads_dir, os.path.basename(file_path))
    
    if file_path != public_path:
        try: shutil.copy2(file_path, public_path)
        except Exception: pass
        
    return Uri.fromFile(File(public_path))

def open_pdf(path, target_os):
    if target_os == "windows":
        os.startfile(path)
    elif target_os == "unix":
        cmd = 'open' if sys.platform == 'darwin' else 'xdg-open'
        subprocess.run([cmd, path], check=True)
    elif target_os == "mobile":
        try:
            from jnius import autoclass
            
            StrictMode = autoclass('android.os.StrictMode')
            VmPolicyBuilder = autoclass('android.os.StrictMode$VmPolicy$Builder')
            StrictMode.setVmPolicy(VmPolicyBuilder().build())
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            
            context = PythonActivity.mActivity
            uri = _get_shareable_uri(context, path, "application/pdf")

            intent = Intent(Intent.ACTION_VIEW)
            intent.setDataAndType(uri, "application/pdf")
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            
            context.startActivity(intent)
        except Exception as e:
            raise Exception(f"PDF konnte nicht geöffnet werden (Fehlt ein PDF-Viewer?): {e}")

def print_pdf(path, target_os):
    if target_os == "windows":
        os.startfile(path, "print")
    elif target_os == "unix":
        subprocess.run(['lpr', path], check=True)
    elif target_os == "mobile":
        try:
            from jnius import autoclass, cast
            # StrictMode Hack erlaubt file:// URIs für Share-Intents ab Android 7+
            StrictMode = autoclass('android.os.StrictMode')
            VmPolicyBuilder = autoclass('android.os.StrictMode$VmPolicy$Builder')
            StrictMode.setVmPolicy(VmPolicyBuilder().build())
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            String = autoclass('java.lang.String')
            
            context = PythonActivity.mActivity
            uri = _get_shareable_uri(context, path, "application/pdf")
                
            intent = Intent(Intent.ACTION_SEND)
            intent.setType("application/pdf")
                    
            intent.putExtra(Intent.EXTRA_STREAM, cast('android.os.Parcelable', uri))
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION)
            
            chooser = Intent.createChooser(intent, cast('java.lang.CharSequence', String("Drucken / Teilen mit...")))
            chooser.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(chooser)
        except Exception as e:
            raise Exception(f"Drucken/Teilen nicht möglich: {e}")

def save_pdf_native(pdf_daten, default_filename, target_os, custom_dir=None):
    if custom_dir and custom_dir != "STANDARD":
        res = write_to_custom_dir(pdf_daten, "Manuelle_Exporte", default_filename, target_os, custom_dir)
        if res:
            return f"Ordner: Manuelle_Exporte/{default_filename}"
            
    if target_os == "windows":
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            filepath = filedialog.asksaveasfilename(
                defaultextension=".pdf",
                initialfile=default_filename,
                title="Rechnung speichern als...",
                filetypes=[("PDF Dokumente", "*.pdf")]
            )
            root.destroy()
            if filepath:
                with open(filepath, "wb") as f:
                    f.write(pdf_daten)
                return filepath
            return None
        except Exception:
            return "KIVY_FALLBACK"
            
    elif target_os == "mobile":
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            cache_dir = context.getCacheDir().getAbsolutePath()
            
            target_path = os.path.join(cache_dir, default_filename)
            base, ext = os.path.splitext(default_filename)
            counter = 1
            while os.path.exists(target_path):
                target_path = os.path.join(cache_dir, f"{base}_{counter}{ext}")
                counter += 1
                
            with open(target_path, "wb") as f:
                f.write(pdf_daten)
                
            uri = _get_shareable_uri(context, target_path, "application/pdf")
            try: os.remove(target_path)
            except Exception: pass
            if uri: return uri.toString()
            return "KIVY_FALLBACK"
        except Exception as e:
            Logger.error(f"PlatformIO: Android Speichern Fehler: {e}")
            return "KIVY_FALLBACK"
            
    return "KIVY_FALLBACK"

def send_email_native(email_addr, subject, body, attachment_path, target_os):
    if target_os == "mobile":
        try:
            from jnius import autoclass, cast
            
            StrictMode = autoclass('android.os.StrictMode')
            VmPolicyBuilder = autoclass('android.os.StrictMode$VmPolicy$Builder')
            StrictMode.setVmPolicy(VmPolicyBuilder().build())
            
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Intent = autoclass('android.content.Intent')
            String = autoclass('java.lang.String')
            
            context = PythonActivity.mActivity
            intent = Intent(Intent.ACTION_SEND)
            # Sicherer für Attachments als rfc822 (zwingt Apps den Anhang zu akzeptieren)
            intent.setType("application/pdf")
            
            # PyJnius Array-Fix
            try:
                intent.putExtra(Intent.EXTRA_EMAIL, [email_addr])
            except Exception:
                StringArray = autoclass('[Ljava.lang.String;')
                arr = StringArray(1)
                arr[0] = email_addr
                intent.putExtra(Intent.EXTRA_EMAIL, arr)
                
            intent.putExtra(Intent.EXTRA_SUBJECT, subject)
            intent.putExtra(Intent.EXTRA_TEXT, body)
            
            if attachment_path:
                uri = _get_shareable_uri(context, attachment_path, "application/pdf")
                        
                intent.putExtra(Intent.EXTRA_STREAM, cast('android.os.Parcelable', uri))
                
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_GRANT_READ_URI_PERMISSION)
            chooser = Intent.createChooser(intent, cast('java.lang.CharSequence', String("E-Mail senden mit...")))
            chooser.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            context.startActivity(chooser)
            return True
        except Exception as e:
            raise Exception(f"E-Mail-App konnte nicht gestartet werden: {e}")
    else:
        import urllib.parse
        import webbrowser
        url = f"mailto:{email_addr}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(body)}"
        webbrowser.open(url)
        
        try:
            # Zeigt die Datei markiert im Datei-Explorer (Windows/Mac) an für einfaches Drag & Drop
            if target_os == "windows":
                subprocess.run(['explorer', '/select,', os.path.normpath(attachment_path)])
            elif target_os == "unix":
                if sys.platform == 'darwin':
                    subprocess.run(['open', '-R', attachment_path])
                else:
                    subprocess.run(['xdg-open', os.path.dirname(attachment_path)])
        except Exception:
            pass
            
        return False

def save_zip_native(zip_daten, default_filename, target_os, custom_dir=None):
    if custom_dir and custom_dir != "STANDARD":
        res = write_to_custom_dir(zip_daten, "Backups", default_filename, target_os, custom_dir)
        if res:
            return f"Ordner: Backups/{default_filename}"
            
    if target_os == "windows":
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            filepath = filedialog.asksaveasfilename(
                defaultextension=".zip",
                initialfile=default_filename,
                title="ZIP speichern als...",
                filetypes=[("ZIP Archive", "*.zip")]
            )
            root.destroy()
            if filepath:
                with open(filepath, "wb") as f:
                    f.write(zip_daten)
                return filepath
            return None
        except Exception:
            return "KIVY_FALLBACK"
            
    elif target_os == "mobile":
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            cache_dir = context.getCacheDir().getAbsolutePath()
            
            target_path = os.path.join(cache_dir, default_filename)
            base, ext = os.path.splitext(default_filename)
            counter = 1
            while os.path.exists(target_path):
                target_path = os.path.join(cache_dir, f"{base}_{counter}{ext}")
                counter += 1
                
            with open(target_path, "wb") as f:
                f.write(zip_daten)
                
            uri = _get_shareable_uri(context, target_path, "application/zip")
            try: os.remove(target_path)
            except Exception: pass
            if uri: return uri.toString()
            return "KIVY_FALLBACK"
        except Exception as e:
            Logger.error(f"PlatformIO: Android Speichern Fehler: {e}")
            return "KIVY_FALLBACK"
            
    return "KIVY_FALLBACK"

def choose_directory_native(callback, target_os):
    if target_os in ("windows", "unix", "macosx"):
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folderpath = filedialog.askdirectory(title="Ordner für Autosave & Exporte wählen")
            root.destroy()
            if folderpath:
                callback(folderpath)
            else:
                callback(None)
        except Exception:
            callback(None)
    elif target_os == "mobile":
        try:
            from android import activity
            from jnius import autoclass
            from kivy.clock import mainthread
            Intent = autoclass('android.content.Intent')
            
            def on_activity_result(request_code, result_code, intent):
                if request_code != 1004:
                    return
                activity.unbind(on_activity_result=on_activity_result)

                @mainthread
                def run_callback(res_path):
                    callback(res_path)

                if result_code != -1 or not intent:
                    run_callback(None)
                    return
                    
                uri = intent.getData()
                if uri:
                    try:
                        context = autoclass('org.kivy.android.PythonActivity').mActivity
                        flags = intent.getFlags() & (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                        context.getContentResolver().takePersistableUriPermission(uri, flags)
                    except Exception: pass
                    run_callback(uri.toString())
                else:
                    run_callback(None)

            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
            activity.bind(on_activity_result=on_activity_result)
            PythonActivity.mActivity.startActivityForResult(intent, 1004)
        except Exception as e:
            Logger.error(f"PlatformIO: Directory Chooser Error: {e}")
            callback(None)

def write_to_custom_dir(data_bytes, relative_folder, filename, target_os, custom_dir):
    if not custom_dir or custom_dir == "STANDARD":
        return False
        
    # Verhindert doppelte Ordner (wie \2026_05\2026_05), falls der User beim Setup versehentlich den Monatsordner gewählt hat
    if relative_folder:
        import urllib.parse
        decoded_custom = urllib.parse.unquote(str(custom_dir)).replace('\\', '/').rstrip('/')
        rel_norm = str(relative_folder).replace('\\', '/').strip('/')
        
        if decoded_custom.endswith('/' + rel_norm) or decoded_custom == rel_norm:
            relative_folder = ""
            
    if target_os in ("windows", "unix", "macosx"):
        import os
        full_dir = os.path.join(custom_dir, relative_folder)
        os.makedirs(full_dir, exist_ok=True)
        full_path = os.path.join(full_dir, filename)
        with open(full_path, "wb") as f:
            f.write(data_bytes)
        return full_path
        
    elif target_os == "mobile":
        try:
            from jnius import autoclass
            Uri = autoclass('android.net.Uri')
            DocumentFile = autoclass('androidx.documentfile.provider.DocumentFile')
            context = autoclass('org.kivy.android.PythonActivity').mActivity
            
            tree_uri = Uri.parse(custom_dir)
            root_doc = DocumentFile.fromTreeUri(context, tree_uri)
            if not root_doc or not root_doc.canWrite():
                return False
                
            current_doc = root_doc
            if relative_folder:
                for part in relative_folder.replace('\\', '/').split('/'):
                    if not part: continue
                    next_doc = current_doc.findFile(part)
                    if not next_doc:
                        next_doc = current_doc.createDirectory(part)
                    if next_doc:
                        current_doc = next_doc
                        
            file_doc = current_doc.findFile(filename)
            if file_doc:
                file_doc.delete()
            
            mime = "application/zip" if filename.endswith(".zip") else "application/pdf"
            file_doc = current_doc.createFile(mime, filename)
            if not file_doc: return False
            
            import os
            import shutil
            cache_dir = context.getExternalCacheDir()
            if not cache_dir: cache_dir = context.getCacheDir()
            temp_path = os.path.join(cache_dir.getAbsolutePath(), "temp_write_saf")
            with open(temp_path, "wb") as f:
                f.write(data_bytes)
                
            try:
                pfd = context.getContentResolver().openFileDescriptor(file_doc.getUri(), "w")
                if pfd:
                    fd = pfd.getFd()
                    fd_dup = os.dup(fd)
                    with open(temp_path, 'rb') as in_f:
                        with os.fdopen(fd_dup, 'wb') as out_f:
                            shutil.copyfileobj(in_f, out_f)
                    try: pfd.close()
                    except: pass
            except Exception as e:
                Logger.error(f"PlatformIO: Fehler beim Kopieren in den SAF-Stream: {e}")
                
            os.remove(temp_path)
            return file_doc.getUri().toString()
        except Exception as e:
            Logger.error(f"PlatformIO: Write to SAF Error: {e}")
            return False
    return False

def choose_image_native(callback, target_os):
    if target_os == "windows":
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            filepath = filedialog.askopenfilename(
                title="Logo auswählen",
                filetypes=[("Bilder", "*.png;*.jpg;*.jpeg")]
            )
            root.destroy()
            if filepath:
                callback([filepath])
            else:
                callback([])
            return True
        except Exception:
            return "KIVY_FALLBACK"
    elif target_os == "mobile":
        try:
            from android import activity
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            
            def on_activity_result(request_code, result_code, intent):
                if request_code != 1001:
                    return
                activity.unbind(on_activity_result=on_activity_result)
                
                if result_code != -1 or not intent:
                    callback([])
                    return
                    
                uri = intent.getData()
                if not uri:
                    callback([])
                    return

                import threading
                from kivy.clock import mainthread

                def copy_file_thread(uri_to_copy):
                    try:
                        PythonActivity = autoclass('org.kivy.android.PythonActivity')
                        context = PythonActivity.mActivity
                        
                        import os
                        import shutil
                        files_dir = context.getFilesDir()
                        if not files_dir:
                            files_dir = context.getCacheDir()
                        temp_dir = files_dir.getAbsolutePath()
                        
                        content_resolver = context.getContentResolver()
                        mime_type = content_resolver.getType(uri_to_copy)
                        ext = ".png" if mime_type == "image/png" else ".jpg"
                        temp_file = os.path.join(temp_dir, f"app_logo{ext}")
                        
                        for old_ext in [".jpg", ".png", ".jpeg"]:
                            old_file = os.path.join(temp_dir, f"app_logo{old_ext}")
                            if os.path.exists(old_file):
                                try: os.remove(old_file)
                                except: pass
                            
                        try:
                            pfd = content_resolver.openFileDescriptor(uri_to_copy, "r")
                            if pfd:
                                fd = pfd.getFd()
                                fd_dup = os.dup(fd)
                                with os.fdopen(fd_dup, 'rb') as in_f:
                                    with open(temp_file, 'wb') as out_f:
                                        shutil.copyfileobj(in_f, out_f)
                                try: pfd.close()
                                except: pass
                        except Exception:
                            input_stream = content_resolver.openInputStream(uri_to_copy)
                            FileOutputStream = autoclass('java.io.FileOutputStream')
                            out_stream = FileOutputStream(temp_file)
                            try:
                                FileUtils = autoclass('android.os.FileUtils')
                                FileUtils.copy(input_stream, out_stream)
                            except Exception:
                                try:
                                    input_stream.transferTo(out_stream)
                                except Exception:
                                    pass
                            try: input_stream.close()
                            except: pass
                            try: out_stream.close()
                            except: pass
                        
                        @mainthread
                        def do_callback():
                            callback([temp_file])
                        do_callback()
                    except Exception as e:
                        Logger.error(f"PlatformIO: Android File Read Error: {e}")
                        @mainthread
                        def do_callback_error():
                            callback([])
                        do_callback_error()

                threading.Thread(target=copy_file_thread, args=(uri,)).start()

            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("image/*")
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            
            activity.bind(on_activity_result=on_activity_result)
            PythonActivity.mActivity.startActivityForResult(intent, 1001)
            return True
        except Exception as e:
            Logger.error(f"PlatformIO: Android ImageChooser Fehler: {e}")
            return "KIVY_FALLBACK"
            
    return "KIVY_FALLBACK"

def choose_zip_native(callback, target_os):
    if target_os == "windows":
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            filepath = filedialog.askopenfilename(
                title="Backup auswählen",
                filetypes=[("ZIP Archive", "*.zip")]
            )
            root.destroy()
            if filepath:
                callback([filepath])
            else:
                callback([])
            return True
        except Exception:
            return "KIVY_FALLBACK"
    elif target_os == "mobile":
        try:
            from android import activity
            from jnius import autoclass
            Intent = autoclass('android.content.Intent')
            
            def on_activity_result(request_code, result_code, intent):
                if request_code != 1002:
                    return
                activity.unbind(on_activity_result=on_activity_result)
                
                if result_code != -1 or not intent:
                    callback([])
                    return
                    
                uri = intent.getData()
                if not uri:
                    callback([])
                    return

                import threading
                from kivy.clock import mainthread

                def copy_file_thread(uri_to_copy):
                    try:
                        PythonActivity = autoclass('org.kivy.android.PythonActivity')
                        context = PythonActivity.mActivity
                        
                        import os
                        import shutil
                        cache_dir = context.getExternalCacheDir()
                        if not cache_dir:
                            cache_dir = context.getCacheDir()
                        temp_dir = cache_dir.getAbsolutePath()
                        temp_file = os.path.join(temp_dir, "temp_backup.zip")
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                            
                        content_resolver = context.getContentResolver()
                        
                        try:
                            pfd = content_resolver.openFileDescriptor(uri_to_copy, "r")
                            if pfd:
                                fd = pfd.getFd()
                                fd_dup = os.dup(fd)
                                with os.fdopen(fd_dup, 'rb') as in_f:
                                    with open(temp_file, 'wb') as out_f:
                                        shutil.copyfileobj(in_f, out_f)
                                try: pfd.close()
                                except: pass
                        except Exception:
                            input_stream = content_resolver.openInputStream(uri_to_copy)
                            FileOutputStream = autoclass('java.io.FileOutputStream')
                            out_stream = FileOutputStream(temp_file)
                            try:
                                FileUtils = autoclass('android.os.FileUtils')
                                FileUtils.copy(input_stream, out_stream)
                            except Exception:
                                try:
                                    input_stream.transferTo(out_stream)
                                except Exception:
                                    pass
                            try: input_stream.close()
                            except: pass
                            try: out_stream.close()
                            except: pass
                        
                        @mainthread
                        def do_callback():
                            callback([temp_file])
                        do_callback()
                    except Exception as e:
                        Logger.error(f"PlatformIO: Android File Read Error: {e}")
                        @mainthread
                        def do_callback_error():
                            callback([])
                        do_callback_error()

                threading.Thread(target=copy_file_thread, args=(uri,)).start()

            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_GET_CONTENT)
            intent.setType("application/zip")
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            
            activity.bind(on_activity_result=on_activity_result)
            PythonActivity.mActivity.startActivityForResult(intent, 1002)
            return True
        except Exception as e:
            Logger.error(f"PlatformIO: Android ZipChooser Fehler: {e}")
            return "KIVY_FALLBACK"
            
    return "KIVY_FALLBACK"

def read_file_native(file_path, target_os):
    import os
    if not file_path:
        return None
    if str(file_path).startswith("content://") and target_os == "mobile":
        try:
            from jnius import autoclass
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            context = PythonActivity.mActivity
            uri = Uri.parse(str(file_path))
            pfd = context.getContentResolver().openFileDescriptor(uri, "r")
            if pfd:
                fd = pfd.getFd()
                fd_dup = os.dup(fd)
                with os.fdopen(fd_dup, 'rb') as in_f:
                    data = in_f.read()
                try: pfd.close()
                except: pass
                return data
        except Exception as e:
            Logger.error(f"PlatformIO: Fehler beim Lesen von SAF: {e}")
            return None
    elif os.path.exists(file_path):
        with open(file_path, "rb") as f:
            return f.read()
    return None