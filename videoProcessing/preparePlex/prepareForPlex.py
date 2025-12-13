import sys
import os
import shutil
import traceback
import time
from pathlib import Path
from datetime import datetime
from colorama import init, Fore, Style
init(autoreset=True)
from utils import *
from process_movie import *


def generate_recap(info):
    msg = f"\n ----------------------------------------\n"
    msg += f"|                RECAP                   |\n"
    msg += f"|----------------------------------------\n"
    msg += f"|  Title: {info.video_path.stem}\n"
    msg += f"|----------------------------------------\n"

    for vs in info.get_video_tracks():
        video_attr = {"codec": vs["codec_name"], "pixel_dim": f'{vs["width"]}x{vs["height"]}'}
        msg += f"|  Video track {vs['index']}:\n"
        for k, v in video_attr.items():
            msg += f"|     {k}: {v}\n"
    msg += f"|----------------------------------------\n"
    for aus in info.get_audio_tracks():
        if aus["tags"]["language"]:
            offsym = f"+{aus['offset']}" if aus["offset"] > 0 else (f"-{aus['offset']}" if aus["offset"] < 0 else "NO")
            sub_attr = {"codec": aus["codec_name"], "language": aus["tags"]["language"], "title": aus["tags"]["title"], "offset": offsym}
            msg += f"|  Audio track {aus['index']}:\n"
            for k, v in sub_attr.items():
                msg += f"|     {k}: {v}\n"
    msg += f"|----------------------------------------\n"
    if (len(info.get_sub_tracks())):
        for ss in info.get_sub_tracks():
            if ss["tags"].get("language", ""):
                offsym = f"+{ss['offset']}" if ss["offset"] > 0 else (f"-{ss['offset']}" if ss["offset"] < 0 else "NO")
                sub_attr = {"codec": ss["codec_name"], "language": ss["tags"]["language"], "title": ss["tags"]["title"], "offset": offsym}
                msg += f"|  Subtitle {ss['index']}:\n"
                for k, v in sub_attr.items():
                    msg += f"|     {k}: {v}\n"
    else:
        msg += f"|  {Fore.LIGHTRED_EX}NO SUBTITLES{Fore.LIGHTCYAN_EX}\n"
    msg += f"|----------------------------------------\n"
    if len([x for x in info.get_external_subs() if x["tags"]["language"] is not None]):
        for ss in info.get_external_subs():
            if ss["tags"].get("language", ""):
                sub_attr = {"language": ss["tags"]["language"], "title": ss["tags"]["title"]}
                msg += f"|  Subtitle {ss.get('index', 'extra')}:\n"
                for k, v in sub_attr.items():
                    msg += f"|     {k}: {v}\n"
    else:
        msg += f"|  {Fore.LIGHTRED_EX}NO EXTERNAL SUBTITLES{Fore.LIGHTCYAN_EX}\n"
    msg += f"|----------------------------------------\n"

    msg += f"\n\nPress:\n"
    msg += f"\t- 'm' to mark it as to be remuxed\n"
    msg += f"\t- 'r' to directly mark it as READY\n"
    if len([x for x in info.get_audio_tracks() if x["tags"]["language"] is not None]):
        msg += f"\t- 'audioffset' to sync audio\n"
    if len([x for x in (info.get_sub_tracks() + info.get_external_subs()) if x["tags"]["language"] is not None]):
        msg += f"\t- 'suboffset' to sync internal subtitles\n"
    msg += f"\t- 'o' to open the video folder via explorer\n"
    msg += f"\t- 't' to test the final movie\n"
    msg += f"\t- 'trash' to move the movie into trash\n"
    msg += f"\t- ENTER to repeat sub-scanning\n"
    return msg


