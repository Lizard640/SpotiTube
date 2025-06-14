

import os
import sys
import re
import time
import ssl
import threading
from queue import Queue
from tkinter import filedialog
import configparser
import traceback

# Tkinter and Style
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import tkinter.font as tkfont

# Spotify and YouTube Libraries
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
from youtube_search import YoutubeSearch

# Add lyrics support
import lyricsgenius

# --- NEW: Helper function to find FFMPEG (Cross-Platform) ---
def get_ffmpeg_path():
    """Gets the correct path to ffmpeg, whether running as a script or a bundled exe."""
    # Determine the executable filename based on the OS
    ffmpeg_filename = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    
    if getattr(sys, 'frozen', False):
        # We are running in a bundle (pyinstaller)
        # The ffmpeg folder is at the root of the bundle
        return os.path.join(sys._MEIPASS, 'ffmpeg', ffmpeg_filename)
    else:
        # We are running in a normal Python environment
        # This assumes 'ffmpeg' is in the system's PATH
        return "ffmpeg"

FFMPEG_EXE_PATH = get_ffmpeg_path()
# --- End of new code ---

# --- PERFORMANCE CONFIGURATION ---
NUM_WORKERS = 4
CONFIG_FILE = 'config.ini'

class DarkModeSpotifyDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Spotify to YouTube MP3 Converter")
        self.root.geometry("900x700")
        self.root.configure(bg='#1E1E1E')

        self.title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.label_font = tkfont.Font(family="Segoe UI", size=10)
        
        self.colors = {'background': '#1E1E1E', 'text': '#1DB954', 'accent': '#1DB954', 'input_bg': '#2C2C2C', 'button_bg': '#1DB954', 'button_fg': '#FFFFFF', 'progress_bg': '#3C3C3C'}

        self.sp = None
        self.genius = None
        self.spotify_client_id = None
        self.spotify_client_secret = None
        self.genius_api_token = None

        if not self.load_config():
            self.prompt_for_keys()

        self.initialize_apis()

        self.download_queue = Queue()
        self.is_downloading = False
        self.youtube_links = []
        self.downloaded_tracks = 0
        self.total_tracks = 0
        self.download_lock = threading.Lock()

        self.download_dir = os.path.abspath("downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        
        self.create_dark_gui()

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return False
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)
        try:
            self.spotify_client_id = config.get('API_KEYS', 'spotify_client_id')
            self.spotify_client_secret = config.get('API_KEYS', 'spotify_client_secret')
            self.genius_api_token = config.get('API_KEYS', 'genius_api_token', fallback=None)
            if not self.spotify_client_id or not self.spotify_client_secret:
                return False
            return True
        except (configparser.NoSectionError, configparser.NoOptionError):
            return False

    def save_config(self):
        config = configparser.ConfigParser()
        config['API_KEYS'] = {
            'spotify_client_id': self.spotify_client_id,
            'spotify_client_secret': self.spotify_client_secret,
            'genius_api_token': self.genius_api_token or ''
        }
        with open(CONFIG_FILE, 'w') as configfile:
            config.write(configfile)

    def prompt_for_keys(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("API Key Configuration")
        dialog.geometry("400x200")
        dialog.configure(bg=self.colors['background'])
        dialog.transient(self.root)
        dialog.grab_set()

        frame = tk.Frame(dialog, bg=self.colors['background'], padx=15, pady=15)
        frame.pack(expand=True, fill=tk.BOTH)

        tk.Label(frame, text="Spotify Client ID:", bg=self.colors['background'], fg=self.colors['text']).grid(row=0, column=0, sticky='w', pady=5)
        id_entry = tk.Entry(frame, width=40, bg=self.colors['input_bg'], fg=self.colors['text'])
        id_entry.grid(row=0, column=1, pady=5)
        if self.spotify_client_id: id_entry.insert(0, self.spotify_client_id)

        tk.Label(frame, text="Spotify Client Secret:", bg=self.colors['background'], fg=self.colors['text']).grid(row=1, column=0, sticky='w', pady=5)
        secret_entry = tk.Entry(frame, width=40, bg=self.colors['input_bg'], fg=self.colors['text'])
        secret_entry.grid(row=1, column=1, pady=5)
        if self.spotify_client_secret: secret_entry.insert(0, self.spotify_client_secret)

        tk.Label(frame, text="Genius Token (Optional):", bg=self.colors['background'], fg=self.colors['text']).grid(row=2, column=0, sticky='w', pady=5)
        genius_entry = tk.Entry(frame, width=40, bg=self.colors['input_bg'], fg=self.colors['text'])
        genius_entry.grid(row=2, column=1, pady=5)
        if self.genius_api_token: genius_entry.insert(0, self.genius_api_token)

        def on_save():
            spotify_id = id_entry.get().strip()
            spotify_secret = secret_entry.get().strip()
            if not spotify_id or not spotify_secret:
                messagebox.showerror("Error", "Spotify Client ID and Secret are required.", parent=dialog)
                return
            self.spotify_client_id = spotify_id
            self.spotify_client_secret = spotify_secret
            self.genius_api_token = genius_entry.get().strip()
            self.save_config()
            self.initialize_apis()
            dialog.destroy()

        save_button = tk.Button(frame, text="Save and Continue", command=on_save, bg=self.colors['button_bg'], fg=self.colors['button_fg'])
        save_button.grid(row=3, column=0, columnspan=2, pady=20)
        self.root.wait_window(dialog)

    def initialize_apis(self):
        if not self.spotify_client_id or not self.spotify_client_secret:
            messagebox.showerror("API Error", "Spotify API keys are not configured. The application will now exit.")
            sys.exit(1)
        try:
            self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=self.spotify_client_id, client_secret=self.spotify_client_secret))
            self.sp.search('test', limit=1)
        except Exception as e:
            messagebox.showerror("Spotify API Error", f"Failed to initialize Spotify client. Please check your keys in Settings.\n\nError: {e}")
            self.sp = None
        if self.genius_api_token:
            try:
                self.genius = lyricsgenius.Genius(self.genius_api_token, verbose=False, remove_section_headers=True)
            except Exception as e:
                messagebox.showwarning("Genius API Error", f"Failed to initialize Genius client. Lyrics will be unavailable.\n\nError: {e}")
                self.genius = None
        else:
            self.genius = None
    
    def create_dark_gui(self):
        main_frame = tk.Frame(self.root, bg=self.colors['background'])
        main_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)
        top_frame = tk.Frame(main_frame, bg=self.colors['background'])
        top_frame.pack(fill=tk.X, pady=(0, 20))
        title_label = tk.Label(top_frame, text="Spotify Playlist Downloader", font=self.title_font, fg=self.colors['text'], bg=self.colors['background'])
        title_label.pack(side=tk.LEFT, expand=True)
        settings_button = tk.Button(top_frame, text="Settings", command=self.prompt_for_keys, font=self.label_font, bg='#4F4F4F', fg='#FFFFFF')
        settings_button.pack(side=tk.RIGHT)
        url_frame = tk.Frame(main_frame, bg=self.colors['background'])
        url_frame.pack(fill=tk.X, pady=10)
        url_label = tk.Label(url_frame, text="Spotify Playlist URL:", font=self.label_font, fg=self.colors['text'], bg=self.colors['background'])
        url_label.pack(side=tk.LEFT, padx=(0, 10))
        self.url_entry = tk.Entry(url_frame, width=70, font=self.label_font, bg=self.colors['input_bg'], fg=self.colors['text'], insertbackground=self.colors['text'])
        self.url_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 10))
        self.fetch_button = tk.Button(url_frame, text="Fetch Tracks", command=self.fetch_tracks_async, font=self.label_font, bg=self.colors['button_bg'], fg=self.colors['button_fg'], activebackground=self.colors['accent'])
        self.fetch_button.pack(side=tk.RIGHT)
        dir_frame = tk.Frame(main_frame, bg=self.colors['background'])
        dir_frame.pack(fill=tk.X, pady=10)
        dir_label = tk.Label(dir_frame, text="Save to:", font=self.label_font, fg=self.colors['text'], bg=self.colors['background'])
        dir_label.pack(side=tk.LEFT, padx=(0, 10))
        self.dir_var = tk.StringVar()
        self.dir_entry = tk.Entry(dir_frame, textvariable=self.dir_var, width=70, font=self.label_font, bg=self.colors['input_bg'], fg=self.colors['text'], insertbackground=self.colors['text'], state='readonly')
        self.dir_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 10))
        self.browse_button = tk.Button(dir_frame, text="Browse", command=self.select_directory, font=self.label_font, bg=self.colors['button_bg'], fg=self.colors['button_fg'], activebackground=self.colors['accent'])
        self.browse_button.pack(side=tk.RIGHT)
        lyrics_frame = tk.Frame(main_frame, bg=self.colors['background'])
        lyrics_frame.pack(fill=tk.X, pady=10)
        self.lyrics_var = tk.BooleanVar(value=True)
        lyrics_check = tk.Checkbutton(lyrics_frame, text="Download and embed lyrics", variable=self.lyrics_var, font=self.label_font, fg=self.colors['text'], bg=self.colors['background'], selectcolor=self.colors['input_bg'], activebackground=self.colors['background'], activeforeground=self.colors['text'])
        lyrics_check.pack(side=tk.LEFT)
        self.lrc_var = tk.BooleanVar(value=True)
        lrc_check = tk.Checkbutton(lyrics_frame, text="Create .lrc files", variable=self.lrc_var, font=self.label_font, fg=self.colors['text'], bg=self.colors['background'], selectcolor=self.colors['input_bg'], activebackground=self.colors['background'], activeforeground=self.colors['text'])
        lrc_check.pack(side=tk.LEFT, padx=(20, 0))
        self.dir_var.set(self.download_dir)
        progress_container = tk.Frame(main_frame, bg=self.colors['background'])
        progress_container.pack(fill=tk.X, pady=10)
        overall_progress_frame = tk.Frame(progress_container, bg=self.colors['background'])
        overall_progress_frame.pack(fill=tk.X, pady=5)
        self.overall_percentage_label = tk.Label(overall_progress_frame, text="0%", font=self.label_font, fg=self.colors['text'], bg=self.colors['background'])
        self.overall_percentage_label.pack(side=tk.LEFT)
        self.overall_progress_bar = ttk.Progressbar(overall_progress_frame, orient=tk.HORIZONTAL, length=600, mode="determinate", style="Custom.Horizontal.TProgressbar")
        self.overall_progress_bar.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)
        current_track_frame = tk.Frame(progress_container, bg=self.colors['background'])
        current_track_frame.pack(fill=tk.X, pady=5)
        self.current_track_label = tk.Label(current_track_frame, text="", font=self.label_font, fg=self.colors['text'], bg=self.colors['background'])
        self.current_track_label.pack()
        self.result_area = scrolledtext.ScrolledText(main_frame, width=90, height=10, wrap=tk.WORD, font=self.label_font, bg=self.colors['input_bg'], fg=self.colors['text'], insertbackground=self.colors['text'])
        self.result_area.pack(pady=10, fill=tk.BOTH, expand=True)
        self.download_button = tk.Button(main_frame, text="Download All as MP3", command=self.download_all_tracks, font=self.label_font, bg=self.colors['button_bg'], fg=self.colors['button_fg'], activebackground=self.colors['accent'])
        self.download_button.pack(pady=10)
        style = ttk.Style()
        style.theme_use('default')
        style.configure("Custom.Horizontal.TProgressbar", background=self.colors['accent'], troughcolor=self.colors['progress_bg'])

    def embed_lyrics_in_mp3(self, mp3_file, lyrics):
        if not lyrics: return
        try:
            temp_lyrics_file = f"{mp3_file}.lyrics.txt"
            with open(temp_lyrics_file, 'w', encoding='utf-8') as f: f.write(lyrics)
            temp_output_file = f"{mp3_file}.temp.mp3"
            
            # --- MODIFIED: Use the FFMPEG_EXE_PATH variable ---
            cmd = [FFMPEG_EXE_PATH, '-y', '-i', mp3_file, '-i', temp_lyrics_file, '-map', '0', '-map', '1', '-c', 'copy', '-id3v2_version', '3', '-metadata:s:t', 'mimetype=text/plain', temp_output_file]
            
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            import subprocess
            subprocess.run(cmd, check=True, capture_output=True, startupinfo=startupinfo)
            os.replace(temp_output_file, mp3_file)
            os.remove(temp_lyrics_file)
        except Exception as e: self.root.after(0, self.result_area.insert, tk.END, f"Error embedding lyrics: {e}\n")

    # (All other functions remain the same)
    def select_directory(self):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            self.download_dir = selected_dir
            self.dir_var.set(selected_dir)
            os.makedirs(self.download_dir, exist_ok=True)
    def sanitize_filename(self, name):
        sanitized = re.sub(r'[\\/*?:"<>|]', '_', name)
        return sanitized.strip()
    def fetch_tracks_async(self):
        if not self.sp:
            messagebox.showerror("API Error", "Spotify client not initialized. Please configure your API keys in Settings.")
            return
        playlist_link = self.url_entry.get()
        if not playlist_link:
            messagebox.showerror("Error", "Please enter a Spotify playlist URL.")
            return
        self.fetch_button.config(state=tk.DISABLED)
        self.download_button.config(state=tk.DISABLED)
        self.result_area.delete(1.0, tk.END)
        self.result_area.insert(tk.END, "Fetching track list from Spotify...\n")
        threading.Thread(target=self.fetch_tracks_worker, args=(playlist_link,), daemon=True).start()
    def fetch_tracks_worker(self, playlist_link):
        try:
            tracks = self.get_spotify_playlist_tracks(playlist_link)
            self.total_tracks = len(tracks)
            self.youtube_links = []
            self.root.after(0, self.result_area.insert, tk.END, f"Found {self.total_tracks} tracks. Searching YouTube (this may take a moment)...\n")
            self.root.after(0, self.overall_progress_bar.config, {"maximum": self.total_tracks, "value": 0})
            for i, track in enumerate(tracks):
                youtube_link = self.find_youtube_link(track)
                if youtube_link:
                    self.youtube_links.append(youtube_link)
                def update_fetch_progress(index):
                    self.overall_progress_bar["value"] = index + 1
                    percentage = ((index + 1) / self.total_tracks) * 100
                    self.overall_percentage_label.config(text=f"{int(percentage)}%")
                self.root.after(0, update_fetch_progress, i)
            def on_fetch_complete():
                self.result_area.insert(tk.END, "\n--- Found YouTube Links ---\n")
                for idx, link in enumerate(self.youtube_links, 1):
                    self.result_area.insert(tk.END, f"{idx}. {link['title']} by {link['artist']}\n")
                messagebox.showinfo("Success", f"Ready to download {len(self.youtube_links)} tracks!")
                self.fetch_button.config(state=tk.NORMAL)
                self.download_button.config(state=tk.NORMAL)
            self.root.after(0, on_fetch_complete)
        except Exception as e:
            def on_fetch_error():
                messagebox.showerror("Error", str(e))
                self.fetch_button.config(state=tk.NORMAL)
            self.root.after(0, on_fetch_error)
    def get_spotify_playlist_tracks(self, playlist_link):
        playlist_id_match = re.search(r'playlist/([a-zA-Z0-9]+)', playlist_link)
        if not playlist_id_match:
            raise ValueError("Invalid Spotify Playlist URL")
        playlist_id = playlist_id_match.group(1)
        results = self.sp.playlist_tracks(playlist_id)
        tracks = []
        while results:
            tracks.extend([{'name': item['track']['name'], 'artist': item['track']['artists'][0]['name'], 'album': item['track']['album']['name']} for item in results['items'] if item['track']])
            results = self.sp.next(results) if results['next'] else None
        return tracks
    def find_youtube_link(self, track):
        search_query = f"{track['name']} {track['artist']} audio"
        try:
            results = YoutubeSearch(search_query, max_results=1).to_dict()
            if results:
                return {'title': track['name'], 'artist': track['artist'], 'album': track.get('album', ''), 'youtube_url': f"https://youtube.com{results[0]['url_suffix']}"}
            return None
        except Exception as e:
            self.root.after(0, self.result_area.insert, tk.END, f"Search error for '{search_query}': {str(e)}\n")
            return None
    def download_all_tracks(self):
        if not self.youtube_links:
            messagebox.showerror("Error", "Fetch tracks first!")
            return
        os.makedirs(self.download_dir, exist_ok=True)
        while not self.download_queue.empty():
            self.download_queue.get()
        for link in self.youtube_links:
            self.download_queue.put(link)
        self.downloaded_tracks = 0
        self.total_tracks = len(self.youtube_links)
        self.overall_progress_bar.config(maximum=self.total_tracks, value=0)
        self.overall_percentage_label.config(text="0%")
        self.current_track_label.config(text=f"Starting {NUM_WORKERS} download workers...")
        self.is_downloading = True
        self.fetch_button.config(state=tk.DISABLED)
        self.download_button.config(state=tk.DISABLED)
        self.result_area.delete(1.0, tk.END)
        self.threads = []
        for i in range(NUM_WORKERS):
            thread = threading.Thread(target=self.download_worker, args=(i,), daemon=True)
            thread.start()
            self.threads.append(thread)
        self.monitor_download()
    def download_worker(self, worker_id):
        while not self.download_queue.empty():
            try:
                link = self.download_queue.get_nowait()
            except Queue.Empty:
                break
            try:
                self.root.after(0, self.result_area.insert, tk.END, f"[Worker {worker_id}] Starting: {link['title']}\n")
                output_filename = os.path.join(self.download_dir, f"{self.sanitize_filename(link['artist'])} - {self.sanitize_filename(link['title'])}")
                mp3_filename = f"{output_filename}.mp3"
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'noplaylist': True,
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
                    'outtmpl': output_filename + '.%(ext)s',
                    'quiet': True,
                    'no_warnings': True,
                    'ignoreerrors': False,
                    'overwrites': False,
                    'concurrent_fragment_downloads': NUM_WORKERS,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link['youtube_url']])
                self.root.after(0, self.result_area.insert, tk.END, f"[Worker {worker_id}] Converted to MP3: {os.path.basename(mp3_filename)}\n")
                if self.lyrics_var.get() and self.genius:
                    lyrics = self.fetch_lyrics(link['artist'], link['title'])
                    if lyrics:
                        if self.lrc_var.get(): self.create_lrc_file(link['artist'], link['title'], lyrics)
                        self.embed_lyrics_in_mp3(mp3_filename, lyrics)
                self.root.after(0, self.result_area.insert, tk.END, f"[SUCCESS] {link['artist']} - {link['title']}.mp3\n")
            except Exception as e:
                self.root.after(0, self.result_area.insert, tk.END, f"[FAILED] {link['title']} - {str(e)}\n")
            finally:
                with self.download_lock:
                    self.downloaded_tracks += 1
                self.root.after(0, self.update_overall_progress)
                self.download_queue.task_done()
    def fetch_lyrics(self, artist, title):
        if not self.genius: return None
        try:
            song = self.genius.search_song(title, artist)
            return song.lyrics if song else None
        except Exception: return None
    def create_lrc_file(self, artist, title, lyrics):
        if not lyrics: return
        lrc_filename = os.path.join(self.download_dir, f"{self.sanitize_filename(artist)} - {self.sanitize_filename(title)}.lrc")
        try:
            lrc_content = f"[ar:{artist}]\n[ti:{title}]\n"
            lyrics = re.sub(r'.*Lyrics', '', lyrics, 1)
            lines = [line.strip() for line in lyrics.split('\n') if line.strip() and not line.strip().startswith('[')]
            lrc_content += "\n".join(lines)
            with open(lrc_filename, 'w', encoding='utf-8') as f: f.write(lrc_content)
        except Exception as e: self.root.after(0, self.result_area.insert, tk.END, f"Error creating LRC: {e}\n")
    def update_overall_progress(self):
        self.overall_progress_bar["value"] = self.downloaded_tracks
        if self.total_tracks > 0:
            percentage = (self.downloaded_tracks / self.total_tracks) * 100
            self.overall_percentage_label.config(text=f"{int(percentage)}%")
            self.current_track_label.config(text=f"Processed {self.downloaded_tracks} of {self.total_tracks} tracks...")
    def monitor_download(self):
        if any(t.is_alive() for t in self.threads):
            self.root.after(1000, self.monitor_download)
        else:
            self.is_downloading = False
            self.root.after(0, self.show_completion_message)
            self.root.after(0, self.enable_ui)
    def show_completion_message(self):
        messagebox.showinfo("Complete", f"Download process finished. Processed {self.downloaded_tracks}/{self.total_tracks} files.")
    def enable_ui(self):
        self.fetch_button.config(state=tk.NORMAL)
        self.download_button.config(state=tk.NORMAL)
        self.overall_progress_bar["value"] = self.total_tracks
        if self.total_tracks > 0: self.overall_percentage_label.config(text="100%")
        self.current_track_label.config(text="All downloads finished.")
        
def main():
    root = tk.Tk()
    root.resizable(False, False)
    app = DarkModeSpotifyDownloader(root)
    root.mainloop()

if __name__ == "__main__":
    main()
