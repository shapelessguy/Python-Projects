using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Imaging;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace CyanLauncherManager
{
    class LApplication
    {
        public string name = "";
        public string apps_path = "";
        public string icon_path = "";
        public string id = "";

        public LApplication(string directory, string icon_path, string id)
        {
            this.name = Path.GetFileName(directory);
            this.apps_path = Path.GetDirectoryName(directory);
            this.icon_path = icon_path;
            if (id.Length > 0) this.id = id;
            else
            {
                this.icon_path = this.icon_path.Replace(".ico", "default.ico");
                this.id = "default";
                string new_icon_path = Path.Combine(apps_path, "__Icons__", this.id + ".ico");
                string reference_path = Path.Combine(apps_path, name, name + ".exe");
                string loc_path = Path.Combine(apps_path, name, name + ".lnk");
                using(StreamWriter stream = new StreamWriter(Path.Combine(apps_path, name, "id.txt"))) stream.Write(this.id);
                new CreateLink(reference_path, loc_path, new_icon_path);
            }
        }

        public void Start()
        {
            Program.KillProc(name);
            string link_path = Path.Combine(apps_path, name, name + ".lnk");
            Console.WriteLine(link_path);
            try
            {
                ProcessStartInfo info = new ProcessStartInfo(link_path, "-h");
                Process.Start(info);
            }
            catch {
                MessageBox.Show("Sorry man, this " + link_path + " path is nowhere to be found!");
            }
        }

        private bool UpdateName(string new_name)
        {
            if (name == new_name) return true;
            Console.WriteLine("Updating name.");
            try
            {
                Program.KillProc(name);

                Directory.Move(Path.Combine(apps_path, name), Path.Combine(apps_path, new_name));
                try
                {
                    File.Move(Path.Combine(apps_path, new_name, name + ".exe"), Path.Combine(apps_path, new_name, new_name + ".exe"));
                    File.Move(Path.Combine(apps_path, new_name, name + ".lnk"), Path.Combine(apps_path, new_name, new_name + ".lnk"));
                }
                catch (Exception) { Directory.Move(Path.Combine(apps_path, new_name), Path.Combine(apps_path, name)); return false; }

                this.name = new_name;
                return true;
            }
            catch (Exception ex) { Console.WriteLine(ex); }
            return false;
        }
        private bool UpdateImage(string ico_path)
        {
            Console.WriteLine("Updating image.");
            try
            {
                Process[] processCollection = Process.GetProcesses();
                foreach (Process p in processCollection) if (p.ProcessName == name) p.Kill();
                foreach (string file in Directory.EnumerateFiles(Path.Combine(apps_path, name))) if (Program.isLink(file)) File.Delete(file);

                try {
                    id = Program.GenerateCausualString(10);
                    string new_icon_path = Path.Combine(apps_path, "__Icons__", id + ".ico");
                    string redundant_icon_path = Path.Combine(apps_path, name, "icon.ico");
                    string reference_path = Path.Combine(apps_path, name, name + ".exe");
                    string loc_path = Path.Combine(apps_path, name, name + ".lnk");
                    if (Path.GetExtension(ico_path) == "ico") File.Copy(ico_path, new_icon_path); 
                    else PngIconConverter.Convert(ico_path, new_icon_path, 200);
                    using (StreamWriter stream = new StreamWriter(Path.Combine(apps_path, name, "id.txt"))) stream.Write(id);
                    new CreateLink(reference_path, loc_path, new_icon_path);
                    File.Copy(new_icon_path, redundant_icon_path);
                }
                catch (Exception) { }

                this.icon_path = ico_path;
                return true;
            }
            catch (Exception ex) { Console.WriteLine(ex); }
            return false;
        }


        public bool setName(string name)
        {
            bool valid = true;
            try { Path.GetFullPath(Path.Combine(apps_path, name)); }
            catch (Exception) { valid = false; }
            if (name.Contains(".")) valid = false;

            if (valid)
            {
                UpdateName(name);
                return true;
            }
            else
            {
                MessageBox.Show("The application name is invalid.");
                return false;
            }
        }
        public bool setImage(string ico_path)
        {
            return UpdateImage(ico_path);
        }
    }
}
