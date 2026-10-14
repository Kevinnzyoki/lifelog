[app]
title = LifeLog
package.name = lifelog
package.domain = org.lifelog
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 0.1
requirements = python3==3.11.5,hostpython3==3.11.5,kivy==2.3.0,sqlite3,pyjnius,android
orientation = portrait
fullscreen = 0
android.permissions = ACTIVITY_RECOGNITION,PACKAGE_USAGE_STATS,INTERNET
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
p4a.branch = v2024.01.21

[buildozer]
log_level = 2
warn_on_root = 1
