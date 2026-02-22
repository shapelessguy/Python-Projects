using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Imaging;
using System.Drawing.Text;
using System.IO;
using System.Windows.Forms;

namespace CyanLauncher
{
    public class Icon : Panel
    {
        public string exePath = "";
        public string arguments = "";
        public string name = "";
        public string imgPath = "";
        public bool as_admin = false;
        public bool notFound = false;
        public string currentSizeStr = "small";
        public PictureBox picture;
        public Bitmap pic;
        public Bitmap pic_big;
        private ContextMenuStrip contextMenuStrip;
        private ToolStripMenuItem editIcon;
        private ToolStripMenuItem removeIcon;
        private ToolStripMenuItem run_otherWay;
        private bool isMouseOver = false;
        private System.Windows.Forms.Timer mouseTracker;
        Point prevPos;

        private void MouseTracker_Tick(object sender, EventArgs e)
        {
            if (Frontal.disableResizing) return;
            Point mousePos = Cursor.Position;
            Point localPos = this.PointToClient(mousePos);

            bool nowOver = this.ClientRectangle.Contains(localPos);

            if (nowOver && !isMouseOver)
            {
                SetSize("big");
            }
            else if (!nowOver && isMouseOver)
            {
                SetSize("small");
            }
        }

        public Icon(string exePath, string arguments, string name, string imgPath, bool as_admin)
        {
            if (mouseTracker == null)
            {
                System.Windows.Forms.Timer mouseTracker = new System.Windows.Forms.Timer();
                mouseTracker.Interval = 30; // check ~33 times per second
                mouseTracker.Tick += MouseTracker_Tick;
                mouseTracker.Start();
            }
            this.exePath = exePath;
            this.arguments = arguments;
            this.name = name;
            this.imgPath = imgPath;
            this.as_admin = as_admin;
            string exeText = Program.GetExeText(exePath);
            if (!File.Exists(exeText) && !Directory.Exists(exeText)) notFound = true;
            RefreshImg();
            BackgroundImageLayout = ImageLayout.Center;
            picture = new PictureBox()
            {
                Image = System.Drawing.Bitmap.FromFile(imgPath),
                SizeMode = System.Windows.Forms.PictureBoxSizeMode.StretchImage,
            };
            SizeChanged += (o, e) => {
                picture.Size = Size;
            };
            MouseDown += (o, e) => {
                BringToFront();
                prevPos = Program.frontal.PointToClient(MousePosition);
            };
            MouseUp += (o, e) => 
            {
                Point newPos = Program.frontal.PointToClient(MousePosition);
                if (Program.allowsDrag && prevPos != newPos)
                {
                    Program.frontal.IconRelocation();
                }
                else if (
                    e.Button == MouseButtons.Left &&
                    Math.Abs(prevPos.X - newPos.X) < 15 && Math.Abs(prevPos.Y - newPos.Y) < 15)
                {
                    Mouse_Click(true);
                }
            };
            //picture.MouseClick += Mouse_Click;

            contextMenuStrip = new ContextMenuStrip
            {
                ImageScalingSize = new System.Drawing.Size(24, 24),
                Name = "contextMenuStrip1",
                Size = new System.Drawing.Size(141, 34)
            };
            editIcon = new ToolStripMenuItem
            {
                Size = new System.Drawing.Size(140, 30),
                Text = "Edit",
                Image = Properties.Resources.Edit_icon
            };
            editIcon.Click += new System.EventHandler(EditIcon_Click);
            removeIcon = new ToolStripMenuItem
            {
                Size = new System.Drawing.Size(140, 30),
                Text = "Remove Program",
                Image = Properties.Resources.delete_icon
            };
            removeIcon.Click += new System.EventHandler(RemoveIcon_Click);

            Image admin_image = Properties.Resources.admin;
            if (as_admin) admin_image = Properties.Resources.admin_no;
            run_otherWay = new ToolStripMenuItem
            {
                Size = new System.Drawing.Size(140, 30),
                Text = "Run as administrator",
                Image = admin_image
            };
            if (as_admin) run_otherWay.Text = "Run without admin privileges";
            run_otherWay.Click += new EventHandler(Run_otherWay_Click);
            contextMenuStrip.Items.AddRange(new ToolStripItem[] { editIcon, run_otherWay, removeIcon });
            ContextMenuStrip = contextMenuStrip;
        }

        public void RefreshImg()
        {
            string withoutExt = Path.Combine(new string[] { Directory.GetParent(imgPath).FullName, Path.GetFileNameWithoutExtension(imgPath) });
            string specImg = withoutExt + Program.iconSize.Width + ".ico";
            string specImg_big = withoutExt + Program.iconSize.Width + "_big.ico";

            if (!File.Exists(specImg)) Compress(imgPath, Program.iconSize.Width, Program.iconSize.Height, specImg);
            if (!File.Exists(specImg_big)) Compress(imgPath, Program.iconSize.Width + 6, Program.iconSize.Height + 6, specImg_big);

            pic = new Bitmap(specImg);
            pic_big = new Bitmap(specImg_big);
            //pic = new Bitmap(pic, new Size(Program.iconSize.Width, Program.iconSize.Height));
            //pic_big = new Bitmap(pic, new Size(Program.iconSize.Width + 6, Program.iconSize.Height + 6));
            BackgroundImage = pic;
        }
        private void addNotFound(Graphics g, int width, int height)
        {
            GraphicsPath p = new GraphicsPath();
            int fontSize = (int)(width * 0.15f);
            StringFormat format = new StringFormat(StringFormatFlags.FitBlackBox);
            format.Alignment = StringAlignment.Center;
            format.LineAlignment = StringAlignment.Far;
            p.AddString(
                "-NotFound-",
                FontFamily.GenericSansSerif,
                (int)FontStyle.Bold,
                fontSize,
                new Rectangle(0, (int)((float)height / 100 * 30), width, (int)((float)height / 100 * 40)),
                format);
            g.InterpolationMode = InterpolationMode.High;
            g.SmoothingMode = SmoothingMode.HighQuality;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            g.CompositingQuality = CompositingQuality.HighQuality;
            Pen pen = new Pen(Brushes.White);
            pen.Width = 5.0f;
            g.DrawPath(pen, p);
            g.FillPath(Brushes.Red, p);
        }

        
        private void addFlags(Graphics g, int width, int height)
        {
            int flag_length = (int)((float)width * 0.2);
            Image image = null;
            if (Path.GetExtension(exePath) == ".lnk") image = Properties.Resources.link;
            else if (Directory.Exists(exePath)) image = Properties.Resources.folder;
            else if (exePath.StartsWith("python:")) image = Properties.Resources.python;
            else if (exePath.StartsWith("chrome:")) image = Properties.Resources.chrome;
            if (image != null)
            {
                g.DrawImage(image, 0, height - flag_length, flag_length, flag_length);
            }
        }

