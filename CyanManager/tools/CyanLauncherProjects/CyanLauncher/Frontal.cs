using Microsoft.Win32;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace CyanLauncher
{
    public partial class Frontal : Form
    {
        private int maxIcon_on_row = 0;
        private int maxIcon_on_col = 0;
        private int offsetX = 10;
        public ChangeDimensions change_dim_window = null;
        public AddIcon add_icon_window = null;
        private ContextMenuStrip contextMenuStrip;
        private ToolStripMenuItem addIcon;
        private ToolStripMenuItem changeDimension;
        private List<Icon> iconList = new List<Icon>();
        private Timer cleaner;
        private Timer calls, slow;
        public static bool disableResizing = false;

        //public bool allowshowdisplay = false;
        public Size initialSize;

        [DllImportAttribute("user32.dll")]
        public static extern bool SetForegroundWindow(IntPtr hWnd);

        private void toScreenCenter()
        {
            Screen screen = Screen.FromPoint(Cursor.Position);
            Rectangle bounds = screen.WorkingArea;

            int x = bounds.X + (bounds.Width - this.Width) / 2;
            int y = bounds.Y + (bounds.Height - this.Height) / 2;

            // Apply new location
            this.Location = new Point(x, y);
        }
        private void relocate()
        {
            
            if (Program.centerSpawn) toScreenCenter();
            else 
            {
                bool within = false;
                foreach (Screen screen in Screen.AllScreens)
                {
                    Rectangle bounds = screen.Bounds;
                    bounds.X = bounds.X - Size.Width;
                    bounds.Y = bounds.Y - 10;
                    bounds.Width = bounds.Width + Size.Width;
                    bounds.Height = bounds.Height + 10;
                    if (bounds.Contains(Program.current_location)) within = true;
                }
                if (within) Location = Program.current_location;
                else toScreenCenter();
            }
        }

        public Frontal()
        {
            Visible = false;
            setOpacity(Program.opacity);


            ComponentResourceManager resources = new ComponentResourceManager(typeof(Frontal));
            string id = "";
            string id_path = Path.Combine(Environment.CurrentDirectory, "id.txt");
            if (File.Exists(id_path)) using (StreamReader stream = new StreamReader(id_path)) id = stream.ReadToEnd();
            string icon_path = Path.Combine(Path.GetDirectoryName(Environment.CurrentDirectory), "__Icons__", id + ".ico");

            maxIcon_on_row = Program.dimensions.Width;
            maxIcon_on_col = Program.dimensions.Height;
            initialSize = new Size(maxIcon_on_row * Program.iconSize.Width + (maxIcon_on_row + 1) * offsetX + 10, maxIcon_on_col * Program.iconSize.Height + (maxIcon_on_col + 1) * offsetX + 10);
            
            FormClosing += (o, e) => { e.Cancel = true; Visible = false; ShowInTaskbar = false; };

            InitializeComponent();

            if (File.Exists(icon_path) && File.Exists(id_path))
            {
                Icon = new System.Drawing.Icon(icon_path);
                //pictureBox1.Image = Bitmap.FromFile(icon_path);
            }
            else { 
                Icon = Properties.Resources.Icon;
                //pictureBox1.Image = Icon.ToBitmap(); 
            }

            Text = Path.GetFileName(Environment.CurrentDirectory);
            //label1.Text = Text;


            contextMenuStrip = new ContextMenuStrip
            {
                ImageScalingSize = new System.Drawing.Size(24, 24),
                Name = "contextMenuStrip1",
                Size = new System.Drawing.Size(141, 34)
            };
            addIcon = new ToolStripMenuItem
            {
                Size = new System.Drawing.Size(140, 30),
                Text = "Add Program/Folder",
                Image = Properties.Resources.add
            };
            addIcon.Click += new System.EventHandler(addIcon_Click);
            changeDimension = new ToolStripMenuItem
            {
                Size = new Size(140, 30),
                Text = "Options",
                Image = Properties.Resources.resize
            };
            changeDimension.Click += new System.EventHandler(changeDimension_Click);
            contextMenuStrip.Items.AddRange(new ToolStripItem[] { addIcon, changeDimension });
            ContextMenuStrip = contextMenuStrip;
            CreateIcons();

            cleaner = new Timer()
            {
                Enabled = true,
                Interval = 5000,
            };
            cleaner.Tick += Clean;
            calls = new Timer() { Enabled = true, Interval = 60 };
            calls.Tick += (o, e) =>
            {
                const string RegPath = @"CyanLauncher";
                bool wasCalled = false;
                using (var key = Registry.CurrentUser.OpenSubKey(RegPath))
                {
                    if (key != null)
                    {
                        var value = key.GetValue(AppDomain.CurrentDomain.BaseDirectory);
                        wasCalled = value is int i && i == 1;
                        if (wasCalled)
                        {
                            try
                            {
                                Registry.CurrentUser.DeleteSubKeyTree(RegPath, false);
                            }
                            catch { }

                            Visible = true;
                            WindowState = FormWindowState.Normal;
                            relocate();
                            SizeChanged += new EventHandler(this.Frontal_SizeChanged);
                            Focus();
                            SetForegroundWindow(this.Handle);
                            TopMost = true;
                            ShowInTaskbar = true;
                        }
                    }
                }
            };

            slow = new Timer() { Enabled = true, Interval = 200 };
            slow.Tick += (o, e) =>
            {
                if (!AddIcon.active && !ChangeDimensions.active && !TopMost) { TopMost = true; }
                else if ((AddIcon.active && !add_icon_window.TopMost) || (ChangeDimensions.active && !change_dim_window.TopMost))
                {
                    TopMost = false;
                    if (AddIcon.active) { SetForegroundWindow(add_icon_window.Handle); add_icon_window.TopMost = true; }
                    if (ChangeDimensions.active) { SetForegroundWindow(change_dim_window.Handle); change_dim_window.TopMost = true; }
                }

                if (Program.current_location != Location && WindowState != FormWindowState.Minimized)
                {
                    Program.current_location = Location;
                    Program.current_size = Size;
                    Program.saveSettings();
                }
            };

            SetDimensions(Program.dimensions);
            relocate();
            this.SizeChanged += new EventHandler(this.Frontal_SizeChanged);
            SetForegroundWindow(this.Handle);
            if (!Program.initial_call) WindowState = FormWindowState.Minimized;
            Program.initial_call = true;
        }

        public void setOpacity(int level)
        {
            int values_window = 20;  // percentage
            Opacity = (double)((float)(level + 1) / 1000) * values_window + (double)(100 - values_window) / 100;
        }

        private bool isLink(string file)
        {
            if (file.Contains(".lnk")) return true;
            return false;
        }
        /*protected override void SetVisibleCore(bool value)
        {
            base.SetVisibleCore(allowshowdisplay ? value : allowshowdisplay);
        }*/

        public void SetDimensions(Size dim)
        {
            Program.dimensions = dim;
            maxIcon_on_row = Program.dimensions.Width;
            maxIcon_on_col = Program.dimensions.Height;
            Program.Save();
            SizeChanged -= new EventHandler(this.Frontal_SizeChanged);
            ClientSize = new Size(maxIcon_on_row * Program.iconSize.Width + (maxIcon_on_row + 1) * offsetX + 10, 
                maxIcon_on_col * Program.iconSize.Height + (maxIcon_on_col + 1) * offsetX + 10);
            panel1.Size = new Size(ClientSize.Width - 10, ClientSize.Height - 10);
            toScreenCenter();
            SizeChanged += new EventHandler(this.Frontal_SizeChanged);
            IconResize();
        }

        public void Drag()
        {
            bool active = Program.allowsDrag;
            foreach (Icon ico in panel1.Controls)
            {
                ControlExtension.Draggable(ico, active);
            }
        }

        private void changeDimension_Click(object sender, EventArgs e)
        {
            if (ChangeDimensions.active) return;
            change_dim_window = new ChangeDimensions(this);
            change_dim_window.Show();
        }

        private void Clean(object sender, EventArgs e)
        {
            return;
            int iconsRemoved = 0;
            for (int i = 0; i < Program.INFO.Count; i++)
            {
                if(!System.IO.File.Exists(Program.INFO[i].exepath) && !System.IO.Directory.Exists(Program.INFO[i].exepath))
                {
                    if(Program.INFO[i].exepath == "")
                    {
                        Program.INFO.RemoveAt(i);
                        Program.Save();
                    }
                    else
                    {
                        iconsRemoved += 1;
                        foreach (Icon ico in iconList)
                        {
                            if (ico.exePath == Program.INFO[i].exepath)
                            {
                                panel1.Controls.Remove(ico);
                                iconList.Remove(ico);
                                Program.INFO.RemoveAt(i);
                                Program.Save();
                                break;
                            }

                        }
                    }

                }
            }
            if(iconsRemoved != 0) IconResize();
        }

        private void CreateIcons()
        {
            for (int i=0; i< Program.INFO.Count; i++)
            {
                try
                {
                    iconList.Add(new Icon(Program.INFO[i].exepath, Program.INFO[i].name,
                        Program.INFO[i].imgpath, Program.INFO[i].as_admin));

                }
                catch (Exception e) { Console.WriteLine("EXCEPTION: "+ e.Message); }
            }
            Program.Save();
            Console.WriteLine("___________________________");
            Console.WriteLine("ICON ADDED");
            foreach (Icon ico in iconList) { panel1.Controls.Add(ico); ico.Print(); }
            Console.WriteLine("___________________________");
            IconResize();
            Drag();
        }

        public void addIcon_Click(object s, EventArgs e)
        {
            if (AddIcon.active) return;
            add_icon_window = new AddIcon();
            add_icon_window.Show();
        }
        public void addIcon_Click(Icon icon)
        {
            if (AddIcon.active) return;
            int i = 0;
            for (i = 0; i < iconList.Count; i++) if (iconList[i] == icon) break;
            add_icon_window = new AddIcon(icon, i);
            add_icon_window.pictureBox1.Image = icon.pic;
            add_icon_window.imagePath = icon.imgPath;
            add_icon_window.textBox1.Text = icon.exePath;
            add_icon_window.textBox2.Text = icon.name;
            add_icon_window.checkBox1.Checked = icon.as_admin_bool;
            add_icon_window.Show();
        }

        private void panel1_DragEnter(object sender, DragEventArgs e)
        {
            e.Effect = DragDropEffects.Link;
        }
        private void Frontal_SizeChanged(object sender, EventArgs e)
        {
            Console.WriteLine("SizeChanged");
            if (WindowState == FormWindowState.Minimized)
            {
                SizeChanged -= new EventHandler(this.Frontal_SizeChanged);
                System.Threading.Thread.Sleep(200);
                ShowInTaskbar = false;
                Visible = false;
            }
        }

        public void RemoveIcon(Icon icon)
        {
            string exePath = icon.exePath;
            for (int i = 0; i < iconList.Count; i++)
            {
                if (iconList[i].exePath == exePath)
                {
                    panel1.Controls.Remove(icon);
                    iconList.Remove(icon);
                    IconResize();
                    break;
                }
            }
            for (int i = 0; i < Program.INFO.Count; i++)
            {
                if (Program.INFO[i].exepath == exePath)
                {
                    Program.INFO.RemoveAt(i);
                    Program.Save();
                    return;
                }
            }
        }

        public void AddIcon_(Icon icon, Icon prev_icon = null)
        {
            int index = 0;
            foreach(Icon ico in iconList)
            {
                if (ico == prev_icon)
                {
                    try
                    {
                        Program.INFO.RemoveAt(index);
                        iconList.Remove(ico);
                        panel1.Controls.Remove(ico);
                    }
                    catch (Exception e) { }
                    break;
                }
                index += 1;
            }
            Program.INFO.Insert(index, new Info(icon.exePath, icon.name, icon.imgPath, icon.as_admin));
            Program.Save();
            iconList.Insert(index, icon);
            panel1.Controls.Add(icon);
            Drag();
            IconResize();
        }

        public void IconRelocation()
        {
            if (iconList.Count == 0) return;
            List<Icon> SortedIcon = new List<Icon>();
            Icon LastIcon = iconList[0];
            foreach (Icon Icon in iconList)
            {
                Point min = new Point(100000, 100000);
                foreach (Icon icon in iconList)
                {
                    if (SortedIcon.Contains(icon)) continue;
                    if (icon.Location.Y < min.Y - LastIcon.Height/2) { LastIcon = icon; min = LastIcon.Location; }
                    else if (icon.Location.Y <= min.Y + LastIcon.Height / 2)
                    {
                        if (icon.Location.X <= min.X) { LastIcon = icon; min = LastIcon.Location; }
                    }
                }
                if (SortedIcon.Contains(LastIcon)) continue;
                else SortedIcon.Add(LastIcon);
            }
            foreach (Icon icon in iconList)
            {
                if (!SortedIcon.Contains(icon)) SortedIcon.Add(icon);
            }
            for (int i = 0; i < SortedIcon.Count; i++)
            {
                Icon icon = SortedIcon[i];
                Program.INFO[i].exepath = icon.exePath;
                Program.INFO[i].name = icon.name;
                Program.INFO[i].imgpath = icon.imgPath;
                Program.INFO[i].as_admin = icon.as_admin;
                Program.Save();
            }
            iconList.Clear();
            for (int i=0; i<SortedIcon.Count; i++) iconList.Add(SortedIcon[i]);
            SortedIcon.Clear();
            IconResize();
        }
        public void IconResize()
        {
            if (iconList.Count == 0) return;
            List<string> currentSizes = new List<string>();
            disableResizing = true;
            foreach (Icon icon in iconList)
            {
                icon.RefreshImg();
                currentSizes.Add(icon.currentSizeStr);
                icon.SetSize("small");
            }
            iconList[0].Location = new Point(offsetX, offsetX);
            for (int i = 1; i < iconList.Count; i++)
            {
                Point PartialLocation = iconList[i - 1].Location;
                if(i==1) PartialLocation = new Point(offsetX, offsetX);
                if (PartialLocation.X + 2 * iconList[i].Size.Width + 3 * offsetX <= Width)
                {
                    iconList[i].Location =
                        new Point(PartialLocation.X + iconList[i].Size.Width + offsetX, PartialLocation.Y);
                }
                else
                {
                    iconList[i].Location =
                        new Point(offsetX, PartialLocation.Y + iconList[i].Size.Height + offsetX);
                }
            }
            disableResizing = false;
        }

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        static extern uint RegisterWindowMessage(string lpString);
        static uint MESSAGE_ID = RegisterWindowMessage("MyUniqueMessageIdentifier");

        protected override void WndProc(ref Message message)
        {
            const int WM_SYSCOMMAND = 0x0112;
            const int SC_MOVE = 0xF010;

            switch (message.Msg)
            {
                case WM_SYSCOMMAND:
                        if (!Program.canMove)
                        {
                            int command = message.WParam.ToInt32() & 0xfff0;
                            if (command == SC_MOVE)
                                return;
                        }
                        break;

            }

            base.WndProc(ref message);
        }
    }
}
