using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace CyanLauncher
{
    static class Program
    {
        static public Frontal frontal;
        static public string tempDataPath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "Cyan", "CyanLauncher", "launchFile.txt");
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


        [DllImport("user32.dll")]
        public static extern IntPtr FindWindow(string lpClassName, String lpWindowName);
        [DllImport("user32.dll")]
        public static extern int SendMessage(IntPtr hWnd, uint wMsg, IntPtr wParam, IntPtr lParam);
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        static extern uint RegisterWindowMessage(string lpString);

        /// <summary>
        /// Punto di ingresso principale dell'applicazione.
        /// </summary>
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
            Application.Run(frontal = new Frontal()); //{ allowshowdisplay = true });
        }

        static private void CreateFolders()
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(tempDataPath) ?? throw new InvalidOperationException("Invalid path"));
                if (!File.Exists(tempDataPath)) File.WriteAllText(tempDataPath, "");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }

            string icoFolder = Path.Combine(new string[] { programFolder, "Icons" });
            if (!Directory.Exists(icoFolder)) Directory.CreateDirectory(icoFolder);
            iconsFolder = icoFolder;

        }
        static public void Load()
        {
            if (!File.Exists(Path.Combine(new string[] { programFolder, "Info.txt" })))
            {
                saveInfo();
            }
            if (!File.Exists(Path.Combine(new string[] { programFolder, "Settings.txt" })))
            {
                saveSettings();
            }
            try
            {
                foreach (string stringa in File.ReadAllLines(Path.Combine(new string[] { programFolder, "Info.txt" })))
                {
                    string[] segments = stringa.Split(new string[] { "|^_^|" }, StringSplitOptions.RemoveEmptyEntries);
                    try
                    {
                        INFO.Add(new Info(segments[0], segments[1], segments[2], segments[3]));
                    }
                    catch (Exception) { Console.WriteLine("EXCEPTION IN LOAD"); }
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
            Console.WriteLine(dimensions);
        }

        static private void saveInfo()
        {
            try
            {
                List<string> strings = new List<string>();
                foreach (Info inf in INFO) strings.Add(inf.Serialize());

                File.WriteAllLines(Path.Combine(new string[] { programFolder, "Info.txt" }), strings.ToArray());
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
    }

    public class Info
    {
        public string exepath = "";
        public string name = "";
        public string imgpath = "";
        public string as_admin = "";
        public Info(string exepath, string name, string imgpath, string as_admin)
        {
            this.exepath = exepath;
            this.name = name;
            if (imgpath.Substring(0, 1) == @"\") imgpath = Program.programFolder + imgpath;
            this.imgpath = imgpath;
            this.as_admin = as_admin;
        }
        public string Serialize()
        {
            string output = "";
            output += exepath + "|^_^|";
            output += name + "|^_^|";
            output += imgpath.Replace(Program.programFolder, "") + "|^_^|";
            output += as_admin;
            return output;
        }
    }
}
