import mido
from mido import Message, MidiFile, MidiTrack, MetaMessage, pitchwheel
import random
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
import threading


# ========================= CONFIG (defaults) =========================
KEY = "A"                  # Change to any root
MODE = "minor"             # "major" or "minor"
PROGRESSION = ["i", "VI", "III", "VII"]  # Venus Theory modal style
OCTAVE_BASS = 2
OCTAVE_CHORDS = 4
TEMPO = 128
DURATION_BEATS = 4
ARP = True                 # Higher‑frequency arp bass (Diva / Jon Audio vibe)
NEURAL_VARIATION = True
PYTHAGOREAN_MODE = True    # Pure 3:2 fifths + pitch‑bend
# =========================================================


# Scales
MAJOR_SCALE = [0, 2, 4, 5, 7, 9, 11]
MINOR_SCALE = [0, 2, 3, 5, 7, 8, 10]


def get_scale(root, mode):
    root_note = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"].index(root)
    scale = MAJOR_SCALE if mode == "major" else MINOR_SCALE
    return [(root_note + deg) % 12 for deg in scale]


def roman_to_base_chord(roman, scale):
    roman_map = {"i":0, "ii":1, "iii":2, "iv":3, "v":4, "vi":5, "vii":6,
                 "I":0, "II":1, "III":2, "IV":3, "V":4, "VI":5, "VII":6}
    degree = roman_map[roman.upper()]
    root = scale[degree]
    if roman.islower():
        triad = [root, (root + 3) % 12, (root + 7) % 12]
        ext = [(root + 10) % 12]
    else:
        triad = [root, (root + 4) % 12, (root + 7) % 12]
        ext = [(root + 11) % 12]
    ninth = (root + 2) % 12
    return triad + ext + [ninth]


class PythagoreanTuner:
    def __init__(self, root_midi=60):
        self.root_midi = root_midi
        self.fifth_ratio_cents = 701.955
        self.octave_cents = 1200.0

    def get_pythagorean_note(self, scale_degree, octave_offset=0):
        fifth_steps = [0, 2, 4, -1, 1, 3, 5, -2, 0, 2, 4, -1][scale_degree]
        cents = fifth_steps * self.fifth_ratio_cents
        while cents >= self.octave_cents:
            cents -= self.octave_cents
        while cents < 0:
            cents += self.octave_cents
        midi_float = self.root_midi + (cents / 100.0)
        midi_note = int(round(midi_float))
        bend_cents = (midi_float - midi_note) * 100.0
        bend_value = int(bend_cents * 81.92)
        return midi_note + (12 * octave_offset), bend_value


class NeuralChoralcelo:
    def __init__(self, scale, pythagorean_tuner=None, neural_variation=True):
        self.scale = scale
        self.neural_variation = neural_variation
        self.pythagorean_tuner = pythagorean_tuner

    def consonance_score(self, note1, note2):
        interval = abs(note1 - note2) % 12
        scores = {0: 10, 7: 9, 5: 8, 4: 7, 3: 6, 9: 5, 2: 4, 11: 3, 1: 1, 6: 0, 8: 2, 10: 2}
        return scores.get(interval, 0)

    def generate_cello_voicing(self, base_chord, octave):
        voicing = []
        root = base_chord[0]
        voicing.append(root + 12 * octave)
        voicing.append((root + 7) % 12 + 12 * octave)
        voicing.append(base_chord[1] + 12 * (octave + 1))
        if len(base_chord) > 3:
            voicing.append(base_chord[3] + 12 * octave)
        if len(base_chord) > 4:
            ninth_oct = octave + (1 if random.random() > 0.5 else 2)
            voicing.append(base_chord[4] + 12 * ninth_oct)
        if self.neural_variation and random.random() > 0.6:
            eleventh = (root + 5) % 12
            if self.consonance_score(root, eleventh) > 5:
                voicing.append(eleventh + 12 * (octave + 1))
        if self.neural_variation and random.random() > 0.7:
            voicing[1] -= 12
        voicing = sorted(set(voicing))
        if self.pythagorean_tuner:
            tuned = []
            bends = []
            for n in voicing:
                mn, b = self.pythagorean_tuner.get_pythagorean_note(n % 12, n // 12)
                tuned.append(mn)
                bends.append(b)
            return tuned, bends
        return voicing, None


def create_bass_track(scale, progression, arp=False, pythagorean_tuner=None):
    track = MidiTrack()
    track.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(TEMPO)))
    for roman in progression * 2:
        base = roman_to_base_chord(roman, scale)
        root_deg = base[0]
        root_midi = root_deg + 12 * OCTAVE_BASS
        if pythagorean_tuner:
            root_midi, bend = pythagorean_tuner.get_pythagorean_note(root_deg, OCTAVE_BASS)
            track.append(pitchwheel(channel=0, pitch=bend, time=0))
        if arp:
            arp_notes = [root_midi, (root_midi + 7) % 12 + 12 * OCTAVE_BASS, root_midi + 12]
            for n in arp_notes * 2:
                track.append(Message('note_on', note=n, velocity=100, time=120))
                track.append(Message('note_off', note=n, velocity=0, time=60))
        else:
            track.append(Message('note_on', note=root_midi, velocity=110, time=0))
            track.append(Message('note_off', note=root_midi, velocity=0, time=int(DURATION_BEATS * 480)))
        track.append(MetaMessage('text', text="SECRET-TAPE-SOURCE → ToTape9 + Slew4", time=0))
    return track


