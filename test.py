import win32api
import win32con
import pywintypes

def set_resolution(width: int, height: int) -> bool:
    """
    Change primary display resolution.
    Returns True if successful, False otherwise.
    """
    try:
        devmode = pywintypes.DEVMODEType()

        # Only changing width & height (refresh rate stays as is)
        devmode.PelsWidth  = width
        devmode.PelsHeight = height
        devmode.Fields     = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT

        # 0 = change on primary display + update registry (persistent)
        result = win32api.ChangeDisplaySettings(devmode, 0)

        if result == win32con.DISP_CHANGE_SUCCESSFUL:
            print(f"Resolution changed to {width}×{height}")
            return True
        else:
            print(f"ChangeDisplaySettings failed: {result}")
            # Common codes: -1 = bad mode, -2 = not supported, -3 = bad flags, -4 = bad param, -5 = driver failed, etc.
            return False

    except Exception as e:
        print(f"Error: {e}")
        return False


# ────────────────────────────────────────────────
if __name__ == "__main__":
    # Examples
    set_resolution(1920, 1200)     # Full HD
    # set_resolution(2560, 1440)   # 1440p
    # set_resolution(3840, 2160)   # 4K (if monitor supports it)