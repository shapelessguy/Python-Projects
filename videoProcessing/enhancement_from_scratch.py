import subprocess
import shutil
import os
from pathlib import Path
import subprocess
import re
import statistics
import concurrent
import concurrent.futures
import json


IMG_EXT = "png"
MAX_WORKERS = 4
FPS_MULT = 2


def convert_hms_to_seconds(time_string: str) -> float:
    """
    Converts a time string in HH:MM:SS.fractional_seconds format 
    (e.g., '02:15:19.028000000') into a total number of seconds (float).
    """
    try:
        h_str, m_str, s_f_str = time_string.split(':')
        hours = int(h_str)
        minutes = int(m_str)
        seconds_and_fraction = float(s_f_str)
        total_seconds = (hours * 3600) + (minutes * 60) + seconds_and_fraction
        
        return total_seconds
        
    except ValueError as e:
        raise ValueError(f"Invalid time string format. Expected HH:MM:SS.fraction, got '{time_string}'. Error: {e}")


def detect_scene_changes(input_file: Path, info: dict, threshold: float=0.0):
    """Runs FFmpeg's scenedetect filter, reads the output, and returns a list of detected scene cuts."""

    command = [
        'ffmpeg', '-i', str(input_file), '-filter:v', f"select='gt(scene,{threshold})' ,metadata=print", '-an', '-f', 'null',
        '-nostats', '-loglevel', 'info', '-',
    ]
    print(f"Executing command: {' '.join(command)}")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error during FFmpeg execution (check log file for details):\n{e.stderr}")
        return []
    except FileNotFoundError:
        print("Error: FFmpeg is not found. Ensure it is installed and in your system's PATH.")
        return []
    
    frame_time_pattern = re.compile(r'frame:(\d+)\s+pts:\s*(\d+)\s+pts_time:([\d.]+)')
    score_pattern = re.compile(r'lavfi\.scene_score=([\d.]+)')

    # Example:
    # video 1fps
    # in 60 seconds, there should be 61 frames
    # The total time would be (61 - 1)frames / 1fps = 60s

    all_frames_data = []
    scores = []
    total_time = info["duration"]

    try:
        current_frame_data = {}
        id_ = None
        for line in (result.stdout + result.stderr).split("\n"):
            if "pts_time" in line:
                match_ft = frame_time_pattern.search(line)
                if match_ft:
                    time_ = float(match_ft.group(3))
                    id__ = time_ / total_time * (info["n_frames"] - 1) + 1
                    id_ = int(id__ + 0.5)
                    current_frame_data = {
                        'time': time_,
                        'score': None
                    }
            elif "lavfi.scene_score" in line:
                match_ft = score_pattern.search(line)
                if match_ft:
                    current_frame_data['score'] = float(match_ft.group(1))
                    if id_ - 2 > len(all_frames_data):
                        for _ in range(len(all_frames_data), id_ - 2):
                            all_frames_data.append({'time': None, 'score': 0})
                            scores.append(0)
                    all_frames_data.append(current_frame_data)
                    scores.append(current_frame_data['score'])
        
        if id_ - 1 > len(all_frames_data):
            for _ in range(len(all_frames_data), id_ - 1):
                all_frames_data.append({'time': None, 'score': 0})
                scores.append(0)
    except Exception as e:
        print(f"Error reading or parsing log file: {e}")

    mean_value = statistics.mean(scores)
    std_dev_sample = statistics.stdev(scores)
    threshold_ = mean_value + 6 * std_dev_sample
    scene_cuts = []
    for i, x in enumerate(all_frames_data):
        if x['score'] > threshold_:
            x = {'n': i + 1, **x}
            scene_cuts.append(x)
            
    return scene_cuts   # [{'n': 2150, 'frame': 1816, 'time': 89.715, 'score': 0.368458}, ...]