class Folder:
    def __init__(self, path: Path):
        self.path = path
        self.sub_folders: list[Folder] = []
        self.video_paths = []
        self.video_path: Path = None
        self.subs_paths = []
        self.others_paths = []
        self.get_paths()
    
    def get_paths(self):
        files_and_folders = os.listdir(self.path)
        files = [x for x in files_and_folders if self.path.joinpath(x).is_file()]
        self.video_paths = [self.path.joinpath(x) for x in files if x.split(".")[-1] in supported_video_ext]
        if len(self.video_paths):
            self.video_path = self.video_paths[0]
        self.subs_paths = [self.path.joinpath(x) for x in files if x.split(".")[-1] in supported_external_subs_ext]
        self.other_paths = [self.path.joinpath(x) for x in files if x.split(".")[-1] not in (supported_video_ext + supported_external_subs_ext)]
        self.other_paths = [x for x in self.other_paths if x.stem not in ["desktop"]]
        self.sub_folders = [Folder(self.path.joinpath(x)) for x in files_and_folders
                            if not self.path.joinpath(x).is_file() and x not in [TRASH_FOLDER_NAME, WORKING_FOLDER_NAME, READY_FOLDER_NAME]]
    
    def is_valid(self):
        return len(self.video_paths) == 1
    
    def to_working_dir(self, working_dir_path: Path, trash_path: Path):
        new_folder_path = working_dir_path.joinpath(self.path.stem)
        os.mkdir(new_folder_path)
        move(self.video_path, new_folder_path.joinpath(self.video_path.stem + self.video_path.suffix))
        for sub in self.subs_paths:
            move(sub, new_folder_path.joinpath(sub.stem + sub.suffix))
        if not len(os.listdir(self.path)):
            os.rmdir(self.path)
        else:
            move(self.path, trash_path.joinpath(self.path.stem))
    
    def process(self, move_to: Path, trash_path: Path):
        if self.is_valid():
            print(f"\n\n{Fore.LIGHTYELLOW_EX}Working on folder:  < {self.video_path.parent.stem} >{Style.RESET_ALL}")
            info = get_stream_info(self.video_path)

            continue_working = True
            skip_muxing = False
            fullname = get_movie_name(info)
            while continue_working:
                continue_working = False
                while True:
                    info = process_movie(info, fullname)
                    self.path = info.video_path.parent
                    self.video_path = info.video_path
                    if info.to_trash:
                        move(self.video_path.parent, trash_path.joinpath(self.path.stem))
                        return
                    
                    feedback = None
                    repeat = True
                    while feedback != "":
                        skip_prompt = ["t"]
                        feedback = print_console(generate_recap(info), Fore.LIGHTCYAN_EX).replace("\n", "").strip().lower() if feedback not in skip_prompt else input()
                        if feedback == "":
                            self.get_paths()
                            break
                        elif feedback == "m":
                            repeat = False
                            break
                        elif feedback == "r":
                            repeat = False
                            skip_muxing = True
                            break
                        elif feedback == "o":
                            os.startfile(self.video_path.parent)
                        elif feedback == "t":
                            open_video(self.video_path)
                        elif feedback == "audioffset" and len([x for x in info.get_audio_tracks() if x["tags"]["language"] is not None]):
                            offset_interface([x for x in info.get_audio_tracks() if x["tags"]["language"] is not None], "AUDIO")
                        elif feedback == "suboffset" and len([x for x in (info.get_sub_tracks() + info.get_external_subs()) if x["tags"]["language"] is not None]):
                            offset_interface([x for x in (info.get_sub_tracks()) if x["tags"]["language"] is not None], "SUBTITLE")
                            offset_interface([x for x in (info.get_external_subs()) if x["tags"]["language"] is not None], "EXT SUBTITLE", True)
                        elif feedback == "trash":
                            move(self.video_path.parent, trash_path.joinpath(self.path.stem))
                            return
                    if not repeat:
                        break
                
                if not skip_muxing:
                    result = remux(info)
                    if not result:
                        feedback = print_console("Press 'y' if you want to move the working folder into the trash ", Fore.LIGHTCYAN_EX).replace("\n", "").strip().lower()
                        if feedback == "y":
                            move(self.path, trash_path.joinpath(self.path.stem))
                        return
                for sub in info.get_external_subs():
                    if not sub["tags"]["language"]:
                        safe_remove_file(sub["path"])
                try:
                    msg = "Press 't' to test the new file or 'w' to continue working on it: "
                    while not skip_muxing:
                        feedback = print_console(msg, Fore.LIGHTYELLOW_EX).replace("\n", "").strip().lower()
                        if feedback == "t":
                            open_video(info.video_path)
                        elif feedback == "w":
                            continue_working = True
                            break
                        else:
                            break
                    if not continue_working:
                        to_path = move_to.joinpath(info.video_path.parent.stem)
                        if to_path.exists():
                            print(f"{Fore.LIGHTYELLOW_EX}   Folder {to_path} already exists. Overwriting now.{Style.RESET_ALL}")
                            shutil.rmtree(to_path, onexc=remove_readonly)
                        move(info.video_path.parent, to_path)
                        return
                except:
                    print(f"Error while moving folder from working dir to ready dir:\n{traceback.format_exc()}")
                    return


def clean_dirs(path):
    sub_folders = [path.joinpath(x) for x in os.listdir(path)]
    if not sub_folders:
        os.rmdir(path)
    else:
        for f in sub_folders:
            if not len(os.listdir(f)):
                os.rmdir(f)
        if not len(os.listdir(path)):
            os.rmdir(path)


