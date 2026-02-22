using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Threading;

namespace CyanAdminLauncher
{
    internal class Program
    {
        private static string appGuid = "";
        static public string tempDataPath = "";
        static void Main(string[] args)
        {
            if (args.Length > 0) appGuid = args[0];
            if (args.Length > 1) tempDataPath = args[1];
            if (appGuid == "" || tempDataPath == "") return;

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
                        string commandLine = File.ReadAllText(tempDataPath).Trim();
                        File.Delete(tempDataPath);

                        if (!string.IsNullOrWhiteSpace(commandLine))
                        {
                            LaunchTarget(commandLine);
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

        private static void LaunchTarget(string commandLine)
        {
            string trimmed = commandLine.Trim();
            string exe;
            string args = null;

            if (trimmed.StartsWith("\""))
            {
                int closingQuote = trimmed.IndexOf('"', 1);
                if (closingQuote == -1)
                {
                    exe = trimmed;
                }
                else
                {
                    exe = trimmed.Substring(1, closingQuote - 1);
                    string rest = trimmed.Substring(closingQuote + 1).Trim();
                    if (!string.IsNullOrEmpty(rest))
                        args = rest;
                }
            }
            else
            {
                var parts = trimmed.Split(new[] { ' ' }, 2, StringSplitOptions.RemoveEmptyEntries);
                exe = parts[0];
                if (parts.Length > 1) args = parts[1];
            }

            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = args,
                UseShellExecute = true,
                CreateNoWindow = true,
            };

            Process.Start(psi);
        }
    }
}
