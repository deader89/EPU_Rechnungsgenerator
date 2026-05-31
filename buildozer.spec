[app]
title = EPURechnungen
package.name = epurechnungen
package.domain = at.dave
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,enc,salt,ttf,txt,csv,xml,pkl
source.exclude_dirs = libs, bin, build
version = 0.1
requirements = python3,kivy==2.3.1,kivymd==1.2.0,pycryptodome,qrcode,pillow,pyjnius,requests,plyer
icon.filename = icon.png
orientation = all
android.permissions = WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a
android.allow_backup = True
android.copy_libs = 0
android.gradle_dependencies = androidx.documentfile:documentfile:1.0.1
[buildozer]
log_level = 2
p4a.branch = master
p4a.env_vars = FONTTOOLS_NO_CYTHON=1,PIP_NO_BINARY=fonttools