file_uploaded = 0
def prepare_plex(purgatory_path):
    global file_uploaded
    initialize_sftp()

    while purgatory_path != Path(PURGATORY_FOLDER):
        if purgatory_path == purgatory_path.parent:
            break
        purgatory_path = Path(purgatory_path.parent)

    if purgatory_path != Path(PURGATORY_FOLDER):
        print_console(f"You must be on the predefined location: {str(PURGATORY_FOLDER)}\n\nPress Enter to exit", Fore.RED)
        return

    # Setting up the environment
    main_folder = Folder(purgatory_path)
    trash_path = purgatory_path.joinpath(TRASH_FOLDER_NAME)
    cur_trash_path = trash_path.joinpath(datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    working_dir_path = purgatory_path.joinpath(WORKING_FOLDER_NAME)
    ready_dir_path = purgatory_path.joinpath(READY_FOLDER_NAME)
    for folder in [trash_path, cur_trash_path, working_dir_path, ready_dir_path]:
        if not folder.exists():
            os.mkdir(folder)
    
    try:
        # Handling top-most folders
        invalid_folders: list[Folder] = []
        for folder in main_folder.sub_folders:
            if folder.is_valid():
                folder.to_working_dir(working_dir_path, trash_path=cur_trash_path)
            else:
                invalid_folders.append(folder)

        # Handling top-most files
        for file in main_folder.video_paths:
            new_folder_path = working_dir_path.joinpath(file.stem)
            os.mkdir(new_folder_path)
            move(file, new_folder_path.joinpath(file.stem + file.suffix))

        # Sharing info about skipped folders/files
        if len(invalid_folders):
            msg = f"The following containers have been skipped because invalid folders:\n"
            for f in invalid_folders:
                msg += f"\t- {f.path.stem}\n"
            msg += "\nPress Enter to continue..."
            print_console(msg, Fore.LIGHTYELLOW_EX)
        if len(main_folder.other_paths):
            msg = f"The following files have been skipped because invalid video:\n"
            for f in main_folder.other_paths:
                msg += f"\t- {f.stem}\n"
            msg += "\nPress Enter to continue..."
            print_console(msg, Fore.LIGHTYELLOW_EX)
        
        # The structure of the working_path is fixed at this point
        working_folder = Folder(working_dir_path)
        for folder in working_folder.sub_folders:
            folder.process(move_to=ready_dir_path, trash_path=trash_path)
    
    except Exception:
        print(traceback.format_exc())

    clean_dirs(working_dir_path)
    clean_dirs(trash_path)
    
    ready_folder = Folder(ready_dir_path)
    if len(ready_folder.sub_folders):
        print_console(f"Press Enter to send files to {FINAL_MOVIE_HOLDER_PATH}...", Fore.YELLOW)

        total_size = 0
        total_n = len(ready_folder.sub_folders)
        for folder in ready_folder.sub_folders:
            total_size += os.path.getsize(folder.video_path)

        cur_uploaded = 0
        init_time = time.time()
        for i, folder in enumerate(ready_folder.sub_folders):
            file_uploaded = 0

            def progress(currently_copied, current_file_size):
                global file_uploaded
                et = time.time() - init_time
                file_uploaded = currently_copied
                cur_percentage = currently_copied/current_file_size*100
                tot_percentage = (currently_copied + cur_uploaded)/total_size*100

                cur_percentage = 100 if cur_percentage > 100 else  cur_percentage
                tot_percentage = 100 if tot_percentage > 100 else  tot_percentage
                eta = et * 100 / tot_percentage - et
                eta = 0 if eta < 0 else seconds_to_mmss(int(eta))
                
                progress_msg = f"{i+1}/{total_n} - {cur_percentage:.2f}% Moving {folder.path} into {FINAL_MOVIE_HOLDER_PATH}... "
                line = f"{progress_msg} STATUS {tot_percentage:.2f}%  ETA {eta}"
                print(f"\r{line:<180}", end="", flush=True)

            if str(folder.path).split(":")[0] == FINAL_MOVIE_HOLDER_PATH.split(":")[0]:
                move(folder.path, f"{FINAL_MOVIE_HOLDER_PATH}/{folder.path.stem + folder.path.suffix}")
            else:
                copy_folder_with_progress(folder.path, f"{FINAL_MOVIE_HOLDER_PATH}/{folder.path.stem + folder.path.suffix}", progress)
                cur_uploaded += file_uploaded
                if file_uploaded == 0:
                    break
    
    clean_dirs(ready_dir_path)
    print(f"\n{Fore.GREEN}Preparation to Plex completed.{Style.RESET_ALL}")
    print_console("Press Enter to exit")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_path = Path(sys.argv[1].replace("\n", ""))
        if not os.path.exists(VLC_PATH):
            print_console("VLC not found!\n\nPress Enter to exit", Fore.RED)
        else:
            prepare_plex(target_path)
    else:
        print_console("No path target\n\nPress Enter to exit", Fore.RED)
