using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

namespace CyanLauncherManager
{
    class CreateLink
    {
        public CreateLink(string reference_path, string loc_path, string icon_path)
        {
            IShellLink link = (IShellLink)new ShellLink();

            // setup shortcut information
            link.SetDescription("CyanLauncher Link");
            link.SetPath(reference_path);
            link.SetIconLocation(icon_path, 0);

            // save it
            IPersistFile file = (IPersistFile)link;
            file.Save(loc_path, false);
        }
    }

    [ComImport]
    [Guid("00021401-0000-0000-C000-000000000046")]
    internal class ShellLink
    {
    }

    [ComImport]
    [InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    [Guid("000214F9-0000-0000-C000-000000000046")]
    internal interface IShellLink
    {
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string pszName);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string pszIconPath, int iIcon);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string pszFile);
    }
}