def create_chords_track(scale, progression, neural=True, pythagorean_tuner=None):
    track = MidiTrack()
    choral_celo = NeuralChoralcelo(scale, pythagorean_tuner, neural_variation=neural)
    for roman in progression * 2:
        base_chord = roman_to_base_chord(roman, scale)
        voicing, bends = choral_celo.generate_cello_voicing(base_chord, OCTAVE_CHORDS)
        for i, note in enumerate(voicing):
            vel = random.randint(75, 110)
            track.append(Message('note_on', note=note, velocity=vel, time=0))
            if bends and i < len(bends):
                track.append(pitchwheel(channel=0, pitch=bends[i], time=0))
        gate_time = int(DURATION_BEATS * 480)
        track.append(Message('note_off', note=voicing[0], velocity=0, time=gate_time))
        for note in voicing[1:]:
            track.append(Message('note_off', note=note, velocity=0, time=0))
    return track


# ====================== MAIN GUI ======================
def build_gui():
    root = tk.Tk()
    root.title("Venus Pressure Bass – Easy Customizer")
    root.geometry("500x480")

    # --- Variables ---
    key_var = tk.StringVar(value=KEY)
    mode_var = tk.StringVar(value=MODE)
    arp_var = tk.IntVar(value=1 if ARP else 0)
    dur_beats_var = tk.DoubleVar(value=DURATION_BEATS)
    neural_var = tk.IntVar(value=1 if NEURAL_VARIATION else 0)
    pythagorean_var = tk.IntVar(value=1 if PYTHAGOREAN_MODE else 0)

    # --- Rows ---
    row = 0

    # Key
    tk.Label(root, text="Key:").grid(row=row, column=0, sticky="w", padx=10, pady=4)
    key_cbox = ttk.Combobox(
        root, textvariable=key_var,
        values=["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"],
        width=8
    )
    key_cbox.grid(row=row, column=1, sticky="w", padx=10, pady=4)

    # Mode
    tk.Label(root, text="Mode:").grid(row=row, column=2, sticky="w", padx=10, pady=4)
    mode_cbox = ttk.Combobox(
        root, textvariable=mode_var,
        values=["major", "minor"], width=8
    )
    mode_cbox.grid(row=row, column=3, sticky="w", padx=10, pady=4)
    row += 1

    # Progression
    tk.Label(root, text="Progression (Roman):").grid(row=row, column=0, sticky="w", padx=10, pady=4)
    prog_var = tk.StringVar(value=" ".join(PROGRESSION))
    ttk.Entry(root, textvariable=prog_var, width=32).grid(row=row, column=1, columnspan=3, padx=10, pady=4)
    row += 1

    # ARP / Sub bass
    arp_check = tk.Checkbutton(root, text="ARP bass (Diva / Jon Audio vibe)", variable=arp_var)
    arp_check.grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=4)

    sub_check = tk.Checkbutton(root, text="NeuralChoralcelo variation", variable=neural_var)
    sub_check.grid(row=row, column=2, columnspan=2, sticky="w", padx=10, pady=4)
    row += 1

    # Pythagorean mode
    pyth_check = tk.Checkbutton(root, text="Pythagorean tuning (3:2 fifths)", variable=pythagorean_var)
    pyth_check.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=4)
    row += 1

    # Duration‑per‑chord
    tk.Label(root, text="Duration per chord (beats):").grid(row=row, column=0, sticky="w", padx=10, pady=4)
    dur_scale = tk.Scale(
        root, from_=1, to=8, orient="horizontal", resolution=0.5,
        variable=dur_beats_var
    )
    dur_scale.grid(row=row, column=1, columnspan=3, sticky="we", padx=10, pady=4)
    row += 1

    # Help text
    help_text = (
        "Examples:\n"
        "  Progression: i VI III VII\n"
        "  or: I vi IV V (pure copy‑paste)"
    )
    tk.Label(root, text=help_text, justify="left", font=("TkDefaultFont", 8)).grid(
        row=row, column=0, columnspan=4, padx=10, pady=4
    )
    row += 1

    # Buttons
    def start_export():
        try:
            # Parse current GUI values
            key       = key_var.get()
            mode      = mode_var.get()
            arp       = bool(arp_var.get())
            dur_beats = dur_beats_var.get()
            neural    = bool(neural_var.get())
            pyth      = bool(pythagorean_var.get())

            prog_text = prog_var.get().strip()
            prog = [p.strip() for p in prog_text.split() if p.strip()]

            if len(prog) == 0:
                raise ValueError("Progression cannot be empty.")

            # Regenerate scale and (optionally) tuner
            scale = get_scale(key, mode)
            tuner = PythagoreanTuner(root_midi=60) if pyth else None

            # Use values as globals for consistency
            global KEY, MODE, PROGRESSION, ARP, NEURAL_VARIATION, PYTHAGOREAN_MODE, DURATION_BEATS
            KEY               = key
            MODE              = mode
            PROGRESSION       = prog
            ARP               = arp
            NEURAL_VARIATION  = neural
            PYTHAGOREAN_MODE  = pyth
            DURATION_BEATS    = dur_beats

            # Run the same MIDI‑generation logic
            mid = MidiFile()
            mid.tracks.append(create_bass_track(scale, PROGRESSION, arp=arp, pythagorean_tuner=tuner))
            mid.tracks.append(create_chords_track(scale, PROGRESSION, neural=neural, pythagorean_tuner=tuner))

            output_dir = Path("venus_pressure_output")
            output_dir.mkdir(exist_ok=True)

            mid.save(output_dir / "full_harmony_final.mid")
            bass_mid = MidiFile()
            bass_mid.tracks.append(mid.tracks[0])
            bass_mid.save(output_dir / "bass.mid")
            chords_mid = MidiFile()
            chords_mid.tracks.append(mid.tracks[1])
            chords_mid.save(output_dir / "chords.mid")

            messagebox.showinfo(
                "Done",
                f"✓ Generated files in:\n{output_dir}\nKey: {key} {mode}\nProgression: {' - '.join(prog)}"
            )
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def run_export():
        # Run in a thread so GUI doesn’t freeze
        thread = threading.Thread(target=start_export, daemon=True)
        thread.start()

    tk.Button(root, text="Generate MIDIs", command=run_export, bg="lightgreen").grid(
        row=row, column=0, columnspan=2, pady=10
    )
    tk.Button(root, text="Close", command=root.destroy).grid(
        row=row, column=2, columnspan=2, pady=10
    )

    root.mainloop()


if __name__ == "__main__":
    print(f"🎉 Venus Pressure Bass – theRealla GUI Edition")
    print("   • Launching configuration window…")
    print("   • When ready, press 'Generate MIDIs' to create:")
    print("     • full_harmony_final.mid")
    print("     • bass.mid")
    print("     • chords.mid")
    print("   • Files will be saved in: venus_pressure_output/")
    build_gui()

