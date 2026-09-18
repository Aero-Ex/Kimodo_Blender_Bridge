

A Blender addon that generates AI-driven human motion via [NVIDIA Kimodo](https://github.com/nv-tlabs/kimodo) and imports it directly into your scene — no copy-pasting, no manual BVH wrangling.

## Star History

<a href="https://www.star-history.com/?repos=lewdineer%2FKimodo_Blender_Bridge&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=lewdineer/Kimodo_Blender_Bridge&type=date&theme=dark&legend=top-left&sealed_token=gg3e8bjBVO1mASsY7F2FfwXezEB5zKIehjMw-s8K0AeGqeg94JCIRoPyBtxv55OxO9Pvi5cFwEyXXpA7wOwC8khA42N0EIz--WX4-WLBhTkFav2p97mv0gNKScQBzfaLta9xHnw9ELr6Ntm0RTGEbBvwvSp8RubVcK10aKSlsQs3pwmd4LuWqQp0kpux" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=lewdineer/Kimodo_Blender_Bridge&type=date&legend=top-left&sealed_token=gg3e8bjBVO1mASsY7F2FfwXezEB5zKIehjMw-s8K0AeGqeg94JCIRoPyBtxv55OxO9Pvi5cFwEyXXpA7wOwC8khA42N0EIz--WX4-WLBhTkFav2p97mv0gNKScQBzfaLta9xHnw9ELr6Ntm0RTGEbBvwvSp8RubVcK10aKSlsQs3pwmd4LuWqQp0kpux" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=lewdineer/Kimodo_Blender_Bridge&type=date&legend=top-left&sealed_token=gg3e8bjBVO1mASsY7F2FfwXezEB5zKIehjMw-s8K0AeGqeg94JCIRoPyBtxv55OxO9Pvi5cFwEyXXpA7wOwC8khA42N0EIz--WX4-WLBhTkFav2p97mv0gNKScQBzfaLta9xHnw9ELr6Ntm0RTGEbBvwvSp8RubVcK10aKSlsQs3pwmd4LuWqQp0kpux" />
 </picture>
</a>

## Links / Video guide
Youtube tutorial: https://youtu.be/nbiaS43Ncng
Superhive: https://superhivemarket.com/products/kimodoblenderbridge

---

## Tested on 
**Blender 5.1 / 4.4**

**Arch Linux RTX 3090 Python 3.12**

**Windows 11 RTX 1080 Python 3.12**

**Windows 11 RTX 5070 Python 3.13**

<img width="1237" height="1257" alt="image" src="https://github.com/user-attachments/assets/71a1666d-a460-40eb-af23-1dbb8ab750cb" />


---

## How it works

Blender's embedded Python cannot load PyTorch or Kimodo directly. The addon solves this with a two-process bridge:

```
Blender (addon)                Kimodo venv
  subprocess_client.py  ─────▶  bridge_server.py
                        ◀─────  (model loaded once, handles requests)
```

The bridge server loads the Kimodo model once at startup and then responds to generation requests over stdin/stdout. Blender stays responsive while generation runs in a background thread.

---

## Requirements

| Requirement | Notes |
|---|---|
| Blender 4.0+ | Tested on 5.1 (Windows & Arch Linux) |
| Python 3.10–3.12 | System Python used to create the managed venv |
| NVIDIA GPU | 8 GB+ VRAM recommended; 16 GB+ for best results |
| CUDA | Must match your PyTorch build (CUDA 12.1 installed by default) |
| ~10 GB disk | For the managed venv, model weights, and LLM2Vec encoder |

> **Low VRAM?** Run `kimodo_textencoder --device cpu` in a separate terminal with the Kimodo venv activated. This offloads the text encoder to CPU and frees several GB of VRAM.

---

## Installation

As of v1.2.0 Kimodo installs itself automatically — no terminal required. The addon is also compatible with the Blender 4.2+ Extensions platform (includes `blender_manifest.toml`).

### 1 — Install the Blender addon

1. Download or clone this repository (top-right **Code → Download ZIP**).
2. Open Blender → **Edit → Preferences → Add-ons → Install from Disk…**
3. Select the downloaded zip and enable **"Kimodo Motion Generator"**.

### 2 — Click "Install Kimodo (Auto)"

Open the **Kimodo** N-Panel tab (press `N` in the 3D Viewport), expand **Connection**, and click **Install Kimodo (Auto)**.

The installer will:
- Create a managed Python venv at `~/.kimodo-venv/`
- Install PyTorch (CUDA 12.1), all Kimodo dependencies, and the [Aero-Ex offline fork](https://github.com/Aero-Ex/kimodo)
- Download the LLM2Vec text-encoder model locally and patch it for offline use
- Download the `Kimodo-SOMA-RP-v1` model weights into the HF cache
- Set the Python path automatically when done

Progress is shown live in the Connection panel. The full log is printed to the system console (launch Blender from a terminal, or on Windows use **Window → Toggle System Console**).

> **Requires:** Python 3.10–3.12 on your system PATH, internet access, and ~10 GB of free disk space. After the initial install, Kimodo runs fully offline.

### Manual installation (advanced)

If you already have Kimodo installed in your own venv, skip the auto-installer and paste the path to your venv Python into the **Kimodo Python** field in the Connection panel.

---

## Quick Start

### Generate motion from a text prompt

1. **Start** the bridge: click **Start Kimodo** in the Connection panel.  
   The status line will show *Loading model…* then *Ready* once the model is loaded (this takes 10–60 s the first time).

2. Open the **Generate** panel. It opens in **Single Clip** mode — type a prompt (e.g. `a person jogs in a circle`), set a duration, and click **Generate Motion**.

3. A `Kimodo_Source` armature will appear in your scene with the generated motion applied.

> **30 FPS tip:** Kimodo always generates at 30 FPS. If your scene is set to a different frame rate, an alert will appear above the Generate button with a **Set to 30 FPS** button.

### Use multiple segments

Switch the **Generate** panel to **Timeline** mode for this. Each segment is an independent text prompt mapped to a frame range. **Generate Motion** sends every enabled segment to Kimodo in a single model call, producing one continuous animation with smooth transitions between prompts.

- Segments are listed in order. The **Start** frame of each segment after the first is automatically locked to the **End** frame of the previous segment — just drag the End frame and the next segment's Start updates automatically.
- Use **Duplicate** to copy a segment and place it immediately after.
- Use **↑ / ↓** to reorder segments.

<img width="2676" height="1181" alt="image" src="https://github.com/user-attachments/assets/a5d336e9-f32f-44c7-9aca-a09983e869d6" />


### Motion constraints

Spatial goals can be given to Kimodo so the generated motion passes through specific positions:

| Constraint | What it controls |
|---|---|
| Root XZ | Where the character's root lands on the ground plane |
| Full-Body | A full joint-pose keyframe (pose a reference armature) |
| Left / Right Hand | Wrist end-effector position |
| Left / Right Foot | Foot / heel end-effector position |

To add a constraint:
1. Move the 3D cursor (or select an armature) to the desired position.
2. Set the timeline to the target frame.
3. In the **Motion Constraints** panel, click the constraint type.

**Auto-Origin** (off by default) shifts all constraint positions so the earliest root waypoint lands at Kimodo's world origin — author constraints anywhere in your scene without worrying about absolute coordinates.

---

## Panel reference

| Panel | What's in it |
|---|---|
| **Connection** | Kimodo Python path, model selector, Start / Stop bridge |
| **Generate** | Single Clip mode (one prompt, duration, seed) or Timeline mode (segment list, frame ranges) — one Generate Motion button either way |
| **Motion Constraints** | Spatial waypoints for the generated motion |
| **Help** | Quick-start checklist, VRAM tip |

---

## Troubleshooting

**Bridge won't start / "Failed to start"**
- Check the system console for `[Kimodo Bridge]` lines — the full Python/PyTorch error is printed there.
- Check that the Python path points to the venv Python that has Kimodo installed.
- If you used the auto-installer and it failed partway through, click **Retry Install** — it will wipe the partial venv and start clean.

**CUDA out of memory**
- Use a shorter duration or fewer segments.

**Frames from imorted animation dont match**
- Kimodo generates at exactly 30 FPS. Use the **Set to 30 FPS** button that appears in the Generate panel when your scene is at a different frame rate.

---

## File overview

| File | Role |
|---|---|
| `__init__.py` | Blender addon entry point |
| `bridge_server.py` | Subprocess: loads Kimodo, handles generation requests |
| `subprocess_client.py` | Blender-side bridge manager |
| `operators.py` | All `bpy.ops.kimodo.*` operators |
| `properties.py` | All `bpy.props` scene settings |
| `panels.py` | N-panel UI |
| `constraints.py` | Converts Blender constraint markers to Kimodo JSON |
| `ui_list.py` | UIList helper for generation history |
| `setup_operator.py` | One-click auto-installer for Kimodo and all dependencies |

---

## License

See [LICENSE](LICENSE).
