"""
Core clipping logic — adapted from youtube_clipper.py for web use.
All blocking I/O; run inside a ThreadPoolExecutor.
"""

import os
import re
import json
import shutil
import subprocess
from typing import Callable

import anthropic

YTDLP_PATH = shutil.which("yt-dlp") or "/opt/homebrew/bin/yt-dlp"
MAX_CLIPS = 5

Progress = Callable[[str, int], None]  # (message, percent 0-100)


def _ytdlp(args: list, silent: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run([YTDLP_PATH] + args, capture_output=True, text=True)


def download_video_and_transcript(youtube_url: str, work_dir: str, progress: Progress):
    os.makedirs(work_dir, exist_ok=True)

    progress("Đang tải phụ đề / transcript…", 5)
    _ytdlp([
        "--write-auto-sub", "--write-sub",
        "--sub-lang", "vi,en,vi-VN",
        "--sub-format", "json3/vtt/best",
        "--skip-download",
        "--output", os.path.join(work_dir, "transcript"),
        youtube_url,
    ])

    progress("Đang tải video (có thể mất vài phút)…", 15)
    res = _ytdlp([
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--output", os.path.join(work_dir, "video.%(ext)s"),
        "--no-playlist",
        youtube_url,
    ])
    if res.returncode != 0 and not any(f.startswith("video.") for f in os.listdir(work_dir)):
        raise RuntimeError(f"yt-dlp lỗi (code {res.returncode}):\nSTDOUT: {res.stdout[-500:]}\nSTDERR: {res.stderr[-500:]}")

    all_files = os.listdir(work_dir) if os.path.exists(work_dir) else []
    video_file = next(
        (os.path.join(work_dir, f) for f in all_files
         if f.startswith("video.")),
        None,
    )
    if not video_file:
        raise FileNotFoundError(f"Không tải được video. Files trong thư mục: {all_files}")

    transcript_file = next(
        (os.path.join(work_dir, f) for f in os.listdir(work_dir)
         if f.startswith("transcript") and f.endswith((".json3", ".vtt"))),
        None,
    )
    progress("Tải xong!", 30)
    return video_file, transcript_file


def parse_transcript(transcript_file: str) -> str:
    if not transcript_file or not os.path.exists(transcript_file):
        return ""
    with open(transcript_file, encoding="utf-8") as f:
        content = f.read()

    if transcript_file.endswith(".json3"):
        data = json.loads(content)
        lines = []
        for event in data.get("events", []):
            if "segs" not in event:
                continue
            start_sec = event.get("tStartMs", 0) / 1000
            text = "".join(seg.get("utf8", "") for seg in event["segs"]).strip()
            if text and text != "\n":
                m, s = int(start_sec // 60), int(start_sec % 60)
                lines.append(f"[{m:02d}:{s:02d}] {text}")
        return "\n".join(lines)

    if transcript_file.endswith(".vtt"):
        lines = []
        for block in content.split("\n\n"):
            tm = re.search(r"(\d+):(\d+):(\d+\.\d+) -->", block)
            if tm:
                h, m, s = int(tm.group(1)), int(tm.group(2)), float(tm.group(3))
                m += h * 60
            else:
                tm = re.search(r"(\d+):(\d+\.\d+) -->", block)
                if not tm:
                    continue
                m, s = int(tm.group(1)), float(tm.group(2))
            text = re.sub(r"<[^>]+>", "", "\n".join(block.split("\n")[1:])).strip()
            if text:
                lines.append(f"[{int(m):02d}:{int(s):02d}] {text}")
        return "\n".join(lines)

    return ""


def analyze_with_claude(
    transcript_text: str,
    video_duration: float,
    min_dur: int,
    max_dur: int,
    api_key: str,
    progress: Progress,
) -> list[dict]:
    progress("Claude đang phân tích nội dung…", 40)
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Bạn là chuyên gia reup video TikTok/Shorts. Phân tích transcript sau và chọn ra {MAX_CLIPS} đoạn HAY NHẤT để cắt thành clip ngắn viral.

TRANSCRIPT (có timecode [MM:SS]):
{transcript_text[:8000]}

Tổng thời lượng video: {int(video_duration // 60)}:{int(video_duration % 60):02d}

══════════════════════════════════════
TIÊU CHÍ ƯU TIÊN (càng đủ càng tốt):
══════════════════════════════════════
1. Hook 0–3 giây đầu: tạo câu hỏi hoặc yếu tố bất ngờ ngay lập tức
2. Có ít nhất 1 khoảnh khắc "aha" — thông tin người xem chưa biết
3. Tự đứng được — không cần xem phần trước mới hiểu
4. Người xem thấy ảnh hưởng đến họ (tiền bạc, tương lai, an toàn, cảm xúc)
5. Có thể hình ảnh hóa — con số cụ thể, so sánh rõ ràng, địa điểm thực tế

Ưu tiên đoạn đủ cả 5. Nếu không có đủ, chọn đoạn đạt ít nhất 3/5 tiêu chí và có tiêu chí 3 (tự đứng được).

══════════════════════════════════════
TỰ ĐỘNG LOẠI (không chấm điểm):
══════════════════════════════════════
- Quảng cáo sản phẩm/dịch vụ
- Kêu gọi subscribe / like / follow / share
- Chào hỏi đầu video / kết thúc xã giao

QUAN TRỌNG: Bắt buộc phải trả về đúng {MAX_CLIPS} clip. Nếu không đủ clip tốt, chọn các đoạn tốt nhất còn lại.

Độ dài mỗi clip PHẢI trong khoảng {min_dur}–{max_dur} giây.

Trả về JSON thuần (không markdown):
{{
  "clips": [
    {{
      "id": 1,
      "start_time": 45.0,
      "end_time": 90.0,
      "title": "Tiêu đề clip hấp dẫn cho TikTok/Shorts",
      "hashtags": "#trending #viral #shorts",
      "reason": "Lý do chọn đoạn này",
      "hook": "Câu hook mở đầu trong 0–3 giây đầu"
    }}
  ]
}}

start_time và end_time là số giây (float). Đảm bảo end_time - start_time nằm trong [{min_dur}, {max_dur}]."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    result_text = response.content[0].text.strip()

    # Strip markdown code fences if present
    result_text = re.sub(r"^```(?:json)?\s*", "", result_text)
    result_text = re.sub(r"\s*```$", "", result_text)

    try:
        result = json.loads(result_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", result_text, re.DOTALL)
        if not match:
            raise ValueError(f"Claude không trả về JSON hợp lệ:\n{result_text[:300]}")
        try:
            result = json.loads(match.group())
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON lỗi: {e}\nNội dung: {match.group()[:300]}")

    clips = result.get("clips", [])
    if not clips:
        raise ValueError(f"Claude trả về 0 clip. Raw response:\n{result_text[:500]}")
    progress(f"Claude chọn được {len(clips)} đoạn hay", 55)
    return clips


def get_video_duration(video_file: str) -> float:
    res = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_file],
        capture_output=True, text=True,
    )
    return float(res.stdout.strip())


def cut_clips(
    video_file: str,
    clips: list[dict],
    output_dir: str,
    progress: Progress,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    total_dur = get_video_duration(video_file)
    results = []

    for i, clip_info in enumerate(clips):
        pct = 55 + int((i / len(clips)) * 40)
        title = clip_info.get("title", f"Clip {clip_info['id']}")
        progress(f"Đang cắt: {title}", pct)

        start = max(0.0, float(clip_info["start_time"]))
        end = min(total_dur, float(clip_info["end_time"]))
        duration = end - start
        if duration < 10:
            continue

        safe = "".join(c for c in title if c.isalnum() or c in " _-")[:40].strip()
        filename = f"clip_{clip_info['id']:02d}_{safe}.mp4"
        out_path = os.path.join(output_dir, filename)

        res = subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(start), "-to", str(end),
            "-i", video_file,
            "-c:v", "libx264", "-c:a", "aac",
            "-movflags", "+faststart",
            out_path,
        ], capture_output=True, text=True)

        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg lỗi clip {clip_info['id']}: {res.stderr[-300:]}")
        if res.returncode == 0:
            results.append({
                "clip_number": clip_info["id"],
                "title": title,
                "hashtags": clip_info.get("hashtags", ""),
                "hook": clip_info.get("hook", ""),
                "reason": clip_info.get("reason", ""),
                "filename": filename,
                "duration": round(duration),
                "path": out_path,
            })

    progress("Hoàn thành!", 100)
    return results


def run_job(
    youtube_url: str,
    min_dur: int,
    max_dur: int,
    work_dir: str,
    output_dir: str,
    api_key: str,
    progress: Progress,
) -> list[dict]:
    """Entry point called from background thread."""
    video_file, transcript_file = download_video_and_transcript(
        youtube_url, work_dir, progress
    )
    transcript_text = parse_transcript(transcript_file)
    if not transcript_text:
        transcript_text = "Video không có transcript. Hãy chọn các mốc thời gian phân bổ đều."

    duration = get_video_duration(video_file)
    clips_meta = analyze_with_claude(
        transcript_text, duration, min_dur, max_dur, api_key, progress
    )
    results = cut_clips(video_file, clips_meta, output_dir, progress)

    # Clean up working directory (keep only clips)
    shutil.rmtree(work_dir, ignore_errors=True)
    return results
