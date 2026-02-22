using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Windows.Forms;

namespace CyanLauncher
{
    static class Program
    {
        static public Frontal frontal;
        static public string tempDataPathAdmin = Path.Combine(@"C:\", "Temp", "launchFileAdmin.txt");
        static public string tempDataPath = Path.Combine(@"C:\", "Temp", "launchFile.txt");
        static public string iconsFolder = @"";
        static public string programFolder = @"";
        static public List<Info> INFO;

        static public Size dimensions = new Size(3, 2);
        static public Size iconSize = new Size(200, 200);
        static public Point current_location = new Point(-9999, -9999);
        static public Size current_size = new Size(0, 0);
        static public int opacity = 8;
        static public bool centerSpawn = true;
        static public bool allowsDrag = true;
        static public bool vanish = true;
        static public bool canMove = false;
        static public bool initial_call = true;


        [STAThread]

        static void Main(string[] args)
        {
            Environment.CurrentDirectory = AppDomain.CurrentDomain.BaseDirectory;
            const string RegPath = @"CyanLauncher";

            string procName = Process.GetCurrentProcess().ProcessName;

            if (Process.GetProcessesByName(procName).Length > 1)
            {
                using (var key = Registry.CurrentUser.CreateSubKey(RegPath))
                {
                    key.SetValue(AppDomain.CurrentDomain.BaseDirectory, 1, RegistryValueKind.DWord);
                }
                return;
            }
            foreach (string arg in args) if (arg == "-h") initial_call = false;
            programFolder = Environment.CurrentDirectory;
            string filename = Process.GetCurrentProcess().MainModule.FileName;
            INFO = new List<Info>();
            CreateFolders();
            Load();
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(frontal = new Frontal());
        }

        static private void CreateFolders()
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(tempDataPathAdmin) ?? throw new InvalidOperationException("Invalid path"));
                if (!File.Exists(tempDataPathAdmin)) File.WriteAllText(tempDataPathAdmin, "");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }

            string icoFolder = Path.Combine(programFolder, "Icons");
            if (!Directory.Exists(icoFolder)) Directory.CreateDirectory(icoFolder);
            iconsFolder = icoFolder;

        }
        static public void Load()
        {
            if (!File.Exists(Path.Combine(programFolder, "info.json"))) saveInfo();
            if (!File.Exists(Path.Combine(programFolder, "Settings.txt"))) saveSettings();

            try
            {
                string jsonPath = Path.Combine(programFolder, "info.json");
                string json = File.ReadAllText(jsonPath);
                List<Dictionary<string, object>> entries = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(json);

                foreach (var dict in entries)
                {
                    string exe = dict.TryGetValue("exe_path", out var v1) ? v1?.ToString() : "";
                    string arguments = dict.TryGetValue("arguments", out var v2) ? v2?.ToString() : "";
                    string name = dict.TryGetValue("name", out var v3) ? v3?.ToString() : "";
                    string icon = dict.TryGetValue("icon", out var v4) ? v4?.ToString() : "";
                    bool admin = dict.TryGetValue("as_admin", out var v5) && v5 is bool b ? b : false;
                    INFO.Add(new Info(exe, arguments, name, icon, admin));
                }
            }
            catch (Exception e) { MessageBox.Show("Error is occured while trying to load Info. Exception: " + e.Message); }
            try
            {
                foreach (string stringa in File.ReadAllLines(Path.Combine(new string[] { programFolder, "Settings.txt" })))
                {
                    string[] segments = stringa.Split(new string[] { "|^_^|" }, StringSplitOptions.RemoveEmptyEntries);
                    try
                    {
                        if (segments[0] == "dimensions")
                        {
                            string[] coords = segments[1].Split(new string[] { ";" }, StringSplitOptions.RemoveEmptyEntries);
                            dimensions = new Size(Convert.ToInt32(coords[0]), Convert.ToInt32(coords[1]));
                        }
                        else if (segments[0] == "iconSize")
                        {
                            string[] coords = segments[1].Split(new string[] { ";" }, StringSplitOptions.RemoveEmptyEntries);
                            iconSize = new Size(Convert.ToInt32(coords[0]), Convert.ToInt32(coords[1]));
                        }
                        else if (segments[0] == "location")
                        {
                            string[] coords = segments[1].Split(new string[] { ";" }, StringSplitOptions.RemoveEmptyEntries);
                            current_location = new Point(Convert.ToInt32(coords[0]), Convert.ToInt32(coords[1]));
                        }
                        else if (segments[0] == "opacity") opacity = Convert.ToInt32(segments[1]);
                        else if (segments[0] == "allowsDrag") allowsDrag = Convert.ToBoolean(segments[1]);
                        else if (segments[0] == "centerSpawn") centerSpawn = Convert.ToBoolean(segments[1]);
                        else if (segments[0] == "vanish") vanish = Convert.ToBoolean(segments[1]);
                        else if (segments[0] == "canMove") canMove = Convert.ToBoolean(segments[1]);
                    }
                    catch (Exception) { Console.WriteLine("EXCEPTION IN LOAD"); }
                }
            }
            catch (Exception e) { MessageBox.Show("Error is occured while trying to load Settings. Exception: " + e.Message); }
        }

