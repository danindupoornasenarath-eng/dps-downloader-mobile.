import sys
import os
import json
import logging
import platform
import zipfile
import shutil
import subprocess
import re
from pathlib import Path
from datetime import datetime, timedelta
import threading

# Import Kivy elements
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.utils import platform as kivy_platform

# Import KivyMD elements
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivymd.uix.list import TwoLineListItem
from kivymd.uix.menu import MDDropdownMenu

import yt_dlp as youtube_dl
import requests

# Import plyer for Android native integrations
try:
    from plyer import clipboard, tts, vibrator
except ImportError:
    clipboard, tts, vibrator = None, None, None


class TikTokDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract_video_id(self, url):
        patterns = [
            r'https?://(?:www\.)?tiktok\.com/@[^/]+/video/(\d+)',
            r'https?://vm\.tiktok\.com/([^/]+)',
            r'https?://vt\.tiktok\.com/([^/]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def get_no_watermark_video(self, url):
        try:
            apis = [
                f"https://api.tiklydown.eu.org/api/download?url={url}",
                f"https://www.tikwm.com/api/?url={url}",
            ]
            for api_url in apis:
                try:
                    response = requests.get(api_url, timeout=30)
                    if response.status_code == 200:
                        data = response.json()
                        video_url = None
                        if api_url.startswith('https://api.tiklydown.eu.org') and data.get('success'):
                            video_url = data['data'].get('play')
                        elif api_url.startswith('https://www.tikwm.com') and data.get('code') == 0:
                            video_url = data['data'].get('play')
                        
                        if video_url:
                            if not video_url.startswith('http'):
                                video_url = 'https:' + video_url
                            return video_url, None
                except Exception:
                    continue
            return None, "Could not fetch TikTok video without watermark"
        except Exception as e:
            return None, f"Error: {str(e)}"


class FFmpegManager:
    FFMPEG_URLS = {
        'Windows': 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
        'Linux': 'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz',
        'Darwin': 'https://evermeet.cx/ffmpeg/ffmpeg-6.0.zip',
        'Android': 'https://github.com/hzw1199/Android-FFmpeg-Prebuilt/raw/main/ffmpeg-8.0.1/bin/ffmpeg'
    }
    
    def __init__(self, app_data_dir):
        self.app_data_dir = app_data_dir
        self.ffmpeg_dir = self.app_data_dir / "ffmpeg"
        self.ffmpeg_path = None
        if kivy_platform == 'android':
            self.platform = 'Android'
        else:
            self.platform = platform.system()
        
    def get_ffmpeg_path(self):
        if self.ffmpeg_path:
            return self.ffmpeg_path
            
        if self.platform == 'Windows':
            exe_name = 'ffmpeg.exe'
            possible_paths = [
                self.ffmpeg_dir / 'bin' / exe_name,
                self.ffmpeg_dir / exe_name,
            ]
            for item in self.ffmpeg_dir.glob('*'):
                if item.is_dir() and 'ffmpeg' in item.name.lower():
                    bin_path = item / 'bin' / exe_name
                    if bin_path.exists():
                        possible_paths.append(bin_path)
        elif self.platform == 'Android':
            exe_name = 'ffmpeg'
            possible_paths = [self.ffmpeg_dir / exe_name]
        else:
            exe_name = 'ffmpeg'
            possible_paths = [self.ffmpeg_dir / exe_name]
            
        for path in possible_paths:
            if path.exists():
                self.ffmpeg_path = str(path)
                return self.ffmpeg_path
                
        path = shutil.which('ffmpeg')
        if path:
            self.ffmpeg_path = path
            return self.ffmpeg_path
        return None
        
    def is_ffmpeg_working(self):
        ffmpeg = self.get_ffmpeg_path()
        if not ffmpeg:
            return False
        try:
            result = subprocess.run(
                [ffmpeg, '-version'],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if self.platform == 'Windows' else 0,
                timeout=10
            )
            return result.returncode == 0 and 'ffmpeg version' in result.stdout
        except Exception:
            return False
        
    def download_and_extract(self, status_callback=None):
        try:
            if self.ffmpeg_dir.exists():
                shutil.rmtree(self.ffmpeg_dir, ignore_errors=True)
            self.ffmpeg_dir.mkdir(exist_ok=True, parents=True)
            
            url = self.FFMPEG_URLS.get(self.platform)
            if not url: return False
                
            if status_callback:
                status_callback("Downloading FFmpeg...")
            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()
            
            temp_file = self.ffmpeg_dir / ("ffmpeg_temp" if self.platform != 'Android' else 'ffmpeg')
            with open(temp_file, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk: f.write(chunk)
            
            if self.platform == 'Windows':
                with zipfile.ZipFile(temp_file) as zip_ref:
                    zip_ref.extractall(self.ffmpeg_dir)
                    for member in zip_ref.namelist():
                        if member.endswith('ffmpeg.exe'):
                            root_parts = member.split('/')
                            if len(root_parts) > 1:
                                root_dir = root_parts[0]
                                root_path = self.ffmpeg_dir / root_dir
                                if root_path.exists():
                                    for item in root_path.iterdir():
                                        shutil.move(str(item), str(self.ffmpeg_dir))
                                    shutil.rmtree(root_path)
                                break
                temp_file.unlink()
            elif self.platform == 'Android':
                # Mark downloaded binary as executable
                os.chmod(str(temp_file), 0o755)
                self.ffmpeg_path = str(temp_file)
            
            is_working = bool(self.get_ffmpeg_path() and self.is_ffmpeg_working())
            if status_callback:
                status_callback("FFmpeg Ready" if is_working else "FFmpeg Failed")
            return is_working
        except Exception as e:
            logging.error(f"FFmpeg download error: {str(e)}")
            if status_callback:
                status_callback(f"FFmpeg error: {str(e)}")
            return False


KV = '''
MDScreen:
    MDBoxLayout:
        orientation: "vertical"
        md_bg_color: 0.1, 0.1, 0.1, 1

        # Title/Toolbar
        MDTopAppBar:
            title: "DPS Video Downloader v5.2"
            elevation: 4
            pos_hint: {"top": 1}
            md_bg_color: 0.15, 0.15, 0.15, 1
            right_action_items: [["information-outline", lambda x: app.show_about()]]

        ScrollView:
            do_scroll_x: False
            
            MDBoxLayout:
                orientation: "vertical"
                size_hint_y: None
                height: self.minimum_height
                padding: dp(15)
                spacing: dp(15)

                # Search & Paste Section
                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(15)
                    spacing: dp(10)
                    md_bg_color: 0.18, 0.18, 0.18, 1
                    radius: [dp(10)]

                    MDLabel:
                        text: "Search & Link"
                        font_style: "H6"
                        theme_text_color: "Custom"
                        text_color: 1, 1, 1, 1
                        size_hint_y: None
                        height: self.texture_size[1]

                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: dp(60)
                        spacing: dp(10)

                        MDTextField:
                            id: input_entry
                            hint_text: "Search keywords or paste link..."
                            helper_text: "Supports YouTube and TikTok"
                            helper_text_mode: "on_focus"
                            text_color_normal: 1, 1, 1, 1
                            text_color_focus: 1, 1, 1, 1
                            hint_text_color_normal: 0.6, 0.6, 0.6, 1
                            hint_text_color_focus: 0.05, 0.56, 1, 1
                            line_color_normal: 0.4, 0.4, 0.4, 1
                            line_color_focus: 0.05, 0.56, 1, 1
                            mode: "outlined"
                            size_hint_x: 0.8
                            on_text_validate: app.process_input_action()

                        MDIconButton:
                            icon: "content-paste"
                            theme_icon_color: "Custom"
                            icon_color: 0.05, 0.56, 1, 1
                            pos_hint: {"center_y": 0.5}
                            on_release: app.paste_url()

                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: dp(40)
                        spacing: dp(10)

                        MDRaisedButton:
                            text: "Search"
                            md_bg_color: 0.05, 0.56, 1, 1
                            size_hint_x: 0.5
                            on_release: app.search_youtube()

                        MDRaisedButton:
                            text: "Paste"
                            md_bg_color: 0.25, 0.25, 0.25, 1
                            size_hint_x: 0.5
                            on_release: app.paste_url()

                # Search Results Section
                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: dp(220)
                    padding: dp(10)
                    md_bg_color: 0.18, 0.18, 0.18, 1
                    radius: [dp(10)]

                    MDLabel:
                        text: "Results"
                        font_style: "Subtitle1"
                        theme_text_color: "Custom"
                        text_color: 1, 1, 1, 1
                        size_hint_y: None
                        height: self.texture_size[1]

                    ScrollView:
                        MDList:
                            id: results_list

                # Downloader Configuration Options
                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(15)
                    spacing: dp(12)
                    md_bg_color: 0.18, 0.18, 0.18, 1
                    radius: [dp(10)]

                    MDLabel:
                        text: "Download Settings"
                        font_style: "Subtitle1"
                        theme_text_color: "Custom"
                        text_color: 1, 1, 1, 1
                        size_hint_y: None
                        height: self.texture_size[1]

                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: dp(40)
                        spacing: dp(15)
                        
                        MDLabel:
                            text: "Type:"
                            theme_text_color: "Custom"
                            text_color: 1, 1, 1, 1
                            size_hint_x: None
                            width: dp(50)
                            pos_hint: {"center_y": 0.5}

                        MDBoxLayout:
                            orientation: "horizontal"
                            spacing: dp(5)
                            size_hint_x: None
                            width: dp(100)
                            
                            MDCheckbox:
                                id: video_radio
                                group: "dl_type"
                                active: True
                                size_hint: None, None
                                size: dp(36), dp(36)
                                selected_color: 0.05, 0.56, 1, 1
                                unselected_color: 0.6, 0.6, 0.6, 1
                                pos_hint: {"center_y": 0.5}
                                on_active: app.update_dynamic_options()
                            MDLabel:
                                text: "Video"
                                theme_text_color: "Custom"
                                text_color: 1, 1, 1, 1
                                pos_hint: {"center_y": 0.5}

                        MDBoxLayout:
                            orientation: "horizontal"
                            spacing: dp(5)
                            size_hint_x: None
                            width: dp(100)

                            MDCheckbox:
                                id: audio_radio
                                group: "dl_type"
                                size_hint: None, None
                                size: dp(36), dp(36)
                                selected_color: 0.05, 0.56, 1, 1
                                unselected_color: 0.6, 0.6, 0.6, 1
                                pos_hint: {"center_y": 0.5}
                                on_active: app.update_dynamic_options()
                            MDLabel:
                                text: "Audio"
                                theme_text_color: "Custom"
                                text_color: 1, 1, 1, 1
                                pos_hint: {"center_y": 0.5}

                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: dp(40)
                        spacing: dp(10)

                        MDLabel:
                            text: "Format:"
                            theme_text_color: "Custom"
                            text_color: 1, 1, 1, 1
                            pos_hint: {"center_y": 0.5}

                        MDRaisedButton:
                            id: format_dropdown
                            text: "mp4"
                            md_bg_color: 0.25, 0.25, 0.25, 1
                            text_color: 1, 1, 1, 1
                            on_release: app.open_format_menu()

                        MDLabel:
                            text: "Quality:"
                            theme_text_color: "Custom"
                            text_color: 1, 1, 1, 1
                            pos_hint: {"center_y": 0.5}

                        MDRaisedButton:
                            id: quality_dropdown
                            text: "Best"
                            md_bg_color: 0.25, 0.25, 0.25, 1
                            text_color: 1, 1, 1, 1
                            on_release: app.open_quality_menu()

                # Progress & Action Section
                MDCard:
                    orientation: "vertical"
                    size_hint_y: None
                    height: self.minimum_height
                    padding: dp(15)
                    spacing: dp(15)
                    md_bg_color: 0.18, 0.18, 0.18, 1
                    radius: [dp(10)]

                    MDProgressBar:
                        id: progress_bar
                        value: 0
                        max: 100
                        color: 0.05, 0.75, 0.45, 1

                    MDLabel:
                        id: status_label
                        text: "Ready"
                        font_style: "Body2"
                        theme_text_color: "Custom"
                        text_color: 0.8, 0.8, 0.8, 1
                        size_hint_y: None
                        height: self.texture_size[1]

                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: dp(45)
                        spacing: dp(10)

                        MDRaisedButton:
                            id: download_btn
                            text: "Download"
                            md_bg_color: 0.05, 0.75, 0.45, 1
                            size_hint_x: 0.6
                            on_release: app.start_download()

                        MDRaisedButton:
                            id: cancel_btn
                            text: "Cancel"
                            md_bg_color: 0.85, 0.2, 0.25, 1
                            disabled: True
                            size_hint_x: 0.4
                            on_release: app.cancel_download()
'''

class DPSVideoDownloaderApp(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setup_essentials()
        self.current_download_thread = None
        self.last_beep_percent = -1
        self.format_menu = None
        self.quality_menu = None
        self.quality_data = "best"  # Selected quality code

    def build(self):
        self.theme_cls.theme_style = "Dark"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.accent_palette = "Amber"
        
        # Load layout
        self.root = Builder.load_string(KV)
        return self.root

    def on_start(self):
        # Configure runtime directories and request permissions on Android
        self.request_android_permissions()
        
        # Check and initialize components
        self.update_dynamic_options()
        self.check_ffmpeg()
        self.play_startup_sound()
        self.speak("application_start")

    def setup_essentials(self):
        # Determine App storage paths
        if kivy_platform == 'android':
            # Safe internal storage path for downloads & settings
            self.app_data_dir = Path(self.user_data_dir)
            self.download_path = '/storage/emulated/0/Download'
            if not os.path.exists(self.download_path):
                self.download_path = '/sdcard/Download'
        else:
            self.app_data_dir = Path.home() / "DPS_Downloader"
            self.download_path = str(Path.home() / "Downloads")

        self.app_data_dir.mkdir(exist_ok=True, parents=True)
        self.settings_file = self.app_data_dir / "settings.json"
        
        self.ffmpeg_manager = FFmpegManager(self.app_data_dir)
        self.ffmpeg_path = None

        self.language_strings = {
            "english": {
                "title": "DPS Video Downloader v5.2",
                "status_ready": "Ready",
                "searching": "Searching...",
                "application_start": "Application ready",
                "error": "Error",
                "download_complete": "Download complete",
                "search_complete": "Found {count} results",
                "download_starting": "Starting download...",
                "download_canceling": "Canceling download...",
                "url_pasted": "URL pasted",
                "empty_search": "Please enter a search query or URL",
                "list_item_info": "{title} | Duration: {duration} | Channel: {channel}",
                "no_results": "No results found"
            }
        }

        self.settings = {
            "download_path": self.download_path,
            "language": "english",
            "screen_reader": True,
            "sound_feedback": True
        }
        self.load_settings()

    def request_android_permissions(self):
        if kivy_platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.WRITE_EXTERNAL_STORAGE,
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.INTERNET
                ])
            except Exception as e:
                logging.error(f"Permissions request failed: {e}")

    def check_ffmpeg(self):
        self.ffmpeg_path = self.ffmpeg_manager.get_ffmpeg_path()
        if not self.ffmpeg_manager.is_ffmpeg_working():
            self.ffmpeg_path = None
            # Trigger download thread for FFmpeg at startup if missing
            threading.Thread(target=self.ffmpeg_manager.download_and_extract, args=(self.update_status,)).start()

    def update_status(self, text):
        Clock.schedule_once(lambda dt: self._set_status_label(text))

    def _set_status_label(self, text):
        self.root.ids.status_label.text = text

    def update_dynamic_options(self):
        # Format list and quality list depend on whether video/audio button is selected
        if self.root.ids.video_radio.active:
            formats = ["mp4", "mkv"]
            qualities = [("Best", "best"), ("1080p", "1080p"), ("720p", "720p"), ("480p", "480p")]
        else:
            formats = ["mp3", "m4a", "wav"]
            qualities = [("Best Audio", "best"), ("High (320kbps)", "320"), ("Standard (192kbps)", "192"), ("Low (128kbps)", "128")]

        # Update button texts to reflect the default choices
        self.root.ids.format_dropdown.text = formats[0]
        self.root.ids.quality_dropdown.text = qualities[0][0]
        self.quality_data = qualities[0][1]

        # Recreate menus
        self.format_menu = MDDropdownMenu(
            caller=self.root.ids.format_dropdown,
            items=[{
                "text": fmt,
                "viewclass": "OneLineListItem",
                "on_release": lambda x=fmt: self.select_format(x),
            } for fmt in formats],
            width_mult=3,
        )

        self.quality_menu = MDDropdownMenu(
            caller=self.root.ids.quality_dropdown,
            items=[{
                "text": q[0],
                "viewclass": "OneLineListItem",
                "on_release": lambda x=q: self.select_quality(x),
            } for q in qualities],
            width_mult=4,
        )

    def open_format_menu(self):
        if self.format_menu:
            self.format_menu.open()

    def open_quality_menu(self):
        if self.quality_menu:
            self.quality_menu.open()

    def select_format(self, text):
        self.root.ids.format_dropdown.text = text
        self.format_menu.dismiss()

    def select_quality(self, data):
        self.root.ids.quality_dropdown.text = data[0]
        self.quality_data = data[1]
        self.quality_menu.dismiss()

    def process_input_action(self):
        text = self.root.ids.input_entry.text.strip()
        if text.startswith('http'):
            self.start_download()
        else:
            self.search_youtube()

    def play_sound(self, frequency=440, duration=100):
        if not self.settings.get("sound_feedback", True): return
        
        if kivy_platform == 'android':
            try:
                from jnius import autoclass
                ToneGenerator = autoclass('android.media.ToneGenerator')
                AudioManager = autoclass('android.media.AudioManager')
                # STREAM_MUSIC = 3, Volume = 100
                tone_generator = ToneGenerator(3, 100)
                # Play a standard short beep tone
                tone_generator.startTone(24, duration) # 24 is TONE_PROP_BEEP
            except Exception as e:
                print(f"Android sound error: {e}")
        elif platform.system() == 'Windows':
            try:
                import winsound
                winsound.Beep(frequency, duration)
            except: pass
        else:
            print('\a')

    def play_startup_sound(self):
        self.play_sound(440, 100)
        self.play_sound(523, 100)
        self.play_sound(659, 100)

    def speak(self, key, **kwargs):
        if self.settings.get("screen_reader", True):
            text = self.language_strings[self.settings["language"]].get(key, key).format(**kwargs)
            if tts:
                try:
                    tts.speak(text)
                except Exception as e:
                    print(f"Plyer TTS error: {e}")
            else:
                print(f"Speech fallback: {text}")

    def paste_url(self):
        if clipboard:
            try:
                content = clipboard.paste()
                if content:
                    self.root.ids.input_entry.text = content
                    self.speak("url_pasted")
                    if content.startswith('http'):
                        self.search_youtube()
            except Exception as e:
                print(f"Clipboard paste error: {e}")

    def search_youtube(self):
        query = self.root.ids.input_entry.text.strip()
        if not query:
            self.speak("empty_search")
            return

        if self.current_download_thread and self.current_download_thread.is_alive():
            self.speak("download_starting")
            return

        self.root.ids.results_list.clear_widgets()
        self.update_status("Searching...")
        self.speak("searching")

        # Start search thread
        t = threading.Thread(target=self.run_search, args=(query,))
        t.start()

    def run_search(self, query):
        try:
            results = []
            if query.startswith('http'):
                ydl_opts = {'quiet': True, 'no_warnings': True}
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(query, download=False)
                    results = [info]
            else:
                ydl_opts = {
                    'extract_flat': True,
                    'quiet': True,
                    'no_warnings': True,
                    'noplaylist': True
                }
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    result = ydl.extract_info(f"ytsearch15:{query}", download=False)
                    if 'entries' in result:
                        results = list(result['entries'])
            
            Clock.schedule_once(lambda dt: self.display_results(results))
        except Exception as e:
            self.update_status(f"Search failed: {e}")
            Clock.schedule_once(lambda dt: self.speak("error"))

    def display_results(self, results):
        self.root.ids.results_list.clear_widgets()
        if not results:
            self.update_status("No results found")
            self.speak("no_results")
            return

        for entry in results:
            if not entry: continue
            title = entry.get('title', 'Unknown Title')
            duration_sec = entry.get('duration')
            duration = str(timedelta(seconds=duration_sec)) if duration_sec else "N/A"
            channel = entry.get('uploader', entry.get('channel', 'Unknown Channel'))
            url = entry.get('webpage_url', entry.get('url', ''))
            
            if not url.startswith('http') and entry.get('id'):
                url = f"https://www.youtube.com/watch?v={entry.get('id')}"
            
            item = TwoLineListItem(
                text=title,
                secondary_text=f"{duration} | {channel}"
            )
            item.video_url = url
            item.full_text = self.language_strings[self.settings["language"]]["list_item_info"].format(
                title=title, duration=duration, channel=channel
            )
            item.bind(on_release=self.on_result_select)
            self.root.ids.results_list.add_widget(item)
            
        self.update_status(f"Found {len(results)} results")
        self.speak("search_complete", count=len(results))
        self.play_sound(523, 100)

    def on_result_select(self, item):
        self.root.ids.input_entry.text = item.video_url
        self.speak(item.full_text)

    def start_download(self):
        url = self.root.ids.input_entry.text.strip()
        if not url: return

        if not url.startswith('http'):
            self.search_youtube()
            return

        # Ensure FFmpeg is present if required
        dl_type = 'video' if self.root.ids.video_radio.active else 'audio'
        ext = self.root.ids.format_dropdown.text
        
        self.ffmpeg_path = self.ffmpeg_manager.get_ffmpeg_path()
        if not self.ffmpeg_path and (dl_type == 'audio' or ext != "mp4"):
            self.update_status("FFmpeg required! Downloading...")
            # We will start a download thread that triggers FFmpeg setup then starts the video download
            threading.Thread(target=self.setup_ffmpeg_then_download, args=(url, dl_type, ext)).start()
            return

        self.trigger_download(url, dl_type, ext)

    def setup_ffmpeg_then_download(self, url, dl_type, ext):
        success = self.ffmpeg_manager.download_and_extract(self.update_status)
        if success:
            self.ffmpeg_path = self.ffmpeg_manager.get_ffmpeg_path()
            self.trigger_download(url, dl_type, ext)
        else:
            self.update_status("Failed to acquire FFmpeg.")

    def trigger_download(self, url, dl_type, ext):
        self.root.ids.progress_bar.value = 0
        self.last_beep_percent = -1
        self.root.ids.download_btn.disabled = True
        self.root.ids.cancel_btn.disabled = False
        self.play_sound(784, 200)

        self.cancel_flag = False
        self.current_download_thread = threading.Thread(
            target=self.run_download, 
            args=(url, dl_type, ext, self.quality_data)
        )
        self.current_download_thread.start()

    def cancel_download(self):
        self.cancel_flag = True
        self.root.ids.cancel_btn.disabled = True
        self.update_status("Canceling...")

    def run_download(self, url, dl_type, ext, quality):
        try:
            self.update_status("Starting download...")
            if any(domain in url for domain in ['tiktok.com', 'vm.tiktok.com', 'vt.tiktok.com']):
                self.download_tiktok(url)
                return
                
            ydl_opts = self.get_ydl_options(dl_type, ext, quality)
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                
            if not self.cancel_flag:
                Clock.schedule_once(lambda dt: self.on_download_success())
        except Exception as e:
            if not self.cancel_flag:
                Clock.schedule_once(lambda dt: self.on_download_error(str(e)))

    def download_tiktok(self, url):
        try:
            self.update_status("Downloading TikTok...")
            downloader = TikTokDownloader()
            video_url, error = downloader.get_no_watermark_video(url)
            
            if error or not video_url:
                # Fallback to standard yt-dlp
                ydl_opts = self.get_ydl_options('video', 'mp4', 'best')
                with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            else:
                response = requests.get(video_url, stream=True, timeout=30)
                response.raise_for_status()
                
                filename = f"tiktok_video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
                try:
                    with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
                        info = ydl.extract_info(url, download=False)
                        if 'title' in info:
                            filename = re.sub(r'[^\w\-_\. ]', '_', info['title']) + ".mp4"
                except: pass

                filepath = Path(self.settings['download_path']) / filename
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self.cancel_flag:
                            if filepath.exists(): filepath.unlink()
                            return
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            if total_size > 0:
                                percent = int((downloaded_size / total_size) * 100)
                                Clock.schedule_once(lambda dt, p=percent: self.handle_progress(p))
                
                if not self.cancel_flag:
                    Clock.schedule_once(lambda dt: self.on_download_success())
        except Exception as e:
            if not self.cancel_flag:
                Clock.schedule_once(lambda dt: self.on_download_error(str(e)))

    def get_ydl_options(self, dl_type, ext, quality):
        try:
            Path(self.settings['download_path']).mkdir(exist_ok=True, parents=True)
        except PermissionError:
            raise Exception("Download folder permission denied")

        opts = {
            'outtmpl': os.path.join(self.settings['download_path'], '%(title)s.%(ext)s'),
            'progress_hooks': [self.progress_hook],
            'noplaylist': True,
            'verbose': False,
            'no_warnings': True,
        }

        if self.ffmpeg_path:
            opts['ffmpeg_location'] = self.ffmpeg_path

        if dl_type == 'audio':
            opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': ext,
                    'preferredquality': quality if quality != 'best' else '192',
                }],
                'extractaudio': True,
            })
        else:
            quality_str = f"bestvideo[ext={ext}]+bestaudio/best"
            if quality != "best":
                quality_str = f"bestvideo[height<={quality.replace('p','')}]['ext'={ext}]+bestaudio/best"
                
            opts.update({
                'format': quality_str,
                'merge_output_format': ext
            })
            
        return opts

    def progress_hook(self, data):
        if self.cancel_flag:
            raise Exception("Download cancelled by user")
            
        if data['status'] == 'downloading':
            try:
                percent = data.get('_percent_float', 0.0)
                Clock.schedule_once(lambda dt: self.handle_progress(int(percent)))
                speed = data.get('_speed_str', '')
                if speed:
                    self.update_status(f"Downloading: {int(percent)}% ({speed})")
                else:
                    self.update_status(f"Downloading: {int(percent)}%")
            except: pass

    def handle_progress(self, percent):
        self.root.ids.progress_bar.value = percent
        if self.settings.get("sound_feedback", True):
            if percent % 5 == 0 and percent != self.last_beep_percent:
                freq = int(400 + (percent * 10)) 
                self.play_sound(freq, 50)
                self.last_beep_percent = percent

    def on_download_success(self):
        self.root.ids.download_btn.disabled = False
        self.root.ids.cancel_btn.disabled = True
        self.root.ids.progress_bar.value = 100
        self.update_status("Download completed successfully")
        self.speak("download_complete")
        self.play_sound(880, 300)
        if vibrator:
            try: vibrator.vibrate(0.2)
            except: pass

    def on_download_error(self, err_msg):
        self.root.ids.download_btn.disabled = False
        self.root.ids.cancel_btn.disabled = True
        self.update_status(f"Error: {err_msg}")
        self.speak("error")
        self.play_sound(220, 500)
        if vibrator:
            try: vibrator.vibrate(0.5)
            except: pass

    def show_about(self):
        # We can speak or print it. For mobile we show a popup message / speak
        self.speak("DPS Video Downloader version 5 point 2. Copyright 2026 DPS Solutions.")

    def load_settings(self):
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    self.settings.update(json.load(f))
        except: pass

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f)
        except: pass

    def on_stop(self):
        self.save_settings()


if __name__ == "__main__":
    DPSVideoDownloaderApp().run()
