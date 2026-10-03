#!/usr/bin/env python3
"""
Autonomous Video Demonstration Recorder for 3 Top PhD Multi-Agent Use Cases:
1. Act 1: Literature Review Grounding (23 arXiv citations) & Frontier Model Tier Assignment
2. Act 2: Recorded Command-Line Screencast of Physical Hardness Execution & Cryptographic Receipts
3. Act 3: ASCD Swarm Command Deck on Desktop (1920x1080) — HUD, Forge DAG, Proving Grounds, Engine Room, God Mode
4. Act 4: ASCD Swarm Command Deck on Mobile (375x812) — Full Mobile Web Control & Steering
5. Act 5: Gemini 3.1 Pro Formal Peer Review (50/50 Score) & 3 Generated IEEEtran Two-Column Scientific Papers

Resolution: 1920x1080 @ 30fps
Target Duration: ~180s (3:00)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

PRESENTATION_HTML = PROJECT_ROOT / "web" / "phd_3cases_presentation.html"
WEB_URL = "http://localhost:5000"
ARTIFACTS_DIR = Path("/home/xavkal/.gemini/antigravity-ide/brain/b642533c-dc99-479f-95f9-46568fa696a5")
OUTPUT_DIR = PROJECT_ROOT / "results"
OUTPUT_MP4 = OUTPUT_DIR / "phd_3_cases_multi_agent_hardness_demo.mp4"


def record_playwright_sessions(tmp_dir: Path) -> tuple[Path, Path, Path, Path]:
    """Records the video segments using Playwright Chromium headless."""
    from playwright.sync_api import sync_playwright

    rec_pres1_dir = tmp_dir / "rec_pres1"
    rec_web_desktop_dir = tmp_dir / "rec_web_desktop"
    rec_web_mobile_dir = tmp_dir / "rec_web_mobile"
    rec_pres2_dir = tmp_dir / "rec_pres2"

    rec_pres1_dir.mkdir(parents=True, exist_ok=True)
    rec_web_desktop_dir.mkdir(parents=True, exist_ok=True)
    rec_web_mobile_dir.mkdir(parents=True, exist_ok=True)
    rec_pres2_dir.mkdir(parents=True, exist_ok=True)

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
        # Part 1: Presentation Deck (Act 1 & Act 2: Lit Review & CLI Screencast)
        # Duration: ~65 seconds
        # -------------------------------------------------------------
        print("[1/5] Recording Part 1: Literature Review & Command-Line Execution Screencast (65s)...")
        ctx1 = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(rec_pres1_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page1 = ctx1.new_page()
        page1.goto(f"file://{PRESENTATION_HTML.resolve()}")
        page1.wait_for_timeout(1000)

        # Act 1: 0s -> 30s (Lit Review & Model Tiering)
        print("  -> Recording Act 1: Pre-Execution Literature Review & Model Tiering (0-30s)...")
        for s in range(0, 31, 2):
            page1.evaluate(f"setVideoTime({s})")
            page1.wait_for_timeout(500)

        # Act 2: 30s -> 65s (CLI Screencast)
        print("  -> Recording Act 2: Command-Line Physical Hardness Screencast (30-65s)...")
        for s in range(32, 66, 2):
            page1.evaluate(f"setVideoTime({s})")
            # Auto scroll terminal
            page1.evaluate(
                "const t = document.getElementById('terminal-stream-content'); if(t) t.scrollTop += 35;"
            )
            page1.wait_for_timeout(500)

        ctx1.close()

        # -------------------------------------------------------------
        # Part 2: Live ASCD Swarm Command Deck on Desktop (1920x1080)
        # Duration: ~55 seconds
        # -------------------------------------------------------------
        print("[2/5] Recording Part 2: ASCD Swarm Command Deck Web Interface on Desktop (55s)...")
        ctx2 = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(rec_web_desktop_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page2 = ctx2.new_page()
        page2.goto(WEB_URL)
        page2.wait_for_timeout(2000)

        # Switch to Command Deck (ASCD)
        page2.click("#tab-ascd")
        page2.wait_for_timeout(2500)

        # Trigger high-frequency WebSocket stress to show real-time stream
        try:
            page2.click("#ascd-btn-stress")
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("Stress click skipped: %s", exc)
        page2.wait_for_timeout(2000)

        # Interacting with Deck 1: The Forge (DAG, WebGL, Lean 4 Tribunal)
        print("  -> Interacting with Deck 1: The Forge (DAG & Lean 4 Prover)...")
        page2.evaluate("window.scrollBy({ top: 250, behavior: 'smooth' });")
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
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("DAG drag skipped: %s", exc)
        page2.wait_for_timeout(2000)

        # Click Prove on Lean 4 Tribunal
        try:
            btn_prove = page2.locator("button:has-text('Prove (Remove sorry)')")
            if btn_prove.is_visible():
                btn_prove.click()
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("Prove click skipped: %s", exc)
        page2.wait_for_timeout(2500)

        # Interacting with Deck 2: Proving Grounds (Heatmap & Diff Slider)
        print("  -> Interacting with Deck 2: Proving Grounds (Heatmap & Diff Slider)...")
        page2.click("#btn-deck-proving")
        page2.wait_for_timeout(2500)

        # Move diff slider back and forth
        try:
            slider_bar = page2.locator("#ascd-diff-slider")
            if slider_bar.is_visible():
                sbox = slider_bar.bounding_box()
                if sbox:
                    page2.mouse.move(sbox["x"], sbox["y"] + 50)
                    page2.mouse.down()
                    page2.mouse.move(sbox["x"] - 100, sbox["y"] + 50, steps=12)
                    page2.wait_for_timeout(800)
                    page2.mouse.move(sbox["x"] + 100, sbox["y"] + 50, steps=12)
                    page2.mouse.up()
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("Diff slider move skipped: %s", exc)
        page2.wait_for_timeout(2000)

        # Interacting with Deck 3: Engine Room
        print("  -> Interacting with Deck 3: Engine Room (RL Tinder & Context Treemap)...")
        page2.click("#btn-deck-engine")
        page2.wait_for_timeout(2500)

        # Click RL Tinder Accept
        try:
            btn_accept = page2.locator("button:has-text('Accept (Right)')")
            if btn_accept.is_visible():
                btn_accept.click()
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("RL Tinder accept skipped: %s", exc)
        page2.wait_for_timeout(2000)

        # Open God Mode overlay & show steering
        print("  -> Triggering God Mode Emergency Halt & Swarm Steering...")
        try:
            page2.click("#ascd-btn-halt")
            page2.wait_for_timeout(3000)
            page2.evaluate("window.resumeSwarmWithoutSteering();")
        except Exception:
            page2.evaluate("window.closeGodModeOverlay();")
        page2.wait_for_timeout(2000)

        ctx2.close()

        # -------------------------------------------------------------
        # Part 3: Live ASCD Swarm Command Deck on Mobile (375x812)
        # Duration: ~30 seconds
        # -------------------------------------------------------------
        print("[3/5] Recording Part 3: ASCD Swarm Command Deck on Mobile Viewport (30s)...")
        ctx3 = browser.new_context(
            viewport={"width": 375, "height": 812},
            is_mobile=True,
            has_touch=True,
            record_video_dir=str(rec_web_mobile_dir),
            record_video_size={"width": 375, "height": 812},
        )
        page3 = ctx3.new_page()
        page3.goto(f"{WEB_URL}/#ascd")
        page3.wait_for_timeout(2500)

        # Scroll mobile HUD
        print("  -> Scrolling mobile SCADA HUD cards...")
        page3.evaluate("window.scrollBy({ top: 300, behavior: 'smooth' });")
        page3.wait_for_timeout(2000)

        # Switch to Deck 2 on mobile
        try:
            btn_m_prov = page3.locator("#btn-deck-proving")
            if btn_m_prov.is_visible():
                btn_m_prov.click()
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("Mobile deck proving skipped: %s", exc)
        page3.wait_for_timeout(2500)

        # Scroll down mobile Deck 2
        page3.evaluate("window.scrollBy({ top: 300, behavior: 'smooth' });")
        page3.wait_for_timeout(2000)

        # Switch to Deck 3 on mobile
        try:
            btn_m_eng = page3.locator("#btn-deck-engine")
            if btn_m_eng.is_visible():
                btn_m_eng.click()
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("Mobile deck engine skipped: %s", exc)
        page3.wait_for_timeout(2500)

        # Trigger mobile emergency halt
        try:
            btn_m_halt = page3.locator("#ascd-btn-halt")
            if btn_m_halt.is_visible():
                btn_m_halt.click()
                page3.wait_for_timeout(2500)
                page3.evaluate("window.resumeSwarmWithoutSteering();")
        except Exception as exc:
            import logging
            logging.getLogger("VideoRecorder").debug("Mobile halt skipped: %s", exc)
        page3.wait_for_timeout(2000)

        ctx3.close()

        # -------------------------------------------------------------
        # Part 4: Presentation Deck (Act 3: Peer Review & 3 Papers)
        # Duration: ~30 seconds
        # -------------------------------------------------------------
        print("[4/5] Recording Part 4: Gemini 3.1 Pro Peer Review & 3 Papers (30s)...")
        ctx4 = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(rec_pres2_dir),
            record_video_size={"width": 1920, "height": 1080},
        )
        page4 = ctx4.new_page()
        page4.goto(f"file://{PRESENTATION_HTML.resolve()}")
        page4.wait_for_timeout(1000)

        for s in range(110, 151, 2):
            page4.evaluate(f"setVideoTime({s})")
            page4.wait_for_timeout(500)

        ctx4.close()
        browser.close()

    video1 = next(rec_pres1_dir.glob("*.webm"))
    video2 = next(rec_web_desktop_dir.glob("*.webm"))
    video3 = next(rec_web_mobile_dir.glob("*.webm"))
    video4 = next(rec_pres2_dir.glob("*.webm"))

    print(f"Recorded video segments:")
    print(f"  Seg1 (Pres 1): {video1.name}")
    print(f"  Seg2 (Desktop Web): {video2.name}")
    print(f"  Seg3 (Mobile Web): {video3.name}")
    print(f"  Seg4 (Pres 2 / Papers): {video4.name}")

    return video1, video2, video3, video4


def get_video_duration(video_path: Path) -> float:
    """Extracts duration in seconds using ffmpeg -i."""
    res = subprocess.run(["ffmpeg", "-i", str(video_path)], capture_output=True, text=True)
    for line in (res.stdout + res.stderr).splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 1.0


def build_full_video(video1: Path, video2: Path, video3: Path, video4: Path, output_file: Path) -> Path:
    """Combines, rescales (handling 1920x1080 desktop and 375x812 mobile centered), and transcodes to 180s MP4."""
    import numpy as np
    import wave

    print("[5/5] Transcoding and compiling full 180-second HD video with FFmpeg...")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        seg1 = tmp_path / "seg1.mp4"
        seg2 = tmp_path / "seg2.mp4"
        seg3 = tmp_path / "seg3.mp4"
        seg4 = tmp_path / "seg4.mp4"
        concat_txt = tmp_path / "concat.txt"
        audio_wav = tmp_path / "ambient_synth.wav"

        d1 = get_video_duration(video1)
        d2 = get_video_duration(video2)
        d3 = get_video_duration(video3)
        d4 = get_video_duration(video4)
        print(f"  Raw durations: Seg1={d1:.2f}s, Seg2={d2:.2f}s, Seg3={d3:.2f}s, Seg4={d4:.2f}s")

        # Target durations: Seg1: 60s, Seg2: 55s, Seg3: 35s, Seg4: 30s -> Total: 180s
        target_d1 = 60.0
        target_d2 = 55.0
        target_d3 = 35.0
        target_d4 = 30.0

        scale_filter_1080p = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30"
        # For mobile: scale height to 1080 and pad to 1920 width with sleek dark background
        scale_filter_mobile = "scale=499:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=#030712,fps=30"

        # Seg 1: Lit Review & CLI (60s)
        s1 = target_d1 / max(0.5, d1)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video1),
            "-vf", f"setpts={s1}*PTS,{scale_filter_1080p}",
            "-t", str(target_d1),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg1)
        ], check=True)

        # Seg 2: Desktop Web ASCD (55s)
        s2 = target_d2 / max(0.5, d2)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video2),
            "-vf", f"setpts={s2}*PTS,{scale_filter_1080p}",
            "-t", str(target_d2),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg2)
        ], check=True)

        # Seg 3: Mobile Web ASCD (35s)
        s3 = target_d3 / max(0.5, d3)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video3),
            "-vf", f"setpts={s3}*PTS,{scale_filter_mobile}",
            "-t", str(target_d3),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg3)
        ], check=True)

        # Seg 4: Peer Review & Papers (30s)
        s4 = target_d4 / max(0.5, d4)
        subprocess.run([
            "ffmpeg", "-y", "-i", str(video4),
            "-vf", f"setpts={s4}*PTS,{scale_filter_1080p}",
            "-t", str(target_d4),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(seg4)
        ], check=True)

        # Write concat demuxer manifest
        concat_txt.write_text(
            f"file '{seg1.resolve()}'\n"
            f"file '{seg2.resolve()}'\n"
            f"file '{seg3.resolve()}'\n"
            f"file '{seg4.resolve()}'\n"
        )

        # Generate ambient futuristic audio
        print("  -> Generating atmospheric soundtrack (180s @ 44.1kHz)...")
        sr = 44100
        total_samples = int(sr * 180.0)
        t = np.linspace(0, 180.0, total_samples, endpoint=False)

        # Multi-layer ambient pad (55Hz sub-bass, 110Hz root, 165Hz fifth, 220Hz octave)
        sub = 0.25 * np.sin(2 * np.pi * 55 * t)
        root = 0.15 * np.sin(2 * np.pi * 110 * t + 0.05 * np.sin(2 * np.pi * 0.2 * t))
        fifth = 0.10 * np.sin(2 * np.pi * 165 * t)
        octave = 0.08 * np.sin(2 * np.pi * 220 * t + 0.1 * np.sin(2 * np.pi * 0.15 * t))
        shimmer = 0.04 * np.sin(2 * np.pi * 440 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.1 * t))

        audio = sub + root + fifth + octave + shimmer

        # Envelope: 3s fade-in, 3s fade-out
        fade_in = np.minimum(1.0, t / 3.0)
        fade_out = np.minimum(1.0, (180.0 - t) / 3.0)
        audio = audio * fade_in * fade_out

        # Convert to 16-bit PCM
        audio_int16 = (audio * 32767 * 0.6).astype(np.int16)
        with wave.open(str(audio_wav), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(audio_int16.tobytes())

        # Concatenate and mux audio
        cmd_final = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-i", str(audio_wav),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output_file)
        ]
        subprocess.run(cmd_final, check=True)

    print(f"✅ Full 180-second HD Video Generated: {output_file} ({output_file.stat().st_size / (1024*1024):.2f} MB)")
    return output_file


def main():
    print("=" * 80)
    print("🎬 RECORDING 3 TOP PhD MULTI-AGENT CASES DEMO VIDEO (CLI & WEB/MOBILE)")
    print("=" * 80)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        v1, v2, v3, v4 = record_playwright_sessions(tmp_path)
        out_video = build_full_video(v1, v2, v3, v4, OUTPUT_MP4)

    # Copy to artifacts directory
    artifact_copy = ARTIFACTS_DIR / "phd_3_cases_multi_agent_hardness_demo.mp4"
    shutil.copy2(out_video, artifact_copy)
    print(f"✅ Video Copied to Artifacts Directory: {artifact_copy}")

    print("\n" + "=" * 80)
    print("🎉 VIDEO RECORDING COMPLETE & READY FOR PRESENTATION")
    print("=" * 80)


if __name__ == "__main__":
    main()
