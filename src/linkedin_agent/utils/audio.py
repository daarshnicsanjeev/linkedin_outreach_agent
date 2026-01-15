"""
Audio and Notification Utilities
=================================
Sound alerts and Windows toast notifications.
Extracted from agent implementations for reuse.
"""

import asyncio
import os
import threading
from typing import Optional, Callable

try:
    import numpy as np
    import sounddevice as sd
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

try:
    from winotify import Notification, audio as win_audio
    WINOTIFY_AVAILABLE = True
except ImportError:
    WINOTIFY_AVAILABLE = False


class AudioManager:
    """
    Manages audio alerts and notifications.
    
    Features:
    - Multi-tone alert sounds 
    - Laptop speaker detection (bypasses headphones)
    - Windows toast notifications
    - Async-safe sound playback
    """
    
    def __init__(self, app_id: str = "LinkedIn Agent"):
        self.app_id = app_id
        self._speaker_device = None
    
    def find_speaker_device(self) -> Optional[int]:
        """Find laptop speaker device (not headphones) by name."""
        if not AUDIO_AVAILABLE:
            return None
        
        if self._speaker_device is not None:
            return self._speaker_device
            
        try:
            devices = sd.query_devices()
            speaker_keywords = ['speaker', 'realtek', 'built-in', 'internal']
            
            for i, device in enumerate(devices):
                if device['max_output_channels'] > 0:
                    name_lower = device['name'].lower()
                    if any(kw in name_lower for kw in speaker_keywords):
                        self._speaker_device = i
                        return i
            
            # Fallback to default output
            return sd.default.device[1]
        except Exception:
            return None
    
    def play_ready_sound(self, use_speaker: bool = True) -> None:
        """
        Play attention-grabbing sound when ready for review.
        
        Uses a multi-tone ascending melody to capture attention.
        """
        if not AUDIO_AVAILABLE:
            print("Audio unavailable - review ready!")
            return
        
        def play():
            try:
                sample_rate = 44100
                device = self.find_speaker_device() if use_speaker else None
                
                # Ascending melody: C5 -> E5 -> G5 -> C6
                frequencies = [523.25, 659.25, 783.99, 1046.50]
                pattern = []
                
                for freq in frequencies:
                    duration = 0.15
                    t = np.linspace(0, duration, int(sample_rate * duration), False)
                    # Sine wave with envelope
                    envelope = np.exp(-3 * t / duration)
                    tone = np.sin(2 * np.pi * freq * t) * envelope
                    pattern.extend(tone)
                    # Small gap between notes
                    pattern.extend(np.zeros(int(sample_rate * 0.05)))
                
                audio = np.array(pattern, dtype=np.float32) * 0.5
                sd.play(audio, samplerate=sample_rate, device=device, blocking=True)
                
            except Exception as e:
                print(f"Sound playback error: {e}")
        
        thread = threading.Thread(target=play, daemon=True)
        thread.start()
    
    def play_complete_sound(self, use_speaker: bool = True) -> None:
        """
        Play victory sound when posting is complete.
        
        Uses a celebratory two-note fanfare.
        """
        if not AUDIO_AVAILABLE:
            print("Audio unavailable - task complete!")
            return
        
        def play():
            try:
                sample_rate = 44100
                device = self.find_speaker_device() if use_speaker else None
                
                # Victory fanfare: G5 -> C6 (held)
                pattern = []
                
                # First note: G5
                freq1 = 783.99
                duration1 = 0.2
                t1 = np.linspace(0, duration1, int(sample_rate * duration1), False)
                tone1 = np.sin(2 * np.pi * freq1 * t1)
                pattern.extend(tone1)
                
                # Gap
                pattern.extend(np.zeros(int(sample_rate * 0.1)))
                
                # Second note: C6 (held longer)
                freq2 = 1046.50
                duration2 = 0.4
                t2 = np.linspace(0, duration2, int(sample_rate * duration2), False)
                envelope2 = np.exp(-2 * t2 / duration2)
                tone2 = np.sin(2 * np.pi * freq2 * t2) * envelope2
                pattern.extend(tone2)
                
                audio = np.array(pattern, dtype=np.float32) * 0.5
                sd.play(audio, samplerate=sample_rate, device=device, blocking=True)
                
            except Exception as e:
                print(f"Sound playback error: {e}")
        
        thread = threading.Thread(target=play, daemon=True)
        thread.start()
    
    def play_alert_sound(self, frequency: float = 880.0, duration: float = 0.5,
                         use_speaker: bool = True) -> None:
        """Play a simple alert tone at specified frequency."""
        if not AUDIO_AVAILABLE:
            return
        
        def play():
            try:
                sample_rate = 44100
                device = self.find_speaker_device() if use_speaker else None
                
                t = np.linspace(0, duration, int(sample_rate * duration), False)
                tone = np.sin(2 * np.pi * frequency * t) * 0.5
                
                audio = tone.astype(np.float32)
                sd.play(audio, samplerate=sample_rate, device=device, blocking=True)
            except Exception:
                pass
        
        thread = threading.Thread(target=play, daemon=True)
        thread.start()
    
    def show_toast_notification(self, title: str, message: str,
                                 action_label: str = None,
                                 action_url: str = None) -> None:
        """
        Show a Windows toast notification.
        
        Args:
            title: Notification title
            message: Notification body text
            action_label: Optional button label
            action_url: Optional URL or path to open on click
        """
        if not WINOTIFY_AVAILABLE:
            print(f"[{title}] {message}")
            return
        
        def show():
            try:
                toast = Notification(
                    app_id=self.app_id,
                    title=title,
                    msg=message,
                    duration="long"
                )
                
                toast.set_audio(win_audio.Default, loop=False)
                
                if action_label and action_url:
                    toast.add_actions(label=action_label, launch=action_url)
                
                toast.show()
            except Exception as e:
                print(f"Toast notification error: {e}")
        
        thread = threading.Thread(target=show, daemon=True)
        thread.start()


# Module-level singleton for convenience
_audio_manager = None

def get_audio_manager() -> AudioManager:
    """Get or create the global AudioManager instance."""
    global _audio_manager
    if _audio_manager is None:
        _audio_manager = AudioManager()
    return _audio_manager

def play_ready_sound():
    """Convenience function to play ready sound."""
    get_audio_manager().play_ready_sound()

def play_complete_sound():
    """Convenience function to play complete sound."""
    get_audio_manager().play_complete_sound()
