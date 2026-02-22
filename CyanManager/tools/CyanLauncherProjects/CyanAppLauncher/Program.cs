using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using static System.Net.Mime.MediaTypeNames;

namespace CyanAdminLauncher
{
    internal class Program
    {
        private static string appGuid = "c0a76b5a-12ab-45c5-b9d9-d693faa6e9b9";
        static public string tempDataPath = Path.Combine(@"C:\", "Temp", "launchFile.txt");
        static void Main(string[] args)
        {
            string exePath = Assembly.GetEntryAssembly().Location;
            bool createdNew;
            new Mutex(true, "Global\\" + appGuid, out createdNew);
            if (!createdNew)
            {
                Console.WriteLine("Another instance is already running.");
                return;
            }
            try
            {
                if (File.Exists(tempDataPath)) File.Delete(tempDataPath);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Cannot remove the file: " + ex.Message);
            }


            while (true)
            {
                try
                {
                    if (File.Exists(tempDataPath))
                    {
                        string launchPath = File.ReadAllText(tempDataPath).Trim();
                        File.Delete(tempDataPath);

                        if (!string.IsNullOrWhiteSpace(launchPath))
                        {
                            LaunchTarget(launchPath);
                            Console.WriteLine("Pending launch processed and flag removed.");
                        }
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine("File poll error: " + ex.Message);
                }
                Thread.Sleep(100);
            }
        }

        private static void LaunchTarget(string exePath)
        {
            if (!File.Exists(exePath))
            {
                Console.WriteLine("Target not found: " + exePath);
                return;
            }

            Console.WriteLine("Launching target: " + exePath);

            var psi = new ProcessStartInfo
            {
                FileName = exePath,
                UseShellExecute = true,
                WorkingDirectory = Path.GetDirectoryName(exePath),
                WindowStyle = ProcessWindowStyle.Normal
            };

            try
            {
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                Console.WriteLine("Launch failed: " + ex.Message);
            }
        }
    }
}
