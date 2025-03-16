import os
import sys
import re
import time
import ssl
import threading
from queue import Queue
from tkinter import filedialog

# Add more robust error handling
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

# FFmpeg Configuration
FFMPEG_PATH = r"C:\ffmpeg-master-latest-win64-gpl\bin"
if FFMPEG_PATH not in os.environ['PATH']:
    os.environ['PATH'] += os.pathsep + FFMPEG_PATH

class DarkModeSpotifyDownloader:
    def __init__(self, root):
        # Window Setup
        self.root = root
        self.root.title("Spotify to YouTube MP3 Converter")
        self.root.geometry("900x700")
        self.root.configure(bg='#1E1E1E')

        # Custom Fonts
        self.title_font = tkfont.Font(family="Segoe UI", size=16, weight="bold")
        self.label_font = tkfont.Font(family="Segoe UI", size=10)
        
        # Dark Theme Colors
        self.colors = {
            'background': '#1E1E1E',
            'text': '#1DB954',
            'accent': '#1DB954',  # Spotify Green
            'input_bg': '#2C2C2C',
            'button_bg': '#1DB954',
            'button_fg': '#FFFFFF',
            'progress_bg': '#3C3C3C',
        }

        # Spotify API Configuration
        try:
            self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id='ADD CLIENT ID',
                client_secret='ADD CLIENT SECRET'
            ))
        except Exception as e:
            messagebox.showerror("Spotify API Error", f"Failed to initialize Spotify client: {e}")
            sys.exit(1)
            
        # Initialize Genius for lyrics
        try:
            # You need to get a Genius API token from https://genius.com/api-clients
            self.genius = lyricsgenius.Genius("ADD GENIUS API")
            self.genius.verbose = False  # Turn off status messages
            self.genius.remove_section_headers = True  # Remove section headers (e.g. [Chorus]) from lyrics
        except Exception as e:
            messagebox.showerror("Genius API Error", f"Failed to initialize Genius client: {e}")
            self.genius = None

        # Download Management
        self.download_queue = Queue()
        self.is_downloading = False
        self.youtube_links = []

        # Create downloads directory
        self.download_dir = os.path.abspath("downloads")
        os.makedirs(self.download_dir, exist_ok=True)

        # Create Dark Mode GUI
        self.create_dark_gui()

    def create_dark_gui(self):
        # Main Container
        main_frame = tk.Frame(self.root, bg=self.colors['background'])
        main_frame.pack(padx=20, pady=20, fill=tk.BOTH, expand=True)

        # Title
        title_label = tk.Label(
            main_frame, 
            text="Spotify Playlist Downloader", 
            font=self.title_font, 
            fg=self.colors['text'], 
            bg=self.colors['background']
        )
        title_label.pack(pady=(0, 20))

        # URL Entry Frame
        url_frame = tk.Frame(main_frame, bg=self.colors['background'])
        url_frame.pack(fill=tk.X, pady=10)

        # URL Label
        url_label = tk.Label(
            url_frame, 
            text="Spotify Playlist URL:", 
            font=self.label_font, 
            fg=self.colors['text'], 
            bg=self.colors['background']
        )
        url_label.pack(side=tk.LEFT, padx=(0, 10))

        # URL Entry with Dark Mode Style
        self.url_entry = tk.Entry(
            url_frame, 
            width=70, 
            font=self.label_font, 
            bg=self.colors['input_bg'], 
            fg=self.colors['text'], 
            insertbackground=self.colors['text']
        )
        self.url_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 10))

        # Fetch Tracks Button
        self.fetch_button = tk.Button(
            url_frame, 
            text="Fetch Tracks", 
            command=self.fetch_tracks,
            font=self.label_font,
            bg=self.colors['button_bg'], 
            fg=self.colors['button_fg'],
            activebackground=self.colors['accent']
        )
        self.fetch_button.pack(side=tk.RIGHT)

        # Directory Selection Frame
        dir_frame = tk.Frame(main_frame, bg=self.colors['background'])
        dir_frame.pack(fill=tk.X, pady=10)

        # Directory Label
        dir_label = tk.Label(
            dir_frame, 
            text="Save to:", 
            font=self.label_font, 
            fg=self.colors['text'], 
            bg=self.colors['background']
        )
        dir_label.pack(side=tk.LEFT, padx=(0, 10))

        # Directory Entry
        self.dir_var = tk.StringVar()
        self.dir_entry = tk.Entry(
            dir_frame, 
            textvariable=self.dir_var,
            width=70, 
            font=self.label_font, 
            bg=self.colors['input_bg'], 
            fg=self.colors['text'], 
            insertbackground=self.colors['text'],
            state='readonly'
        )
        self.dir_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 10))

        # Browse Button
        self.browse_button = tk.Button(
            dir_frame, 
            text="Browse", 
            command=self.select_directory,
            font=self.label_font,
            bg=self.colors['button_bg'], 
            fg=self.colors['button_fg'],
            activebackground=self.colors['accent']
        )
        self.browse_button.pack(side=tk.RIGHT)
        
        # Add Lyrics Option
        lyrics_frame = tk.Frame(main_frame, bg=self.colors['background'])
        lyrics_frame.pack(fill=tk.X, pady=10)
        
        self.lyrics_var = tk.BooleanVar(value=True)
        lyrics_check = tk.Checkbutton(
            lyrics_frame,
            text="Download and embed lyrics",
            variable=self.lyrics_var,
            font=self.label_font,
            fg=self.colors['text'],
            bg=self.colors['background'],
            selectcolor=self.colors['input_bg'],
            activebackground=self.colors['background'],
            activeforeground=self.colors['text']
        )
        lyrics_check.pack(side=tk.LEFT)
        
        # Add LRC file Option
        self.lrc_var = tk.BooleanVar(value=True)
        lrc_check = tk.Checkbutton(
            lyrics_frame,
            text="Create .lrc files",
            variable=self.lrc_var,
            font=self.label_font,
            fg=self.colors['text'],
            bg=self.colors['background'],
            selectcolor=self.colors['input_bg'],
            activebackground=self.colors['background'],
            activeforeground=self.colors['text']
        )
        lrc_check.pack(side=tk.LEFT, padx=(20, 0))

        # Set default directory
        self.dir_var.set(self.download_dir)

        # Progress Frames
        progress_container = tk.Frame(main_frame, bg=self.colors['background'])
        progress_container.pack(fill=tk.X, pady=10)

        # Overall Progress
        overall_progress_frame = tk.Frame(progress_container, bg=self.colors['background'])
        overall_progress_frame.pack(fill=tk.X, pady=5)

        self.overall_percentage_label = tk.Label(
            overall_progress_frame, 
            text="0%", 
            font=self.label_font, 
            fg=self.colors['text'], 
            bg=self.colors['background']
        )
        self.overall_percentage_label.pack(side=tk.LEFT)

        self.overall_progress_bar = ttk.Progressbar(
            overall_progress_frame, 
            orient=tk.HORIZONTAL, 
            length=600, 
            mode="determinate",
            style="Custom.Horizontal.TProgressbar"
        )
        self.overall_progress_bar.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)

        # Current Track Progress
        current_track_frame = tk.Frame(progress_container, bg=self.colors['background'])
        current_track_frame.pack(fill=tk.X, pady=5)

        self.current_track_label = tk.Label(
            current_track_frame, 
            text="", 
            font=self.label_font, 
            fg=self.colors['text'], 
            bg=self.colors['background']
        )
        self.current_track_label.pack()

        track_progress_subframe = tk.Frame(current_track_frame, bg=self.colors['background'])
        track_progress_subframe.pack(fill=tk.X)

        self.current_track_percentage_label = tk.Label(
            track_progress_subframe, 
            text="", 
            font=self.label_font, 
            fg=self.colors['text'], 
            bg=self.colors['background']
        )
        self.current_track_percentage_label.pack(side=tk.LEFT)

        self.current_track_progress_bar = ttk.Progressbar(
            track_progress_subframe, 
            orient=tk.HORIZONTAL, 
            length=600, 
            mode="determinate",
            style="Custom.Horizontal.TProgressbar"
        )
        self.current_track_progress_bar.pack(side=tk.LEFT, padx=10, expand=True, fill=tk.X)

        self.time_remaining_label = tk.Label(
            track_progress_subframe, 
            text="", 
            font=self.label_font, 
            fg=self.colors['text'], 
            bg=self.colors['background']
        )
        self.time_remaining_label.pack(side=tk.LEFT, padx=10)

        # Results Area
        self.result_area = scrolledtext.ScrolledText(
            main_frame, 
            width=90, 
            height=10, 
            wrap=tk.WORD,
            font=self.label_font,
            bg=self.colors['input_bg'], 
            fg=self.colors['text'],
            insertbackground=self.colors['text']
        )
        self.result_area.pack(pady=10, fill=tk.BOTH, expand=True)

        # Download Button
        self.download_button = tk.Button(
            main_frame, 
            text="Download All as MP3", 
            command=self.download_all_tracks,
            font=self.label_font,
            bg=self.colors['button_bg'], 
            fg=self.colors['button_fg'],
            activebackground=self.colors['accent']
        )
        self.download_button.pack(pady=10)

        # Configure Progressbar Style
        style = ttk.Style()
        style.theme_use('default')
        style.configure(
            "Custom.Horizontal.TProgressbar", 
            background=self.colors['accent'],
            troughcolor=self.colors['progress_bg']
        )

    def select_directory(self):
        selected_dir = filedialog.askdirectory()
        if selected_dir:
            self.download_dir = selected_dir
            self.dir_var.set(selected_dir)
            os.makedirs(self.download_dir, exist_ok=True)

    def sanitize_filename(self, name):
        sanitized = re.sub(r'[\\/*?:"<>|]', '_', name)
        return sanitized.strip()

    def fetch_tracks(self):
        # Clear previous results
        self.result_area.delete(1.0, tk.END)
        playlist_link = self.url_entry.get()

        if not playlist_link:
            messagebox.showerror("Error", "Please enter a Spotify playlist URL.")
            return

        try:
            # Extract playlist tracks
            tracks = self.get_spotify_playlist_tracks(playlist_link)
            
            # Update progress bar
            self.total_tracks = len(tracks)
            self.overall_progress_bar["maximum"] = self.total_tracks
            self.overall_progress_bar["value"] = 0

            # Find YouTube links
            self.youtube_links = []
            self.result_area.insert(tk.END, f"Found {self.total_tracks} tracks. Searching YouTube...\n")
            
            for track in tracks:
                youtube_link = self.find_youtube_link(track)
                if youtube_link:
                    self.youtube_links.append(youtube_link)
                
                # Update progress
                self.overall_progress_bar["value"] += 1
                self.overall_percentage_label.config(
                    text=f"{int((self.overall_progress_bar['value'] / self.total_tracks) * 100)}%"
                )
                self.root.update()

            # Display found links
            self.result_area.insert(tk.END, "\nFound YouTube links:\n")
            for idx, link in enumerate(self.youtube_links, 1):
                self.result_area.insert(tk.END, f"{idx}. {link['title']} by {link['artist']}\n")
                self.result_area.insert(tk.END, f"   URL: {link['youtube_url']}\n\n")

            messagebox.showinfo("Success", f"Found {len(self.youtube_links)} tracks!")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def get_spotify_playlist_tracks(self, playlist_link):
        # Extract playlist ID
        playlist_id = re.search(r'playlist/([a-zA-Z0-9]+)', playlist_link).group(1)
        
        # Fetch playlist tracks
        results = self.sp.playlist_tracks(playlist_id)
        tracks = []
        
        while results:
            tracks.extend([{
                'name': item['track']['name'],
                'artist': item['track']['artists'][0]['name'],
                'album': item['track']['album']['name']
            } for item in results['items'] if item['track']])
            
            results = self.sp.next(results) if results['next'] else None
        
        return tracks

    def find_youtube_link(self, track):
        # Construct search query
        search_query = f"{track['name']} {track['artist']} audio"
        
        try:
            # Use YouTube Search
            results = YoutubeSearch(search_query, max_results=1).to_dict()
            
            if results:
                return {
                    'title': track['name'],
                    'artist': track['artist'],
                    'album': track.get('album', ''),
                    'youtube_url': f"https://youtube.com{results[0]['url_suffix']}"
                }
            
            return None

        except Exception as e:
            self.result_area.insert(tk.END, f"Search error: {search_query} - {str(e)}\n")
            return None

    def download_all_tracks(self):
        if not self.youtube_links:
            messagebox.showerror("Error", "Fetch tracks first!")
            return

        # Ensure download directory exists
        os.makedirs(self.download_dir, exist_ok=True)

        # Clear previous queue
        while not self.download_queue.empty():
            self.download_queue.get()

        # Populate download queue
        for link in self.youtube_links:
            self.download_queue.put(link)

        # Reset progress
        self.downloaded_tracks = 0
        self.overall_progress_bar["value"] = 0
        self.overall_percentage_label.config(text="0%")
        self.current_track_label.config(text="")
        self.current_track_progress_bar["value"] = 0
        self.current_track_percentage_label.config(text="")
        self.time_remaining_label.config(text="")

        # Disable UI
        self.is_downloading = True
        self.fetch_button.config(state=tk.DISABLED)
        self.download_button.config(state=tk.DISABLED)
        self.result_area.delete(1.0, tk.END)

        # Start download thread
        self.current_download_thread = threading.Thread(
            target=self.download_worker, 
            daemon=True
        )
        self.current_download_thread.start()
        self.monitor_download()

    def fetch_lyrics(self, artist, title):
        """Fetch lyrics from Genius"""
        if not self.genius:
            return None
            
        try:
            self.result_area.insert(tk.END, f"Searching for lyrics: {title} by {artist}...\n")
            song = self.genius.search_song(title, artist)
            if song:
                return song.lyrics
            return None
        except Exception as e:
            self.result_area.insert(tk.END, f"Error fetching lyrics: {str(e)}\n")
            return None

    def save_lyrics_to_file(self, artist, title, lyrics):
        """Save lyrics to a text file"""
        if not lyrics:
            return None
            
        lyrics_filename = os.path.join(
            self.download_dir, 
            f"{self.sanitize_filename(artist)} - {self.sanitize_filename(title)}.txt"
        )
        
        try:
            with open(lyrics_filename, 'w', encoding='utf-8') as f:
                f.write(lyrics)
            return lyrics_filename
        except Exception as e:
            self.result_area.insert(tk.END, f"Error saving lyrics: {str(e)}\n")
            return None
            
    def create_lrc_file(self, artist, title, lyrics):
        """Create an LRC file from lyrics text"""
        if not lyrics:
            return None
            
        # Create filename for the LRC file - same name as the MP3
        lrc_filename = os.path.join(
            self.download_dir, 
            f"{self.sanitize_filename(artist)} - {self.sanitize_filename(title)}.lrc"
        )
        
        try:
            # Basic LRC format 
            # Note: this creates a simple LRC without timestamps - just the lyrics text
            
            # Add header information
            lrc_content = f"[ar:{artist}]\n"
            lrc_content += f"[ti:{title}]\n"
            
            # Clean up the lyrics
            # Remove "Lyrics" text if it exists at the beginning
            if lyrics.startswith("Lyrics"):
                lyrics = lyrics.split("\n", 1)[1]
                
            # Remove Genius attribution if present
            if "Lyrics provided by Genius" in lyrics:
                lyrics = lyrics.split("Lyrics provided by Genius")[0]
                
            # Process the lyrics line by line
            lines = lyrics.split('\n')
            for line in lines:
                # Skip empty lines and common headers
                line = line.strip()
                if line and not line.startswith("[") and not line.endswith("]"):
                    # Add each line to the LRC file without timestamp
                    # For a basic LRC file we can just include the lyrics text
                    lrc_content += f"{line}\n"
            
            # Save the LRC file
            with open(lrc_filename, 'w', encoding='utf-8') as f:
                f.write(lrc_content)
                
            self.result_area.insert(tk.END, f"Created LRC file: {os.path.basename(lrc_filename)}\n")
            return lrc_filename
        except Exception as e:
            self.result_area.insert(tk.END, f"Error creating LRC file: {str(e)}\n")
            return None

    def embed_lyrics_in_mp3(self, mp3_file, lyrics):
        """Embed lyrics into MP3 file using FFmpeg"""
        if not lyrics:
            return
            
        try:
            # Create temporary lyrics file
            temp_lyrics_file = f"{mp3_file}.lyrics.txt"
            with open(temp_lyrics_file, 'w', encoding='utf-8') as f:
                f.write(lyrics)
                
            # Create temporary output file
            temp_output_file = f"{mp3_file}.temp.mp3"
            
            # Use FFmpeg to embed lyrics
            cmd = [
                'ffmpeg', '-i', mp3_file, 
                '-i', temp_lyrics_file, 
                '-map', '0', '-map', '1', 
                '-c', 'copy', '-id3v2_version', '3', 
                '-metadata:s:t', 'mimetype=text/plain', 
                temp_output_file
            ]
            
            import subprocess
            subprocess.run(cmd, check=True, capture_output=True)
            
            # Replace original file with the one containing lyrics
            os.remove(mp3_file)
            os.rename(temp_output_file, mp3_file)
            
            # Clean up
            if os.path.exists(temp_lyrics_file):
                os.remove(temp_lyrics_file)
                
            self.result_area.insert(tk.END, f"Lyrics embedded in MP3 file\n")
            
        except Exception as e:
            self.result_area.insert(tk.END, f"Error embedding lyrics: {str(e)}\n")

    def download_worker(self):
        start_time = time.time()
        self.total_tracks = len(self.youtube_links)

        while not self.download_queue.empty():
            link = self.download_queue.get()
            
            try:
                # Update UI about current download
                self.root.after(0, self.update_current_track_ui, link)

                # Get the output filename
                output_filename = os.path.join(
                    self.download_dir, 
                    f"{self.sanitize_filename(link['artist'])} - {self.sanitize_filename(link['title'])}"
                )
                mp3_filename = f"{output_filename}.mp3"

                # yt-dlp configuration for robust downloading
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                    'outtmpl': output_filename + '.%(ext)s',
                    'no_warnings': True,
                    'ignoreerrors': False,
                    'progress_hooks': [self.download_progress_hook]
                }

                # Download using yt-dlp
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([link['youtube_url']])
                
                # If lyrics option is checked, get and add lyrics
                if self.lyrics_var.get() and self.genius:
                    # Update UI about lyrics download
                    self.root.after(0, self.result_area.insert, tk.END, 
                                  f"Fetching lyrics for {link['title']}...\n")
                    
                    # Fetch lyrics
                    lyrics = self.fetch_lyrics(link['artist'], link['title'])
                    
                    if lyrics:
                        # Save lyrics to text file
                        self.save_lyrics_to_file(link['artist'], link['title'], lyrics)
                        
                        # Create LRC file if option is checked
                        if self.lrc_var.get():
                            self.create_lrc_file(link['artist'], link['title'], lyrics)
                        
                        # Embed lyrics in MP3
                        self.embed_lyrics_in_mp3(mp3_filename, lyrics)
                        
                        self.root.after(0, self.result_area.insert, tk.END, 
                                      f"Lyrics added to {link['artist']} - {link['title']}.mp3\n")
                    else:
                        self.root.after(0, self.result_area.insert, tk.END, 
                                      f"No lyrics found for {link['title']}\n")

                # Update overall progress
                self.downloaded_tracks += 1
                elapsed_time = time.time() - start_time
                avg_time_per_track = elapsed_time / self.downloaded_tracks
                estimated_total_time = avg_time_per_track * self.total_tracks
                time_remaining = max(0, estimated_total_time - elapsed_time)

                # Update UI with overall progress and time estimate
                self.root.after(0, self.update_overall_progress, time_remaining)

                # Update UI about successful download
                self.root.after(0, self.result_area.insert, tk.END, 
                              f"Success: {link['artist']} - {link['title']}.mp3\n")

            except Exception as e:
                # Handle download errors
                self.root.after(0, self.result_area.insert, tk.END, 
                              f"Failed: {link['title']} - {str(e)}\n")

            # Mark task as done and add small delay
            self.download_queue.task_done()
            time.sleep(1)

        # Reset downloading state
        self.is_downloading = False
        self.root.after(0, self.enable_ui)

    def download_progress_hook(self, d):
        if d['status'] == 'downloading':
            downloaded_bytes = d.get('downloaded_bytes', 0)
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            
            if total_bytes > 0:
                percent = downloaded_bytes / total_bytes * 100
                
                # Update current track progress
                self.root.after(0, self.update_current_track_progress, percent)

    def update_current_track_ui(self, link):
        self.current_track_label.config(
            text=f"Downloading: {link['title']} by {link['artist']}"
        )
        self.current_track_progress_bar["value"] = 0
        self.current_track_percentage_label.config(text="0%")

    def update_current_track_progress(self, percent):
        self.current_track_progress_bar["value"] = percent
        self.current_track_percentage_label.config(
            text=f"{percent:.1f}%"
        )

    def update_overall_progress(self, time_remaining):
        # Update overall progress bar
        self.overall_progress_bar["value"] = self.downloaded_tracks
        self.overall_percentage_label.config(
            text=f"{int((self.downloaded_tracks / self.total_tracks) * 100)}%"
        )

        # Update time remaining
        minutes, seconds = divmod(int(time_remaining), 60)
        self.time_remaining_label.config(
            text=f"Time Remaining: {minutes:02d}:{seconds:02d}"
        )

    def monitor_download(self):
        if self.is_downloading:
            self.root.after(1000, self.monitor_download)
        else:
            self.root.after(0, self.show_completion_message)

    def show_completion_message(self):
        # Count successfully downloaded MP3 files
        success_count = len([f for f in os.listdir(self.download_dir) if f.endswith(".mp3")])
        messagebox.showinfo("Complete", f"Downloaded {success_count}/{len(self.youtube_links)} files!")

    def enable_ui(self):
        # Re-enable UI elements
        self.fetch_button.config(state=tk.NORMAL)
        self.download_button.config(state=tk.NORMAL)
        self.overall_progress_bar["value"] = 0
        self.overall_percentage_label.config(text="0%")
        self.current_track_label.config(text="")
        self.current_track_progress_bar["value"] = 0
        self.current_track_percentage_label.config(text="")
        self.time_remaining_label.config(text="")

def main():
    root = tk.Tk()
    # Disable minimize/maximize buttons
    root.resizable(False, False)
    
    # Remove window border
    root.overrideredirect(False)
    
    # Optional: Add a custom close button
    app = DarkModeSpotifyDownloader(root)
    root.mainloop()

if __name__ == "__main__":
    main()
