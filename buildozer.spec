[app]

title = Sky Collector
package.name = skycollector
package.domain = org.skycollector
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt
version = 1.0.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.api = 31
android.minapi = 21
android.ndk = 23b
android.archs = arm64-v8a, armeabi-v7a
android.gradle_dependencies = 'androidx.core:core:1.6.+'
android.wakelock = False
android.allow_backup = True

# (optional) icon and splash:
# icon.filename = %(source.dir)s/icon.png
# presplash.filename = %(source.dir)s/splash.png
