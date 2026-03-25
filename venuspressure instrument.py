import mido
from mido import Message, MidiFile, MidiTrack, MetaMessage, pitchwheel
import random
import torch
import torch.nn as nn
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox


# ========================= DEFAULTS =========================
DEFAULT_KEY = "A"
DEFAULT_MODE = "minor"
DEFAULT_PROGRESSION = ["i", "VI", "III", "VII"]
DEFAULT_OCTAVE_BASS = 2
DEFAULT_OCTAVE_CHORDS = 4
DEFAULT_TEMPO = 128
DEFAULT_DURATION_BEATS = 4
DEFAULT_ARP = True
DEFAULT_NEURAL = True
DEFAULT_PYTHAGOREAN = True


# ========================= SCALES & CHORDS =========================
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


# ========================= PYTHAGOREAN TUNER =========================
class PythagoreanTuner:
    def __init__(self, root_midi=60):
        self.root_midi = root_midi
        self.fifth_ratio_cents = 701.955
        self.octave_cents = 1200.0

    def get_pythagorean_note(self, scale_degree, octave_offset=0):
        fifth_steps = [0, 2, 4, -1, 1, 3, 5, -2, 0, 2, 4, -1][scale_degree]
        cents = fifth_steps * self.fifth_ratio_cents
        while cents >= self.octave_cents: cents -= self.octave_cents
        while cents < 0: cents += self.octave_cents
        midi_float = self.root_midi + (cents / 100.0)
        midi_note = int(round(midi_float))
        bend_cents = (midi_float - midi_note) * 100.0
        bend_value = int(bend_cents * 81.92)
        return midi_note + (12 * octave_offset), bend_value


# ========================= NEURALCHORALCELO =========================
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


# ========================= TIMING / GROOVE =========================
def thick_quantize(note_time_ticks, strength=0.85, ticks_per_beat=480, subdivision=16, bias="straight"):
    if strength == 0.0:
        return note_time_ticks
    base_step = ticks_per_beat // 4  # 1/16th = 120 ticks
    if bias == "shuffle":
        base_step = int(base_step * 0.95)
    elif bias == "triplet":
        base_step = int(base_step * 2 / 3)
    elif bias == "vesper":
        base_step = int(base_step * 0.9 + random.uniform(-8, 8))
    nearest = round(note_time_ticks / base_step) * base_step
    return int(note_time_ticks + (nearest - note_time_ticks) * strength)

def thick_swing(onset_ticks, note_index, swing_enabled=True, swing_percent=0.60, style="swing_2to1"):
    if not swing_enabled:
        return onset_ticks
    if (note_index % 2) == 1:
        if style == "swing_2to1":
            return onset_ticks + int(onset_ticks * 0.5 * swing_percent)
        elif style == "triplet_hip":
            return onset_ticks + int(onset_ticks * 0.6 * swing_percent)
        elif style == "vesper":
            return onset_ticks + int(onset_ticks * 0.55 * swing_percent)
    return onset_ticks


# ========================= MOVEMENT NEURAL NET (LSTM) =========================
class MovementNeuralNet(nn.Module):
    def __init__(self, n_tokens=256, n_hidden=128, n_layers=2):
        super().__init__()
        self.n_tokens = n_tokens
        self.n_hidden = n_hidden
        self.n_layers = n_layers
        self.embedding = nn.Embedding(n_tokens, 64)
        self.lstm = nn.LSTM(64, n_hidden, n_layers, batch_first=True)
        self.output = nn.Linear(n_hidden, n_tokens)

    def forward(self, tokens, hidden=None):
        x = self.embedding(tokens)
        out, hidden = self.lstm(x, hidden)
        logits = self.output(out)
        return logits, hidden


