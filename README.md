# Night Screen

**English** · [Русский](README.ru.md)

A small GUI for Linux (X11) to dim and warm your screen at night: color
temperature (1000–10000 K), brightness (10–100 %), contrast (30–150 %) and the
contrast pivot (0–100 %). It changes the GPU gamma ramp and leaves the monitor
backlight alone, so you avoid the PWM flicker that cheap monitors show at low
hardware brightness.

> The interface itself is in Russian.

## Run

```sh
git clone https://github.com/antoh1986/night-screen.git
cd night-screen
./run.sh
```

Requirements: Python 3 with tkinter, plus libX11 and libXrandr (present by default
on Linux Mint). `xsct` is optional: it is only used at startup to read the current
values if the screen was changed from outside this window.

## Usage

- Sliders: mouse, wheel, arrow keys (one step), PageUp/PageDown (×10).
- Entry fields: type a number and press Enter; out-of-range values are clamped.
- Presets (Day / Evening / Night / Deep night) change only temperature and
  brightness. "Сбросить всё" (Reset all) at the bottom restores everything:
  6500 K, 100 %, contrast 100 %, pivot 50 %. Contrast and pivot also have their own
  reset buttons.
- Contrast is a slope around the pivot. Above 100 %, tones darker than the pivot get
  darker and lighter ones get lighter (extremes are clipped). Below 100 %,
  everything is pulled toward the pivot.
- The contrast pivot decides which tones get lighter and which get darker when
  contrast is above 100 %. Right: more tones get lighter; left: more get darker
  (matches the track color). To make dim borders brighter instead of vanishing, use
  about 80–90 %. 100 is plain amplification (black stays black), 0 darkens
  everything (white stays white). Internally the value is inverted: the gray level
  that contrast leaves untouched is 100 % − slider value.
- Order of operations: contrast first, then brightness and temperature, so
  brightness can always dim even a very contrasty picture.
- Settings stay after the window is closed. The last values are stored in
  `~/.config/night-screen/state.json`; if the screen differs from them at startup
  (after a reboot or an `xsct` call), the window shows the real state.
- To restore the screen: "Reset all" or `xsct 6500 1`.

## Files

- `night_screen.py`: the window; limits and presets are at the top.
- `gamma.py`: writes the gamma ramp via XRandR (at contrast 100 % it matches
  `xsct` exactly).
- `run.sh`: launcher.
- `AGENTS.md`: short project map (in Russian).

Not for Wayland: XRandR gamma control is X11-only.
