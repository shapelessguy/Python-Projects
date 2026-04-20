using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.Remoting.Messaging;
using System.Security.Principal;
using System.Windows.Forms;

namespace CyanLauncherManager
{

    static class Program
    {
        public static bool initial_call = false;
        private static string appGuid = "c0a76b5a-12ab-45c5-b9d9-d693faa6e7b9";
        static public string tempDataPathAdmin = Path.Combine(@"C:\", "Temp", "launchFileAdmin.txt");
        static public string tempDataPath = Path.Combine(@"C:\", "Temp", "launchFile.txt");


        [STAThread]
        static void Main()
        {
            RegistryKey rk = Registry.CurrentUser.OpenSubKey("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run", true);
            rk.SetValue("CyanLaunchManager", Application.ExecutablePath);
            using (System.Threading.Mutex mutex = new System.Threading.Mutex(false, "Global\\" + appGuid))
            {
                if (!mutex.WaitOne(0, false)) return;

                string baseDir = AppDomain.CurrentDomain.BaseDirectory;
                string relativePath = Path.Combine(baseDir, @"..\..\..\CyanAppLauncher\bin\Release\CyanAppLauncher.exe");
                string targetExe = Path.GetFullPath(relativePath);
                if (!File.Exists(targetExe))
                {
                    Console.WriteLine($"Target not found: {targetExe}");
                    return;
                }

                string app_id_admin = "c0a76b5a-12ab-45c5-b9d9-d693faa6e9b9";
                var psi_admin = new ProcessStartInfo
                {
                    FileName = targetExe,
                    Arguments = $"\"{app_id_admin}\" \"{tempDataPathAdmin}\"",
                    Verb = "runas",
                    UseShellExecute = true,
                    CreateNoWindow = true,
                    WindowStyle = ProcessWindowStyle.Hidden
                };
                Process.Start(psi_admin);

                if (!new WindowsPrincipal(WindowsIdentity.GetCurrent()).IsInRole(WindowsBuiltInRole.Administrator))
                {
                    string app_id = "c0a76b5a-12ab-45c5-b9d9-d693faa6e9a9";
                    var psi = new ProcessStartInfo
                    {
                        FileName = targetExe,
                        Arguments = $"\"{app_id}\" \"{tempDataPath}\"",
                        UseShellExecute = true,
                        CreateNoWindow = true,
                        WindowStyle = ProcessWindowStyle.Hidden
                    };
                    Process.Start(psi);
                }

                try
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(tempDataPath) ?? throw new InvalidOperationException("Invalid path"));
                }
                catch (Exception ex)
                {
                    Console.WriteLine($"Error: {ex.Message}");
                }

                try
                {
                    Application.EnableVisualStyles();
                    Application.SetCompatibleTextRenderingDefault(false);
                    Application.Run(new MainWindow());
                }
                catch (Exception e)
                {
                    Console.WriteLine($"Application crashed: {e}");
                }
            }
        }

        

        static public bool isIcon(string file)
        {
            if (file.Contains(".ico")) return true;
            else return false;
        }
        static public bool isLink(string file)
        {
            if (file.Contains(".lnk")) return true;
            else return false;
        }
        static public bool isText(string file)
        {
            if (file.Contains(".txt")) return true;
            else return false;
        }

        static public void KillProc(string name)
        {
            Process[] processCollection = Process.GetProcesses();
            foreach (Process p in processCollection) if (p.ProcessName == name) p.Kill();
            System.Threading.Thread.Sleep(100);
        }

        static public List<string> GetApplicationNames(string path, bool only_name = false)
        {
            List<string> output = new List<string>();
            foreach (string directory in Directory.EnumerateDirectories(path))
            {
                if (directory != Path.Combine(path, "__Icons__") && directory != Path.Combine(path, "__Matrix__"))
                {
                    output.Add(only_name ? Path.GetFileName(directory) : directory);
                }
            }
            return output;
        }

        static public string GenerateCausualString(int length)
        {
            Random random = new Random();
            const string chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
            return new string(Enumerable.Repeat(chars, length).Select(s => s[random.Next(s.Length)]).ToArray());
        }
    }
}