def group_scenes(scene_cuts: list, info: dict, inputFrames_folder: Path):
    blocks = []
    initial_frame = 1
    for c in scene_cuts:
        blocks.append((initial_frame, c["n"]))
        initial_frame = c["n"] + 1
    if initial_frame < info["n_frames"]:
        blocks.append((initial_frame, info["n_frames"]))

    scenes_info = []
    for i, b in enumerate(blocks):
        scene_name = f"Scene_{i+1}"
        scene_folder = inputFrames_folder.joinpath(scene_name)
        scenes_info.append({"idx": i, "name": scene_name, "range": b})
        os.mkdir(scene_folder)
        for id_ in range(b[0], b[1] + 1):
            file_name = f"{id_:08d}.{IMG_EXT}"
            shutil.move(inputFrames_folder.joinpath(file_name), scene_folder.joinpath(file_name))
    return scenes_info


def ungroup_scenes(scene_paths: list, inputFrames_folder: Path, outputFrames_folder: Path):
    idx = 1
    for sp in scene_paths:
        scene_in_path, scene_out_path = sp["scene_in_path"], sp["scene_out_path"]
        for f in os.listdir(scene_out_path):
            shutil.move(scene_out_path.joinpath(f), outputFrames_folder.joinpath(f"{idx:08d}.{IMG_EXT}"))
            idx += 1
        for f in os.listdir(scene_in_path):
            shutil.move(scene_in_path.joinpath(f), inputFrames_folder.joinpath(f))
        shutil.rmtree(scene_out_path)
        shutil.rmtree(scene_in_path)


def export_subs(input_path: Path, info: dict, subs_folder: Path):
    if not os.path.exists(subs_folder):
        os.mkdir(subs_folder)
    for sub_stream, sub_info in info["sub"].items():
        for i, e in enumerate(sub_info):
            sub_code = e["sub_code"]
            file_path = subs_folder.joinpath(f"{input_path.stem}.{sub_code}.srt")
            cmd = ["ffmpeg", "-y", "-i", str(input_path), "-map", f"{sub_stream}:s:{i}", "-c:s", "copy", str(file_path)]
            subprocess.run(cmd)


def get_stream_info(input_path: Path):
    info = {"audio": {}, "sub": {}, "fps": None, "n_frames": None, "duration": None}
    cmd_probe = ["ffmpeg", "-i", str(input_path)]
    result = subprocess.run(cmd_probe, capture_output=True, text=True)
    output = result.stdout + result.stderr

    fps = None
    for line in output.splitlines():
        line = line.strip()
        if "Audio:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                regex = r"#(\d+):(\d+)\(([^)]+)\)" 
                match = re.search(regex, line)

                if match:
                    stream_index = match.group(1)
                    language_index = match.group(2)
                    language_code = match.group(3)
                    info["audio"][stream_index] = info["audio"].get(stream_index, []) + [{"language_index": language_index, "language_code": language_code}]
        elif "Subtitle:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                regex = r"#(\d+):(\d+)\(([^)]+)\)" 
                match = re.search(regex, line)

                if match:
                    stream_index = match.group(1)
                    sub_index = match.group(2)
                    sub_code = match.group(3)
                    info["sub"][stream_index] = info["sub"].get(stream_index, []) + [{"sub_index": sub_index, "sub_code": sub_code}]
        elif "Video:" in line:
            parts = line.split(":")
            if len(parts) >= 2:
                props = [x.strip() for x in ":".join(parts[3:]).split(",")]
                fps_ = [x for x in props if " fps" in x]
                if fps_ and info["fps"] is None:
                    fps = float(fps_[0].replace(" fps", ""))
                    info["fps"] = fps
        elif "Duration" in line:
            if info["duration"] is None:
                hms = ":".join(line.split(":")[1:]).split(",")[0].strip()
                print(hms)
                info["duration"] = convert_hms_to_seconds(hms)
    if not fps:
        raise Exception("No fps property found for video stream.")
    return info


def process_scene(scene_info: dict, inputFrames_folder: Path, outputFrames_folder: Path, rife_exe: Path):
    os.mkdir(str(outputFrames_folder.joinpath(scene_info['name'])))
    scene_in_path = inputFrames_folder.joinpath(scene_info['name'])
    scene_out_path = outputFrames_folder.joinpath(scene_info['name'])
    n_frames = scene_info['range'][1] - scene_info['range'][0] + 1
    cmd = [rife_exe, "-i", str(scene_in_path), "-o", str(scene_out_path), "-m", "rife-v4.6", "-n", f"{n_frames * FPS_MULT}", "-j", "1:2:1"]
    print(f"Processing {scene_info['name']}")
    subprocess.run(cmd)
    return {"idx": scene_info["idx"], "scene_in_path": scene_in_path, "scene_out_path": scene_out_path}