def generate_movement_aligned_to_chords(
    model, chord_track, sixteen_bar=False, swing_style="swing_2to1", swing_enabled=True
):
    """Generate a movement (bass + drum + light harmony) aligned to NeuralChoralcelo chords."""
    ticks_per_beat = 480
    total_beats = 16 if sixteen_bar else 8

    # Gather onset‑times from chord track (NeuralChoralcelo timing)
    chord_times = []
    t = 0
    for msg in chord_track:
        t += msg.time
        if msg.type == "note_on" and hasattr(msg, "note"):
            chord_times.append(t)

    if len(chord_times) == 0:
        chord_times = [0]

    # Use a small sliding window of chord times as “context”
    context_times = sorted(set(chord_times))
    track = MidiTrack()

    tokens = [random.randint(0, 255) for _ in range(10)]  # warm‑up tokens
    hidden = None

    for beat in range(total_beats):
        beat_start = beat * ticks_per_beat
        beat_end = beat_start + ticks_per_beat

        # 1. Use the neural network to generate some events
        token_tensor = torch.tensor(tokens[-10:], dtype=torch.long).unsqueeze(0)
        with torch.no_grad():
            logits, hidden = model(token_tensor)
            next_token = torch.argmax(logits[0, -1]).item()
        tokens.append(next_token)

        # 2. Encode token → (note, velocity, offset within beat)
        note = 36 + (next_token % 24)       # 36–60: bass + drum range
        vel = 60 + (next_token % 40)
        offset = (next_token % 4) * 120     # 0, 120, 240, 360 ticks

        # 3. Align to Neptune/NeuralChoralcelo grid
        event_time = beat_start + offset
        event_time = thick_quantize(event_time, 0.85, ticks_per_beat, 16, bias=swing_style if swing_enabled else "straight")
        if swing_enabled:
            event_time = thick_swing(event_time, beat, True, 0.6, swing_style)

        # 4. Clip to beat range
        if beat_start <= event_time <= beat_end:
            track.append(Message('note_on',  note=note, velocity=vel, time=event_time))
            track.append(Message('note_off', note=note, velocity=0,   time=60))

    return track