        static private void saveInfo()
        {
            try
            {
                List<Dictionary<string, object>> serializable = INFO.Select(inf => inf.Serialize()).ToList();
                string json = JsonSerializer.Serialize(serializable, new JsonSerializerOptions { WriteIndented = true });
                File.WriteAllText(Path.Combine(programFolder, "info.json"), json);
            }
            catch (Exception e) { MessageBox.Show("Error is occured while trying to save info. Exception: " + e.Message); }
        }
        static public void saveSettings()
        {
            try
            {
                List<string> strings = new List<string>();
                strings.Add("dimensions|^_^|" + dimensions.Width + ";" + dimensions.Height);
                strings.Add("iconSize|^_^|" + iconSize.Width + ";" + iconSize.Height);
                strings.Add("location|^_^|" + current_location.X + ";" + current_location.Y);
                strings.Add("opacity|^_^|" + opacity);
                strings.Add("allowsDrag|^_^|" + allowsDrag);
                strings.Add("centerSpawn|^_^|" + centerSpawn);
                strings.Add("vanish|^_^|" + vanish);
                strings.Add("canMove|^_^|" + canMove);

                File.WriteAllLines(Path.Combine(new string[] { programFolder, "Settings.txt" }), strings.ToArray());
            }
            catch (Exception e) { MessageBox.Show("Error is occured while trying to save settings. Exception: " + e.Message); }
        }

        static public void Save()
        {
            saveInfo();
            saveSettings();
        }

        static public string GetExeText(string exeText)
        {
            if (exeText.StartsWith("python:")) exeText = exeText.Substring(7);
            else if (exeText.StartsWith("chrome:")) exeText = exeText.Substring(7);
            return exeText;
        }
        static public string GetExeType(string exeText)
        {
            string exeType = "exe";
            if (exeText.StartsWith("python:")) exeType = "python";
            else if (exeText.StartsWith("chrome:")) exeType = "chrome";
            else if (Directory.Exists(exeText)) exeType = "folder";
            return exeType;
        }
    }

    public class Info
    {
        public string exepath = "";
        public string arguments = "";
        public string name = "";
        public string imgpath = "";
        public bool as_admin = false;
        public Info(string exepath, string arguments, string name, string imgpath, bool as_admin)
        {
            this.exepath = exepath;
            this.arguments = arguments;
            this.name = name;
            if (imgpath.Substring(0, 1) == @"\") imgpath = Program.programFolder + imgpath;
            this.imgpath = imgpath;
            this.as_admin = as_admin;
        }
        public Dictionary<string, object> Serialize()
        {
            return new Dictionary<string, object>
            {
                ["exe_path"] = exepath ?? "",
                ["arguments"] = arguments ?? "",
                ["name"] = name ?? "",
                ["icon"] = imgpath?.Replace(Program.programFolder, "") ?? "",
                ["as_admin"] = as_admin
            };
        }
    }
}
