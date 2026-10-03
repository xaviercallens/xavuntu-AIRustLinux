#!/usr/bin/env python3
"""
Generate a 3-minute high-definition video demonstration of:
1. The Approach (Physics of computation, energy function E, symplectic conservation, Banach fixed-point autopoiesis)
2. The Architecture (Dual-loop neuro-symbolic engine, multi-tier gateway, Redis streams, open-weight LoRA pipeline)
3. The Recorded Command Line (Lean 4 proofs, 120 PhD benchmarks, Claude/Opus harvester, LoRA DPO trainer)
4. The ASCD Control Center Web Interface (SCADA HUD, Deck 1 Forge, Deck 2 Proving, Deck 3 Engine, God Mode)
5. Symplectic Phase Space Geometry & Final Empirical Results

Total Duration: Exactly 180 seconds (3:00 minutes).
Resolution: 1920x1080 @ 30fps.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PRESENTATION_HTML = PROJECT_ROOT / "web" / "video_presentation.html"
WEB_URL = "http://localhost:5000"
ARTIFACTS_DIR = Path("/home/xavkal/.gemini/antigravity-ide/brain/b642533c-dc99-479f-95f9-46568fa696a5")
OUTPUT_DIR = PROJECT_ROOT / "results"
OUTPUT_MP4 = OUTPUT_DIR / "ascd_architecture_and_control_center_demo_3min.mp4"


def record_playwright_sessions(tmp_dir: Path) -> tuple[Path, Path, Path]:
    """Records the video segments using Playwright Chromium headless."""
    from playwright.sync_api import sync_playwright

    rec_act123_dir = tmp_dir / "rec_act123"
    rec_act4_dir = tmp_dir / "rec_act4"
    rec_act5_dir = tmp_dir / "rec_act5"
    rec_act123_dir.mkdir(parents=True, exist_ok=True)
    rec_act4_dir.mkdir(parents=True, exist_ok=True)
    rec_act5_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--hide-scrollbars",
            ],
        )

        # -------------------------------------------------------------
        # Part 1: Acts 1, 2, 3 (Approach, Architecture, Command-Line)
        # Duration: ~110 seconds
        # -------------------------------------------------------------
        print("[1/4] Recording Part 1: Approach, Architecture & Command-Line Screencast (110s)...")
        ctx1 = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(rec_act123_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page1 = ctx1.new_page()
        page1.goto(f"file://{PRESENTATION_HTML.resolve()}")
        page1.wait_for_timeout(1000)

        # Act 1: 0s -> 35s (Approach & Physics)
        print("  -> Recording Act 1: Paradigm & Physics of Computation (0-35s)...")
        for s in range(0, 36, 2):
            page1.evaluate(f"setVideoTime({s})")
            page1.wait_for_timeout(600)  # Paced playback

        # Act 2: 35s -> 70s (Architecture & Gateway)
        print("  -> Recording Act 2: Architecture & Multi-Tier Gateway (35-70s)...")
        for s in range(36, 71, 2):
            page1.evaluate(f"setVideoTime({s})")
            page1.wait_for_timeout(600)

        # Act 3: 70s -> 110s (Recorded Terminal Execution)
        print("  -> Recording Act 3: Recorded Command-Line Screencast (70-110s)...")
        for s in range(71, 111, 2):
            page1.evaluate(f"setVideoTime({s})")
            # Auto-scroll terminal
            page1.evaluate(
                "const t = document.getElementById('terminal-stream-content'); if(t) t.scrollTop += 20;"
            )
            page1.wait_for_timeout(600)

        ctx1.close()

        # -------------------------------------------------------------
        # Part 2: Act 4 (ASCD Control Center Web Interface)
        # Duration: ~45 seconds
        # -------------------------------------------------------------
        print("[2/4] Recording Part 2: ASCD Swarm Command Deck Web Interface (45s)...")
        ctx2 = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(rec_act4_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page2 = ctx2.new_page()
        page2.goto(WEB_URL)
        page2.wait_for_timeout(2000)

        # Switch to Command Deck (ASCD)
        page2.click("#tab-ascd")
        page2.wait_for_timeout(2500)

        # Trigger high-frequency WebSocket stress
        page2.click("#ascd-btn-stress")
        page2.wait_for_timeout(2000)

        # Interacting with Deck 1: The Forge
        print("  -> Interacting with Deck 1: The Forge (DAG, WebGL, Lean 4 Tribunal)...")
        page2.evaluate("window.scrollBy({ top: 300, behavior: 'smooth' });")
        page2.wait_for_timeout(2000)

        # Drag DAG node
        try:
            dag_node = page2.locator("#ascd-dag-svg circle").first
            if dag_node.is_visible():
                box = dag_node.bounding_box()
                if box:
                    page2.mouse.move(box["x"] + 10, box["y"] + 10)
                    page2.mouse.down()
                    page2.mouse.move(box["x"] + 80, box["y"] + 40, steps=10)
                    page2.mouse.up()
        except Exception:
            pass
        page2.wait_for_timeout(2000)

        # Click Prove on Lean 4 Tribunal to clear red sorry
        try:
            btn_prove = page2.locator("button:has-text('Prove (Remove sorry)')")
            if btn_prove.is_visible():
                btn_prove.click()
        except Exception:
            pass
        page2.wait_for_timeout(2500)

        # Interacting with Deck 2: Proving Grounds
        print("  -> Interacting with Deck 2: Proving Grounds (Heatmap & Diff Slider)...")
        page2.click("#btn-deck-proving")
        page2.wait_for_timeout(2500)

        # Move holographic diff slider back and forth
        try:
            slider_bar = page2.locator("#ascd-diff-slider")
            if slider_bar.is_visible():
                sbox = slider_bar.bounding_box()
                if sbox:
                    page2.mouse.move(sbox["x"], sbox["y"] + 50)
                    page2.mouse.down()
                    page2.mouse.move(sbox["x"] - 120, sbox["y"] + 50, steps=15)
                    page2.wait_for_timeout(1000)
                    page2.mouse.move(sbox["x"] + 120, sbox["y"] + 50, steps=15)
                    page2.mouse.up()
        except Exception:
            pass
        page2.wait_for_timeout(2500)

        # Interacting with Deck 3: Engine Room
        print("  -> Interacting with Deck 3: Engine Room (RL Tinder & Context Treemap)...")
        page2.click("#btn-deck-engine")
        page2.wait_for_timeout(2500)

        # Swipe / click RL Tinder Accept
        try:
            btn_accept = page2.locator("button:has-text('Accept (Right)')")
            if btn_accept.is_visible():
                btn_accept.click()
        except Exception:
            pass
        page2.wait_for_timeout(2000)

        # Open God Mode overlay
        print("  -> Triggering God Mode Emergency Halt Overlay...")
        try:
            page2.click("#ascd-btn-halt")
            page2.wait_for_timeout(3500)
            # Close God Mode and resume swarm
            page2.evaluate("window.resumeSwarmWithoutSteering();")
        except Exception:
            page2.evaluate("window.closeGodModeOverlay();")
        page2.wait_for_timeout(2000)

        # Switch to Concepts tab briefly
        print("  -> Touring Concepts & Video Tab...")
        try:
            page2.click("#tab-concepts")
            page2.wait_for_timeout(3000)
        except Exception:
            page2.evaluate("switchTab('concepts');")
            page2.wait_for_timeout(3000)

        ctx2.close()

        # -------------------------------------------------------------
        # Part 3: Act 5 (Symplectic Phase Space & Synthesis)
        # Duration: ~25 seconds
        # -------------------------------------------------------------
        print("[3/4] Recording Part 3: Symplectic Phase Space Geometry & Results (25s)...")
        ctx3 = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(rec_act5_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page3 = ctx3.new_page()
        page3.goto(f"file://{PRESENTATION_HTML.resolve()}")
        page3.wait_for_timeout(1000)

        for s in range(155, 181, 1):
            page3.evaluate(f"setVideoTime({s})")
            page3.wait_for_timeout(600)

        ctx3.close()
        browser.close()

    video1 = next(rec_act123_dir.glob("*.webm"))
    video2 = next(rec_act4_dir.glob("*.webm"))
    video3 = next(rec_act5_dir.glob("*.webm"))

    print(f"Recorded video segments: 1: {video1.name}, 2: {video2.name}, 3: {video3.name}")
    return video1, video2, video3


def get_video_duration(video_path: Path) -> float:
    """Extracts duration in seconds using ffmpeg -i."""
    res = subprocess.run(["ffmpeg", "-i", str(video_path)], capture_output=True, text=True)
    for line in (res.stdout + res.stderr).splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 1.0


def build_3min_video(video1: Path, video2: Path, video3: Path, output_file: Path) -> Path:
    """Uses FFmpeg to combine, rescale, and synchronize the video to 180 seconds with ambient synth audio."""
    import numpy as np
    import wave

    print("[4/4] Transcoding and compiling full 180-second HD video with FFmpeg...")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        seg1 = tmp_path / "seg1.mp4"
        seg2 = tmp_path / "seg2.mp4"
        seg3 = tmp_path / "seg3.mp4"
        concat_txt = tmp_path / "concat.txt"
        audio_wav = tmp_path / "ambient_synth.wav"

        # Durations: Act 1-3: 110.0s, Act 4: 45.0s, Act 5: 25.0s -> Total: 180.0s
        d1 = get_video_duration(video1)
        d2 = get_video_duration(video2)
        d3 = get_video_duration(video3)
        print(f"  Source durations: Seg1={d1:.2f}s, Seg2={d2:.2f}s, Seg3={d3:.2f}s")

        scale_filter = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30"

        # Re-encode Seg1 to exact 110.0s
        s1 = 110.0 / max(0.5, d1)
        cmd1 = [
            "ffmpeg", "-y", "-i", str(video1),
            "-vf", f"setpts={s1}*PTS,{scale_filter}",
            "-t", "110.0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg1)
        ]
        subprocess.run(cmd1, check=True)

        # Re-encode Seg2 to exact 45.0s
        s2 = 45.0 / max(0.5, d2)
        cmd2 = [
            "ffmpeg", "-y", "-i", str(video2),
            "-vf", f"setpts={s2}*PTS,{scale_filter}",
            "-t", "45.0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg2)
        ]
        subprocess.run(cmd2, check=True)

        # Re-encode Seg3 to exact 25.0s
        s3 = 25.0 / max(0.5, d3)
        cmd3 = [
            "ffmpeg", "-y", "-i", str(video3),
            "-vf", f"setpts={s3}*PTS,{scale_filter}",
            "-t", "25.0",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg3)
        ]
        subprocess.run(cmd3, check=True)

        # Write concat demuxer manifest
        concat_txt.write_text(f"file '{seg1.resolve()}'\nfile '{seg2.resolve()}'\nfile '{seg3.resolve()}'\n")

        # Synthesize 180s harmonic ambient synthesizer soundtrack
        sr = 44100
        dur = 180.0
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)
        beat = 0.5 + 0.5 * np.sin(2 * np.pi * 0.5 * t)
        snd = (
            0.07 * np.sin(2 * np.pi * 110 * t) +
            0.05 * np.sin(2 * np.pi * 164.81 * t) +
            0.04 * np.sin(2 * np.pi * 220 * t) +
            0.03 * np.sin(2 * np.pi * 261.63 * t) +
            0.02 * beat * np.sin(2 * np.pi * 440 * t)
        )
        snd_int16 = (np.clip(snd, -1.0, 1.0) * 32767).astype(np.int16)
        with wave.open(str(audio_wav), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(snd_int16.tobytes())

        # Concatenate using safe demuxer and merge audio
        cmd_final = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-i", str(audio_wav),
            "-t", "180.0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_file)
        ]
        subprocess.run(cmd_final, check=True)

    print(f"SUCCESS: Video generated at {output_file} (Size: {output_file.stat().st_size} bytes)")
    return output_file


def main():
    print("================================================================================")
    print("  AutoevolveAI & SuperGravity — 3-Minute Comprehensive Video Generator")
    print("================================================================================")
    start_time = time.time()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        v1, v2, v3 = record_playwright_sessions(tmp_path)
        final_mp4 = build_3min_video(v1, v2, v3, OUTPUT_MP4)

    # Copy to artifacts directory
    if ARTIFACTS_DIR.exists():
        artifact_mp4 = ARTIFACTS_DIR / "ascd_architecture_and_control_center_demo_3min.mp4"
        shutil.copy2(final_mp4, artifact_mp4)
        print(f"Copied to artifacts directory: {artifact_mp4}")

    elapsed = time.time() - start_time
    print(f"Total video pipeline completed in {elapsed:.2f} seconds.")


if __name__ == "__main__":
    main()