def interpolate(input_video: str):
    if not os.path.exists(input_video):
        print(f"File not found: {input_video}")
        return
    
    input_path = Path(input_video)
    folder_path = input_path.parent
    rife_folder = Path(__file__).parent.joinpath("rife-ncnn-vulkan-20221029-windows")
    rife_exe = rife_folder.joinpath("rife-ncnn-vulkan.exe")
    build_path = folder_path.joinpath("build")
    scene_cuts_path = build_path.joinpath("scene_cuts.json")
    inputFrames_folder = build_path.joinpath("input_frames")
    outputFrames_folder = build_path.joinpath("output_frames")
    subs_folder = build_path.joinpath("subtitles")
    vfi_folder = folder_path.joinpath("VFI")
    output_path = vfi_folder.joinpath(f"{input_path.stem}.mkv")
    audio_file = f"audio.mka"
    audio_path = build_path / audio_file
    info = get_stream_info(input_path)

    if os.path.exists(build_path):
        shutil.rmtree(build_path)
    os.mkdir(str(build_path))
    if not os.path.exists(vfi_folder):
        os.mkdir(str(vfi_folder))

    # -------------------------- Extraction of subtitles ------------------------------------------------------------------
    export_subs(input_path, info, subs_folder)
    if os.path.exists(subs_folder):
        out_subs_folder = vfi_folder.joinpath("subtitles")
        if not os.path.exists(out_subs_folder):
            os.mkdir(out_subs_folder)
        shutil.copytree(subs_folder, out_subs_folder, dirs_exist_ok=True)

    # # -------------------------- Extraction of audio streams --------------------------------------------------------------
    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-map", f"0:a", "-map", "0:s", "-c", "copy", str(audio_path)]
    print(f"Extracting audio -> {audio_path.name}")
    subprocess.run(cmd)

    # # -------------------------- Extraction of video frames ---------------------------------------------------------------
    if not inputFrames_folder.exists():
        os.mkdir(str(inputFrames_folder))
    video_frame_path = f"%08d.{IMG_EXT}"
    out_file = inputFrames_folder / video_frame_path
    cmd = ["ffmpeg", "-y", "-i", str(input_path), str(out_file)]
    print(f"Extracting frames -> {out_file.name}")
    subprocess.run(cmd)

    # -------------------------- Interpolation -----------------------------------------------------------------------------

    info["n_frames"] = len(os.listdir(inputFrames_folder))
    scene_cuts = detect_scene_changes(input_path, info)
    with open(scene_cuts_path, "w") as file:
        json.dump(scene_cuts, file, indent=4)
    scenes_info = group_scenes(scene_cuts, info, inputFrames_folder)
    
    if not outputFrames_folder.exists():
        os.mkdir(str(outputFrames_folder))
    
    scene_paths = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(process_scene, scene_info, inputFrames_folder, outputFrames_folder, rife_exe) for scene_info in scenes_info]
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
                scene_paths.append(result)
            except Exception as exc:
                print(f'Scene generation failed: {exc}')
    scene_paths.sort(key=lambda x: x["idx"])
    ungroup_scenes(scene_paths, inputFrames_folder, outputFrames_folder)

    # Re-assembling
    video_path = outputFrames_folder.joinpath(f"%08d.{IMG_EXT}")
    final_cmd = ["ffmpeg", "-y", "-framerate", str(info["fps"] * FPS_MULT), "-i", str(video_path), "-i", str(audio_path)]
    final_cmd += [
        "-crf", "20",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-map", "0:v:0",
        "-map", "1:a",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-fflags", "+genpts",
        "-avoid_negative_ts", "make_zero"
    ]
    final_cmd.append(output_path)
    print(f"Finalizing video")
    subprocess.run(final_cmd)


def main():
    interpolate(r"D:\test\test.mkv")
    # interpolate(r"D:\test\A Beautiful Mind.mkv")


if __name__ == "__main__":
    main()