        private void addAdmin(Graphics g, int width, int height)
        {
            int flag_length = (int)((float)width * 0.4);
            Image image = Properties.Resources.admin;
            g.DrawImage(image, width - flag_length, 0, flag_length, flag_length);
        }

        public void SetSize(string size)
        {
            if(size == "big")
            {
                isMouseOver = true;
                currentSizeStr = "big";
                Location = new Point(Location.X - 3, Location.Y - 3);
                int new_width = Program.iconSize.Width + 6;
                int new_height = Program.iconSize.Height + 6;
                int fontSize = (int)(new_width * 0.1f);
                Size = new Size(new_width, new_height);
                BackgroundImage = pic_big;
                using (Graphics g = Graphics.FromImage(BackgroundImage))
                {
                    addFlags(g, new_width, new_height);
                    if (as_admin) addAdmin(g, new_width, new_height);
                    if (notFound) addNotFound(g, new_width, new_height);

                    GraphicsPath p = new GraphicsPath();
                    StringFormat format = new StringFormat(StringFormatFlags.FitBlackBox);
                    format.Alignment = StringAlignment.Center;
                    format.LineAlignment = StringAlignment.Far;
                    p.AddString(
                        name,
                        FontFamily.GenericSansSerif,
                        (int)FontStyle.Bold,
                        fontSize,
                        new Rectangle(0, (int)((float)new_height / 100 * 70), new_width, (int)((float)new_height / 100 * 30)),
                        format);
                    g.InterpolationMode = InterpolationMode.High;
                    g.SmoothingMode = SmoothingMode.HighQuality;
                    g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit; 
                    g.CompositingQuality = CompositingQuality.HighSpeed;
                    Pen pen = new Pen(Brushes.Black);
                    pen.Width = 4.0f;
                    g.DrawPath(pen, p);
                    g.FillPath(Brushes.White, p);
                }
            }
            else
            {
                isMouseOver = false;
                currentSizeStr = "small";
                Location = new Point(Location.X + 3, Location.Y + 3);
                Size = new Size(Program.iconSize.Width, Program.iconSize.Height);
                BackgroundImage = pic;
                using (Graphics g = Graphics.FromImage(BackgroundImage))
                {
                    addFlags(g, Program.iconSize.Width, Program.iconSize.Height);
                    if (as_admin) addAdmin(g, Program.iconSize.Width, Program.iconSize.Height);
                    if (notFound) addNotFound(g, Program.iconSize.Width, Program.iconSize.Height);
                }
            }
        }

        private void EditIcon_Click(object sender, EventArgs e)
        {
            Program.frontal.addIcon_Click(this);
        }
        private void RemoveIcon_Click(object sender, EventArgs e)
        {
            Program.frontal.RemoveIcon(this);
            Dispose();
        }

        private void Run_otherWay_Click(object sender, EventArgs e)
        {
            Mouse_Click(false);
        }

        private void SendToLauncher(string executableString, bool as_admin)
        {
            string folder = Program.tempDataPath;
            if (as_admin) folder = Program.tempDataPathAdmin;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(folder));
                File.WriteAllText(folder, executableString);
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Error: {ex.Message}");
            }

        }

        private void Mouse_Click(bool left)
        {
            string exeText = Program.GetExeText(exePath);
            string exeType = Program.GetExeType(exePath);
            if (exeType == "folder") SendToLauncher($"explorer.exe \"{exeText}\"", false);
            else
            {
                bool ad = as_admin;
                if (!left) ad = !ad;
                if (!File.Exists(exeText))
                {
                    MessageBox.Show("File or directory not found!");
                    return;
                }

                if (exeType == "exe") SendToLauncher($"\"{exeText}\" " + arguments, ad);
                else if (exeType == "python") SendToLauncher($"python \"{exeText}\" " + arguments, ad);
            }

            try
            {
                if (Program.vanish) Program.frontal.Close();
            }
            catch (Exception) 
            { 
                Console.WriteLine("EXC");
            }
        }
        public static void Compress(string image_path, int width, int height, string dest_path = "")
        {
            try
            {
                if (dest_path == "") dest_path = image_path;
                Bitmap btm = new Bitmap(image_path);
                btm = new Bitmap(btm, new Size(width, height));
                btm.Save(dest_path, ImageFormat.Icon);
            }
            catch (Exception e) { Console.WriteLine("EXCEPTION: "+ e.Message); }
        }

        public void Print()
        {
            Console.WriteLine("Path: " + exePath + ", args: " + arguments + ", name: " + name + ", imgPath: " + imgPath);
        }
    }
}
