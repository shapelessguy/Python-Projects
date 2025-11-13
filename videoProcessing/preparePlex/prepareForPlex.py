import sys
import os
from pathlib import Path
import shutil
import traceback
from datetime import datetime
from colorama import init, Fore, Style
init(autoreset=True)
from utils import *
from process_movie import *


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
        self.sub_folders = [Folder(self.path.joinpath(x)) for x in files_and_folders
                            if not self.path.joinpath(x).is_file() and x not in [TRASH_FOLDER_NAME, WORKING_FOLDER_NAME, READY_FOLDER_NAME]]
    
    def is_valid(self):
        return len(self.video_paths) == 1
    
    def to_working_dir(self, working_dir_path: Path, trash_path: Path):
        new_folder_path = working_dir_path.joinpath(self.path.stem)
        os.mkdir(new_folder_path)
        shutil.move(self.video_path, new_folder_path.joinpath(self.video_path.stem + self.video_path.suffix))
        for sub in self.subs_paths:
            shutil.move(sub, new_folder_path.joinpath(sub.stem + sub.suffix))
        if not len(os.listdir(self.path)):
            os.rmdir(self.path)
        else:
            shutil.move(self.path, trash_path.joinpath(self.path.stem))
        
    
    def process(self, move_to: Path):
        if self.is_valid():
            info = get_stream_info(self.video_path)

            while True:
                new_video_path, info = process_movie(info, self.video_path)
                self.path = new_video_path.parent
                self.video_path = new_video_path

                msg = f"\n ----------------------------------------\n"
                msg += f"|                RECAP                   |\n"
                msg += f"|----------------------------------------\n"
                msg += f"|  Title: {new_video_path.stem}\n"
                msg += f"|----------------------------------------\n"

                for vs in info.get_video_tracks():
                    video_attr = {"codec": vs["codec_name"], "pixel_dim": f'{vs["width"]}x{vs["height"]}'}
                    msg += f"|  Video track {vs['index']}:\n"
                    for k, v in video_attr.items():
                        msg += f"|     {k}: {v}\n"
                msg += f"|----------------------------------------\n"
                for aus in info.get_audio_tracks():
                    audio_attr = {"codec": aus["codec_name"]}
                    msg += f"|  Audio track {aus['index']}:\n"
                    for k, v in audio_attr.items():
                        msg += f"|     {k}: {v}\n"
                msg += f"|----------------------------------------\n"
                if (len(info.get_sub_tracks())):
                    for ss in info.get_sub_tracks():
                        if ss["tags"].get("language", ""):
                            ss["tags"]["language"] = ss["tags"].get("language", "")
                            ss["tags"]["title"] = ss["tags"].get("title", "")
                            sub_attr = {"codec": ss["codec_name"], "language": ss["tags"]["language"], "title": ss["tags"]["title"]}
                            msg += f"|  Subtitle {ss['index']}:\n"
                            for k, v in sub_attr.items():
                                msg += f"|     {k}: {v}\n"
                else:
                    msg += f"|  {Fore.LIGHTRED_EX}NO SUBTITLES{Fore.LIGHTCYAN_EX}\n"
                msg += f"|----------------------------------------\n"
                if len([x for x in info.external_subs if x["tags"]["language"] is not None]):
                    for ss in info.external_subs:
                        if ss["tags"].get("language", ""):
                            ss["tags"]["language"] = ss["tags"].get("language", "")
                            ss["tags"]["title"] = ss["tags"].get("title", "")
                            sub_attr = {"language": ss["tags"]["language"], "title": ss["tags"]["title"]}
                            msg += f"|  Subtitle {ss.get('index', 'extra')}:\n"
                            for k, v in sub_attr.items():
                                msg += f"|     {k}: {v}\n"
                else:
                    msg += f"|  {Fore.LIGHTRED_EX}NO EXTERNAL SUBTITLES{Fore.LIGHTCYAN_EX}\n"
                msg += f"|----------------------------------------\n"

                msg += f"\n\nPress:\n"
                msg += f"\t- 'ready' to mark it as ready\n"
                if len([x for x in info.external_subs if x["tags"]["language"] is not None]):
                    msg += f"\t- 'delay' to sync external subtitles\n"
                msg += f"\t- 't' to test the final movie\n"
                msg += f"\t- ENTER to repeat sub-scanning\n"
                
                feedback = None
                repeat = True
                while feedback != "":
                    skip_prompt = ["t"]
                    feedback = print_console(msg, Fore.LIGHTCYAN_EX).replace("\n", "").strip().lower() if feedback not in skip_prompt else input()
                    if feedback == "":
                        self.get_paths()
                        break
                    elif feedback == "ready":
                        repeat = False
                        break
                    elif feedback == "t":
                        subprocess.run([VLC_PATH, self.video_path])
                    elif feedback == "delay" and len([x for x in info.external_subs if x["tags"]["language"] is not None]):
                        sub_delay_interface([x for x in info.external_subs if x["tags"]["language"] is not None])
                if not repeat:
                    break


            if new_video_path:
                for sub in info.external_subs:
                    if not sub["tags"]["language"]:
                        safe_remove_file(sub["path"])
                try:
                    to_path = move_to.joinpath(new_video_path.parent.stem)
                    if to_path.exists():
                        print(f"{Fore.LIGHTYELLOW_EX}   Folder {to_path} already exists. Overwriting now.{Style.RESET_ALL}")
                        shutil.rmtree(to_path, onerror=remove_readonly)
                    shutil.move(new_video_path.parent, to_path)
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


def prepare_plex(purgatory_path):
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
            shutil.move(file, new_folder_path.joinpath(file.stem + file.suffix))

        # Sharing info about skipped folders/files
        if len(invalid_folders):
            msg = f"The following containers have been skipped because invalid folders:\n\nPress Enter to continue..."
            for f in invalid_folders:
                msg += f"\t- {f.path.stem}\n"
            print_console(msg, Fore.LIGHTYELLOW_EX)
        if len(main_folder.other_paths):
            msg = f"The following files have been skipped because invalid video:\n\nPress Enter to continue..."
            for f in main_folder.other_paths:
                msg += f"\t- {f.path.stem}\n"
            print_console(msg, Fore.LIGHTYELLOW_EX)
        
        # The structure of the working_path is fixed at this point
        working_folder = Folder(working_dir_path)
        for folder in working_folder.sub_folders:
            folder.process(move_to=ready_dir_path)
    
    except Exception:
        print(traceback.format_exc())

    clean_dirs(working_dir_path)
    clean_dirs(trash_path)
    
    ready_folder = Folder(ready_dir_path)
    if len(ready_folder.sub_folders):
        print_console("Press Enter to send files to the server...", Fore.YELLOW)

        for folder in ready_folder.sub_folders:
            if "@" in FINAL_MOVIE_HOLDER_PATH:
                print(f"Uploading {folder.path} to the server...")
                cmd = ["scp", "-r", str(folder.path), f"{FINAL_MOVIE_HOLDER_PATH}/{folder.path.stem + folder.path.suffix}"]
                res = execute(cmd, errorMsg=f"Error during scp execution to upload movie")
                if res:
                    shutil.rmtree(folder.path, onerror=remove_readonly)
            else:
                print(f"Moving {folder.path} into {FINAL_MOVIE_HOLDER_PATH}...")
                shutil.move(folder.path, f"{FINAL_MOVIE_HOLDER_PATH}/{folder.path.stem + folder.path.suffix}")
    
    clean_dirs(ready_dir_path)
    print(f"{Fore.GREEN}Preparation to Plex completed.{Style.RESET_ALL}")
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
