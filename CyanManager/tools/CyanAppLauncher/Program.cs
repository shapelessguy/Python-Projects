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
        private const string REG_PATH = @"SOFTWARE\CyanTools\Launcher";
        private const string REG_VALUE_NAME = "LaunchPending";
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


            while (true)
            {
                try
                {
                    using (RegistryKey key = Registry.CurrentUser.OpenSubKey(REG_PATH))
                    {
                        if (key != null)
                        {
                            object value = key.GetValue(REG_VALUE_NAME);
                            if (value != null && value.ToString() != "")
                            {
                                LaunchTarget(value.ToString());
                                using (RegistryKey writeKey = Registry.CurrentUser.OpenSubKey(REG_PATH, true))
                                {
                                    if (writeKey != null) writeKey.DeleteValue(REG_VALUE_NAME, false);
                                }
                            }
                        }
                    }
                }
                catch (Exception ex)
                {
                    Console.WriteLine("Registry poll error: " + ex.Message);
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
