 ------------------------------------------------------------------------------------
|                                                                                    |
|   SIMPLEST WAY TO INSTALL VIDEO-PROCESSING LIB IS TO USE THE "install" BAT FILES.  |
|                                                                                    |
 ------------------------------------------------------------------------------------
Notes:
    In order to cleanly install videoProcessing, you MUST install Plex for Windows, SVP4 and VLC first.
    For VLC support you have to go to: SVP menu -> Run Utilities -> SVP in VLC.
    You MUST download/install ffmpeg/bin - MKVToolNix tools somewhere: they should also be added to the environment variables (PATH).


-----------------

Manual setting of SVP for Plex:

Setting up Plex (Windows, Mac), Plex HTPC (Windows), Plex Media Player (Windows, Linux, macOS)
    versions used: Plex 1.107.1 (22 Jan 2025), Plex HTPC 1.69.0 (9 Dec 2024), PMP 2.58.0 (19 May 2020)

- Install Plex for Windows or Plex HTPC or Plex Media Player (discontinued)
- Install mpv shared library package from the SVP's installer
- Run Utilities -> Set environment variables OR adjust a few system settings manually to allow Plex find the Vapoursynth installation:
        add SVP 4\mpv64 folder to the PATH environment variable
        add new env variable called PYTHONPATH, containing the same SVP 4\mpv64 path

- Replace Plex's libmpv-2.dll with the one from "SVP 4\mpv64\": copy "C:\Program Files (x86)\SVP 4\mpv64\libmpv-2.dll" to "C:\Program Files\Plex\Plex\libmpv-2.dll"
- For older versions of Plex download mpv-2.dll manually and replace "mpv-2.dll" instead.
- Create mpv's configuration file in "C:\Users\<name>\AppData\Local\Plex\mpv.conf" with the following contents:
        >> input-ipc-server=mpvpipe
        >> hwdec-codecs=all
        >> hr-seek-framedrop=no

- VLC (x64) setup: Run Utilities -> SVP in VLC
-----------------

Manual adding splitSubs to Windows contextMenu:

To add the splitSubs into the context menu of windows:

1. Create a key in the registry: Computer\HKEY_CLASSES_ROOT\Directory\Background\shell\preparePlex
2. Inside this key create two strings:
    - Icon: "C:\Users\shape\Pictures\Icons\Alecive-Flatwoken-Apps-Player-Video.ico"
    - MUIVerb: Prepare for Plex
3. Inside this key, create a new key called "command" and set the default value to:
    - "C:\Users\shape\Documents\WorkPySpace\sharedCode\videoProcessing\launch_split_subs.bat" "%V"
---------------
