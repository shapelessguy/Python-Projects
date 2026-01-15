using System;
using System.Diagnostics;
using System.Security.Principal;

class Program
{
    static void Main()
    {
        bool isAdmin = new WindowsPrincipal(
            WindowsIdentity.GetCurrent()
        ).IsInRole(WindowsBuiltInRole.Administrator);

        string script = isAdmin ? "launchCyanManagerAsAdmin.vbs" : "launchCyanManager.vbs";

        Process.Start(new ProcessStartInfo
        {
            FileName = "wscript.exe",
            Arguments = "\"" + script + "\"",
            UseShellExecute = true
        });
    }
}