# ========================= MIDI GENERATION =========================
def generate_midi(key, mode, progression_str, arp, dur_beats, neural, pythagorean, sixteen_bar, swing_enabled, swing_style):
    # 1. Chords first (NeuralChoralcelo)
    progression = [p.strip() for p in progression_str.split() if p.strip()] or DEFAULT_PROGRESSION
    scale = get_scale(key, mode)
    tuner = PythagoreanTuner(root_midi=60) if pythagorean else None
    choral_celo = NeuralChoralcelo(scale, tuner, neural_variation=neural)

    mid = MidiFile()
    base_onset = 0
    loop_mult = 4 if sixteen_bar else 2

    # Chords track (NeuralChoralcelo)
    chords_track = MidiTrack()
    chords_track.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(DEFAULT_TEMPO)))
    for i, roman in enumerate(progression * loop_mult):
        base_chord = roman_to_base_chord(roman, scale)
        voicing, bends = choral_celo.generate_cello_voicing(base_chord, DEFAULT_OCTAVE_CHORDS)
        for j, note in enumerate(voicing):
            vel = random.randint(75, 110)
            attack = 0
            if swing_enabled:
                attack = thick_quantize(0, 0.8, 480, 16, bias="shuffle")
            chords_track.append(Message('note_on', note=note, velocity=vel, time=attack))
            if bends and j < len(bends):
                chords_track.append(pitchwheel(channel=0, pitch=bends[j], time=0))
        gate = int(dur_beats * 480)
        if swing_enabled:
            gate = thick_quantize(gate, 0.8)
        chords_track.append(Message('note_off', note=voicing[0], velocity=0, time=gate))
        for note in voicing[1:]:
            chords_track.append(Message('note_off', note=note, velocity=0, time=0))
    mid.tracks.append(chords_track)

    # Bass track (bass + ARP)
    bass_track = MidiTrack()
    bass_track.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(DEFAULT_TEMPO)))
    base_onset = 0
    for i, roman in enumerate(progression * loop_mult):
        base = roman_to_base_chord(roman, scale)
        root_midi = base[0] + 12 * DEFAULT_OCTAVE_BASS
        if pythagorean:
            root_midi, bend = tuner.get_pythagorean_note(base[0], DEFAULT_OCTAVE_BASS)
            bass_track.append(pitchwheel(channel=0, pitch=bend, time=0))
        if arp:
            arp_notes = [root_midi, (root_midi + 7) % 12 + 12 * DEFAULT_OCTAVE_BASS, root_midi + 12]
            for j, n in enumerate(arp_notes * 2):
                onset = base_onset
                onset = thick_swing(onset, j, swing_enabled, 0.60, swing_style)
                onset = thick_quantize(onset, 0.85, 480, 16, bias=swing_style if swing_enabled else "straight")
                bass_track.append(Message('note_on', note=n, velocity=100, time=onset))
                bass_track.append(Message('note_off', note=n, velocity=0, time=60))
        else:
            bass_track.append(Message('note_on', note=root_midi, velocity=110, time=0))
            off_time = int(dur_beats * 480)
            off_time = thick_quantize(off_time, 0.85)
            bass_track.append(Message('note_off', note=root_midi, velocity=0, time=off_time))
        bass_track.append(MetaMessage('text', text="SECRET-TAPE-SOURCE → ToTape9 + Slew4", time=0))
        base_onset += int(dur_beats * 480)
    mid.tracks.append(bass_track)

    # 3. Generate NeuralChoralcelo‑aligned Movement (LSTM)
    model = MovementNeuralNet()
    movement_track = generate_movement_aligned_to_chords(
        model=model,
        chord_track=chords_track,
        sixteen_bar=sixteen_bar,
        swing_style=swing_style,
        swing_enabled=swing_enabled
    )
    mid.tracks.append(movement_track)

    # Save
    output_dir = Path("venus_pressure_output")
    output_dir.mkdir(exist_ok=True)

    filename = f"venus_pressure_{key}_{mode}_{'16bar' if sixteen_bar else '8bar'}.mid"
    mid.save(output_dir / filename)

    bass_only = MidiFile()
    bass_only.tracks.append(bass_track)
    bass_only.save(output_dir / "bass.mid")

    chords_only = MidiFile()
    chords_only.tracks.append(chords_track)
    chords_only.save(output_dir / "chords.mid")

    movement_only = MidiFile()
    movement_only.tracks.append(movement_track)
    movement_only.save(output_dir / "movement.mid")

    return True, str(output_dir / filename)


# ========================= GUI =========================
def build_gui():
    root = tk.Tk()
    root.title("Venus Theory - Perfect Box")
    root.geometry("600x700")
    root.resizable(False, False)

    # Variables
    key_var = tk.StringVar(value=DEFAULT_KEY)
    mode_var = tk.StringVar(value=DEFAULT_MODE)
    prog_var = tk.StringVar(value=" ".join(DEFAULT_PROGRESSION))
    arp_var = tk.IntVar(value=1 if DEFAULT_ARP else 0)
    neural_var = tk.IntVar(value=1 if DEFAULT_NEURAL else 0)
    pythagorean_var = tk.IntVar(value=1 if DEFAULT_PYTHAGOREAN else 0)
    sixteen_var = tk.IntVar(value=0)
    swing_var = tk.IntVar(value=1)
    swing_style_var = tk.StringVar(value="swing_2to1")
    dur_var = tk.DoubleVar(value=DEFAULT_DURATION_BEATS)

    row = 0
    tk.Label(root, text="VENUS THEORY – PRESSURE + NEURAL MOVEMENT", font=("TkDefaultFont", 14, "bold")).grid(
        row=row, column=0, columnspan=4, pady=12)

    tk.Label(root, text="Key:").grid(row=row + 1, column=0, sticky="w", padx=15, pady=5)
    ttk.Combobox(root, textvariable=key_var, values=["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"], width=6).grid(
        row=row + 1, column=1, sticky="w")

    tk.Label(root, text="Mode:").grid(row=row + 1, column=2, sticky="w", padx=15,

