"""Test script to check if Windows sounds work on this system."""
import winsound
import os

print("Testing Windows sound playback...")
print("=" * 50)

# Test 1: PlaySound with system alias
print("\n[Test 1] PlaySound with SystemExclamation alias...")
try:
    winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
    print("  -> Completed (did you hear it?)")
except Exception as e:
    print(f"  -> FAILED: {e}")

import time
time.sleep(1)

# Test 2: PlaySound with SystemAsterisk
print("\n[Test 2] PlaySound with SystemAsterisk alias...")
try:
    winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
    print("  -> Completed (did you hear it?)")
except Exception as e:
    print(f"  -> FAILED: {e}")

time.sleep(1)

# Test 3: MessageBeep
print("\n[Test 3] MessageBeep with MB_ICONEXCLAMATION...")
try:
    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    print("  -> Completed (did you hear it?)")
except Exception as e:
    print(f"  -> FAILED: {e}")

time.sleep(1)

# Test 4: Beep (PC speaker)
print("\n[Test 4] Beep (PC speaker - may not work on modern PCs)...")
try:
    winsound.Beep(1000, 500)
    print("  -> Completed (did you hear it?)")
except Exception as e:
    print(f"  -> FAILED: {e}")

time.sleep(1)

# Test 5: Direct WAV file
print("\n[Test 5] Direct WAV file from Windows Media folder...")
try:
    media_folder = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Media')
    print(f"  Checking folder: {media_folder}")
    
    # Try common sound files
    wav_files = [
        'Windows Notify System Generic.wav',
        'Windows Notify.wav',
        'Windows Ding.wav',
        'notify.wav',
        'chimes.wav',
    ]
    
    played = False
    for wav_name in wav_files:
        wav_path = os.path.join(media_folder, wav_name)
        if os.path.exists(wav_path):
            print(f"  Found: {wav_name}")
            winsound.PlaySound(wav_path, winsound.SND_FILENAME)
            print(f"  -> Played {wav_name} (did you hear it?)")
            played = True
            break
    
    if not played:
        print("  -> No common WAV files found")
        # List what's available
        if os.path.exists(media_folder):
            files = [f for f in os.listdir(media_folder) if f.endswith('.wav')][:5]
            print(f"  Available: {files}")
except Exception as e:
    print(f"  -> FAILED: {e}")

print("\n" + "=" * 50)
print("Sound test complete. Which tests produced audible sound?")
