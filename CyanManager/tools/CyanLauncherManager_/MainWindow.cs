using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
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
    public partial class MainWindow : Form
    {
        List<LApplication> all_applications = new List<LApplication>();
        string cyanLauncher_corePath = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Launcher");
        string cyanLauncher_dataPath = "";
        static public NotifyIcon notifyIcon;
        static readonly IContainer componentsNotify = new Container();
        static public bool close_for_real = false;
        public MainWindow()
        {
            InitializeComponent();
            CreateNotify();
            app_panel.Visible = false;
            this.startup_check.Checked = Properties.Settings.Default.startup;

            string programData_path = Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData);
            if (!Directory.Exists(Path.Combine(programData_path, "Cyan"))) {
                Directory.CreateDirectory(Path.Combine(programData_path, "Cyan"));
            }
            cyanLauncher_dataPath = Path.Combine(programData_path, "Cyan", "CyanLauncher");
            string cyanLauncher_iconsPath = Path.Combine(cyanLauncher_dataPath, "__Icons__");
            if (!Directory.Exists(cyanLauncher_dataPath)) Directory.CreateDirectory(cyanLauncher_dataPath);

            string solution_path = getParent(Environment.CurrentDirectory, 2);
            EmbedCore(Path.Combine(solution_path, "CyanLauncher", "CyanLauncher", "bin", "Release"));
            if (!Directory.Exists(cyanLauncher_corePath))
            {
                MessageBox.Show("Launcher folder doesn't exist");
                return;
            }

            if (!Directory.Exists(cyanLauncher_iconsPath))
            {
                Directory.CreateDirectory(cyanLauncher_iconsPath);
                File.Copy(Path.Combine(cyanLauncher_corePath, "Icon.ico"), Path.Combine(cyanLauncher_iconsPath, "default.ico"));
            }
            ResetPanel();
            WindowState = FormWindowState.Minimized;
            ShowInTaskbar = false;
            Hide();
        }
        void CreateNotify()
        {
            notifyIcon = new NotifyIcon(componentsNotify)
            {
                Icon = Properties.Resources.Icon1,
                Text = "LauncherManager",
                Visible = true,
            };
            TrayMenuContext();
        }
        void TrayMenuContext()
        {
            notifyIcon.ContextMenuStrip = new ContextMenuStrip();
            notifyIcon.MouseDoubleClick += (o, e) => { OpenWindow(o, e); };
            notifyIcon.ContextMenuStrip.Items.Add("Open", Properties.Resources.Icon, OpenWindow);
            notifyIcon.ContextMenuStrip.Items.Add("Close", Properties.Resources.Icon, CloseWindow);
        }

        private void OpenWindow(object o, EventArgs e)
        {
            ShowInTaskbar = true;
            Visible = true;
            WindowState = FormWindowState.Normal;
        }
        private void CloseWindow(object o, EventArgs e)
        {
            close_for_real = true;
            Close();
        }
        private void MainWindow_FormClosing(object sender, FormClosingEventArgs e)
        {
            if (!close_for_real) {
                Visible = false;
                e.Cancel = true;
            } 
        }

        private void Copy(string path1, string path2, bool force)
        {
            Console.WriteLine("Coping: " + path1 + "  to  " + path2);
            bool isDir = true;
            if (File.Exists(path1)) isDir = false;
            if (force)
            {
                if (isDir && Directory.Exists(path2)) Directory.Delete(path2, true);
                else if (File.Exists(path2)) File.Delete(path2);
            }
            Console.WriteLine(path1 + "   " + isDir);
            if (isDir) CopyFilesRecursively(path1, path2);
            else File.Copy(path1, path2);
        }
        private static void CopyFilesRecursively(string sourcePath, string targetPath)
        {
            //Now Create all of the directories
            Console.WriteLine(sourcePath);
            foreach (string dirPath in Directory.GetDirectories(sourcePath, "*", SearchOption.AllDirectories))
            {
                Directory.CreateDirectory(dirPath.Replace(sourcePath, targetPath));
            }

            //Copy all the files & Replaces any files with the same name
            foreach (string newPath in Directory.GetFiles(sourcePath, "*.*", SearchOption.AllDirectories))
            {
                File.Copy(newPath, newPath.Replace(sourcePath, targetPath), true);
            }
        }
        private void EmbedCore(string release_path)
        {
            string main_dir = Path.GetDirectoryName(Path.GetDirectoryName(release_path));
            if (Directory.Exists(release_path))
            {
                if (!Directory.Exists(cyanLauncher_corePath)) Directory.CreateDirectory(cyanLauncher_corePath);
                Copy(Path.Combine(release_path, "CyanLauncher.exe"), Path.Combine(cyanLauncher_corePath, "CyanLauncher.exe"), true);
                Copy(Path.Combine(release_path, "Control.Draggable.dll"), Path.Combine(cyanLauncher_corePath, "Control.Draggable.dll"), true);
                Copy(Path.Combine(main_dir, "Icon.ico"), Path.Combine(cyanLauncher_corePath, "Icon.ico"), true);
            }
        }

        private void ResetPanel()
        {
            application_panel.Controls.Clear();
            all_applications = findApplications(cyanLauncher_dataPath);
            createGraphicElements(all_applications);
        }

        private string getParent(string init_path, int levels = 1)
        {
            try
            {
                string path = init_path;
                for (int i = 0; i < levels; i++)
                {
                    path = Directory.GetParent(path).FullName;
                }
                return path;
            }
            catch (Exception) { return ""; }
        }

        private List<LApplication> findApplications(string launcher_path)
        {
            List<LApplication> applications = new List<LApplication>();
            foreach (string directory in Program.GetApplicationNames(launcher_path))
            {
                string id_icon = "";
                foreach (string file in Directory.EnumerateFiles(directory))
                {
                    if (Path.GetFileNameWithoutExtension(file) == "id") { 
                        using(StreamReader reader = new StreamReader(file)) id_icon = reader.ReadToEnd(); 
                        break; 
                    }
                }
                if (id_icon == "")
                {
                    using (StreamWriter stream = new StreamWriter(Path.Combine(directory, "id.txt"))) stream.Write("default");
                    id_icon = "default";
                }
                string icon_path = Path.Combine(launcher_path, "__Icons__", id_icon + ".ico");
                applications.Add(new LApplication(directory, icon_path, id_icon));
            }
            if (!Program.initial_call)
            {
                foreach(LApplication app in applications) { app.Start(); }
                Program.initial_call = true;
                Console.WriteLine("Initial call");
            }
            return applications;
        }
        private void createGraphicElements(List<LApplication> applications)
        {
            for (int i = 0; i < applications.Count; i++)
            {
                addToPanel(applications[i], i);
            }

        }

        private void addToPanel(LApplication application, int index = 0)
        {
            Panel app_panel = new Panel();
            Button app_start = new Button();
            Button app_delete = new Button();
            PictureBox app_picture = new PictureBox();
            TextBox app_name = new TextBox();

            // 
            // app_panel
            // 
            app_panel.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            app_panel.BackColor = Color.FromArgb(7, 7, 7);
            app_panel.Controls.Add(app_name);
            app_panel.Controls.Add(app_start);
            app_panel.Controls.Add(app_delete);
            app_panel.Controls.Add(app_picture);
            app_panel.ForeColor = Color.FromArgb(14, 14, 14);
            app_panel.Location = new Point(8, 9 + index * (57 + 6));
            app_panel.Name = "app_panel" + Convert.ToString(index);
            app_panel.Size = new Size(700, 57);
            app_panel.TabIndex = 0;
            app_panel.TabStop = false;

            //
            // app_picture
            //
            app_picture.Image = Properties.Resources.Icon;
            if (application.icon_path != "")
            {
                if (File.Exists((application.icon_path))) app_picture.Image = Bitmap.FromFile(application.icon_path);
            }

            app_picture.BackColor = Color.FromArgb(7, 7, 7);
            app_picture.Name = "app_picture" + Convert.ToString(index);
            app_picture.Location = new Point(94, 6);
            app_picture.Size = new Size(45, 45);
            app_picture.SizeMode = PictureBoxSizeMode.StretchImage;
            app_picture.TabIndex = 0;
            app_picture.TabStop = false;
            app_picture.Click += new EventHandler(app_picture_Click);

            void app_picture_Click(object sender, EventArgs e)
            {

                OpenFileDialog dialog = new OpenFileDialog();
                if (Properties.Settings.Default.lastImgPath != "") dialog.InitialDirectory = Properties.Settings.Default.lastImgPath;
                string filter = "All Graphics Types|*.bmp;*.ico;*.png;*.jpg;*.jpeg;*.tif;*.tiff|";
                filter += "Bitmap|*.bmp|Icon files|*.ico|Png files|*.png|Jpeg files|*.jpg;*.jpeg|Tiff files|*.tif;*.tiff";
                dialog.Filter = filter;

                dialog.CheckFileExists = true;
                dialog.Multiselect = false;

                if (dialog.ShowDialog() == DialogResult.OK)
                {
                    try
                    {
                        Properties.Settings.Default.lastImgPath = Directory.GetParent(dialog.FileName).FullName;
                        Properties.Settings.Default.Save();

                        if (application.setImage(dialog.FileName)) app_picture.Image = Bitmap.FromFile(application.icon_path);
                        else { MessageBox.Show("Error occurred"); }
                    }
                    catch (Exception) { }
                }
            }

            //
            // app_start
            //
            app_start.BackColor = Color.Green;
            app_start.FlatAppearance.BorderColor = Color.Maroon;
            app_start.FlatAppearance.BorderSize = 12;
            app_start.FlatAppearance.MouseDownBackColor = Color.FromArgb(64, 0, 0);
            app_start.FlatAppearance.MouseOverBackColor = Color.Red;
            app_start.FlatStyle = FlatStyle.Popup;
            app_start.Font = new Font("Constantia", 9.75F, FontStyle.Bold, GraphicsUnit.Point, 0);
            app_start.Name = "app_start" + Convert.ToString(index);
            app_start.Location = new Point(14, 17);
            app_start.Size = new Size(68, 23);
            app_start.TabIndex = 0;
            app_start.TabStop = false;
            app_start.Text = "Start";
            app_start.UseVisualStyleBackColor = false;
            app_start.Click += new EventHandler(app_start_Click);

            void app_start_Click(object sender, EventArgs e)
            {
                string link_path = Path.Combine(application.apps_path, application.name, application.name + ".lnk");
                ProcessStartInfo info = new ProcessStartInfo(link_path);
                Process whatever = Process.Start(info);
            }

            // 
            // app_delete
            // 
            app_delete.Anchor = AnchorStyles.Top | AnchorStyles.Right;
            app_delete.BackColor = Color.Red;
            app_delete.FlatAppearance.BorderColor = Color.Maroon;
            app_delete.FlatAppearance.BorderSize = 12;
            app_delete.FlatAppearance.MouseDownBackColor = Color.FromArgb(64, 0, 0);
            app_delete.FlatAppearance.MouseOverBackColor = Color.Red;
            app_delete.FlatStyle = FlatStyle.Popup;
            app_delete.Font = new Font("Constantia", 9.75F, FontStyle.Bold, GraphicsUnit.Point, 0);
            app_delete.Name = "app_delete" + Convert.ToString(index);
            app_delete.Location = new Point(632, 17);
            app_delete.Size = new Size(56, 23);
            app_delete.TabIndex = 0;
            app_delete.TabStop = false;
            app_delete.Text = "Delete";
            app_delete.UseVisualStyleBackColor = false;
            app_delete.Click += new EventHandler(app_delete_Click);

            void app_delete_Click(object sender, EventArgs e)
            {
                Program.KillProc(application.name);
                try { Directory.Delete(Path.Combine(application.apps_path, application.name), true); } catch (Exception) { }
                try { Directory.Delete(Path.Combine(application.apps_path, application.name), true); } catch (Exception) { }
                try { Directory.Delete(Path.Combine(application.apps_path, application.name), true); } catch (Exception) { }
                ResetPanel();
            }

            // 
            // app_name
            // 
            app_name.Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right;
            app_name.BackColor = Color.FromArgb(7, 7, 7);
            app_name.BorderStyle = BorderStyle.None;
            app_name.Font = new Font("Modern No. 20", 15.75F, FontStyle.Bold, GraphicsUnit.Point, ((byte)(0)));
            app_name.ForeColor = Color.White;
            app_name.Location = new Point(146, 17);
            app_name.Size = new Size(477, 23);
            app_name.Name = "app_name" + Convert.ToString(index);
            app_name.Text = application.name;
            app_name.TabIndex = 0;
            app_name.TabStop = false;
            setDefaultState(app_name, false);
            app_name.MouseDoubleClick += new MouseEventHandler(app_name_MouseDoubleClick);
            app_name.Leave += new EventHandler(app_name_Leave);
            app_name.KeyDown += new KeyEventHandler(app_name_KeyDown);

            void setDefaultState(TextBox box, bool update = true)
            {
                if (update) {
                    if (!application.setName(box.Text)) { box.Text = application.name; MessageBox.Show("Error occurred"); }
                    return; 
                }
                box.ReadOnly = true;
                app_name.Cursor = Cursors.Default;
            }
            void setExcitedState(TextBox box)
            {
                box.ReadOnly = false;
                app_name.Cursor = Cursors.IBeam;
            }

            void app_name_MouseDoubleClick(object sender, MouseEventArgs e)
            {
                TextBox box = (TextBox)sender;
                setExcitedState(box);
            }
            void app_name_Leave(object sender, EventArgs e)
            {
                TextBox box = (TextBox)sender;
                setDefaultState(box);
            }
            void app_name_KeyDown(object sender, KeyEventArgs e)
            {
                TextBox box = (TextBox)sender;
                if (e.KeyCode == Keys.Enter)
                {
                    setDefaultState(box);
                    app_start.Focus();
                    e.SuppressKeyPress = true;
                }
            }

            application_panel.Controls.Add(app_panel);
        }

        private bool CheckValidity(string str)
        {
            foreach (string directory in Program.GetApplicationNames(cyanLauncher_dataPath, true)) if (str == directory) return false;
            try { Path.GetFullPath(Path.Combine(cyanLauncher_dataPath, str)); }
            catch (Exception) { return false; }
            if (str.Contains(".") || str.Length == 0) return false;
            return true;
        }

        private void newapp_name_KeyUp(object sender, KeyEventArgs e)
        {
            if (CheckValidity(newapp_name.Text)) newapp_add.BackColor = Color.Orange;
            else newapp_add.BackColor = Color.Gray;
            if (e.KeyCode == Keys.Enter)
            {
                newapp_add_Click(sender, e);
                e.SuppressKeyPress = true;
            }
        }

        private void newapp_add_Click(object sender, EventArgs e)
        {
            if (newapp_add.BackColor == Color.Orange)
            {
                string newname = newapp_name.Text;
                newapp_name.Text = "";
                newapp_add.BackColor = Color.Gray;
                string id = "default";
                string new_icon_path = Path.Combine(cyanLauncher_dataPath, "__Icons__", id + ".ico");
                string reference_path = Path.Combine(cyanLauncher_dataPath, newname, newname + ".exe");
                string dll_reference_path = Path.Combine(cyanLauncher_dataPath, newname, "Control.Draggable.dll");
                string loc_path = Path.Combine(cyanLauncher_dataPath, newname, newname + ".lnk");

                Directory.CreateDirectory(Path.Combine(cyanLauncher_dataPath, newname));
                File.Copy(Path.Combine(cyanLauncher_corePath, "CyanLauncher.exe"), reference_path);
                File.Copy(Path.Combine(cyanLauncher_corePath, "Control.Draggable.dll"), dll_reference_path);
                using (StreamWriter stream = new StreamWriter(Path.Combine(cyanLauncher_dataPath, newname, "id.txt"))) stream.Write(id);
                new CreateLink(reference_path, loc_path, new_icon_path);

                ResetPanel();
            }
        }

        private void update_btn_Click(object sender, EventArgs e)
        {
            foreach (string directory in Program.GetApplicationNames(cyanLauncher_dataPath, true))
            {
                Program.KillProc(directory);
                File.Delete(Path.Combine(cyanLauncher_dataPath, directory, directory + ".exe"));
                File.Copy(Path.Combine(cyanLauncher_corePath, "CyanLauncher.exe"), 
                    Path.Combine(cyanLauncher_dataPath, directory, directory + ".exe"));
                Console.WriteLine("File " + Path.Combine(cyanLauncher_dataPath, directory, directory + ".exe") + " updated.");
            }
            MessageBox.Show("Launchers have been updated!");
        }


        private void checkBox1_CheckedChanged(object sender, EventArgs e)
        {
            Properties.Settings.Default.startup = this.startup_check.Checked;
            Properties.Settings.Default.Save();
            RegistryKey rk = Registry.LocalMachine.OpenSubKey("SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run", true);
            if (this.startup_check.Checked)
            {
                rk.SetValue("CyanLauncherManager", Application.ExecutablePath);
            }
            else
            {
                rk.DeleteValue("CyanLauncherManager", false);
            }
        }
    }
}
