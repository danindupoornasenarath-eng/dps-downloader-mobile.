[app]

# (str) Title of your application
title = DPS Downloader

# (str) Package name
package.name = dpsdownloader

# (str) Package domain (needed for android packaging)
package.domain = org.dpssolutions

# (str) Source code directory
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,json

# (str) Application version
version = 5.2

# (list) Application requirements
# comma separated e.g. requirements = sqlite3,kivy
requirements = python3, kivy==2.3.0, https://github.com/kivymd/KivyMD/archive/master.zip, requests, yt-dlp, plyer, urllib3, chardet, idna, certifi, jinja2, pyjnius

# (str) Supported orientations (one of landscape, sensorLandscape, portrait or all)
orientation = portrait

# (list) Permissions
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE

# (int) Target Android API, should be as high as possible.
android.api = 34

# (int) Minimum API your APK will support.
# Set to 28 because the precompiled Android FFmpeg binary is targeted for API 28+
android.minapi = 28

# (str) Android NDK directory (if empty, it will be automatically downloaded)
# android.ndk_path =

# (str) Android SDK directory (if empty, it will be automatically downloaded)
# android.sdk_path =

# (str) Android NDK version to use
android.ndk = 26b

# (bool) Use --private data directory (True) or public (False)
android.private_storage = True

# (list) Architecture to build for (e.g. arm64-v8a, armeabi-v7a)
# We only compile for arm64-v8a to support modern 64-bit devices and keep the package focused
android.archs = arm64-v8a

# (bool) Enable AndroidX support (required for modern KivyMD)
android.enable_androidx = True

# (str) Bootstrap to use for android (default is sdl2)
p4a.bootstrap = sdl2

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
