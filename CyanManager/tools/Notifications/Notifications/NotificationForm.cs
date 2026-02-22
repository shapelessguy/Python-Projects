using System.ComponentModel;
using System.Diagnostics;
using System.Drawing.Text;

namespace Notifications
{

    public partial class NotificationForm : Form
    {
        private const int WS_EX_LAYERED = 0x00080000;
        private const int WS_EX_TRANSPARENT = 0x00000020;

        protected override CreateParams CreateParams
        {
            get
            {
                CreateParams cp = base.CreateParams;
                cp.ExStyle |= WS_EX_LAYERED | WS_EX_TRANSPARENT;
                return cp;
            }
        }
        private void SetText(string title, string text)
        {
            var lbl = new RoundedLabel();
            lbl.ForeColor = Color.White;
            lbl.BackColor = TransparencyKey;
            lbl.Font = new Font("Modern No. 20", 23.9999962F, FontStyle.Bold, GraphicsUnit.Point, 0);
            lbl.Text = text;
            lbl.Location = new Point(132, 24);
            lbl.Padding = new Padding(30);
            lbl.AutoSize = false;
            using (Graphics g = CreateGraphics())
            {
                g.TextRenderingHint = TextRenderingHint.AntiAlias;
                SizeF textSize = g.MeasureString(text, lbl.Font, new SizeF(9999, lbl.Height - 25), StringFormat.GenericTypographic);
                int requiredWidth = (int)Math.Ceiling(textSize.Width * 1.1) + 60 + 50;
                lbl.Size = new Size(requiredWidth, 70);
            }
            Controls.Add(lbl);
        }
        public NotificationForm(string iconPath, string title, string message, int timeout)
        {
            InitializeComponent();
            FormBorderStyle = FormBorderStyle.None;
            TopMost = true;
            TransparencyKey = Color.FromArgb(1, 1, 1);
            BackColor = TransparencyKey;
            SetText(title, message);
            var closeTimer = new System.Windows.Forms.Timer
            {
                Interval = timeout,
                Enabled = true
            };

            closeTimer.Tick += (s, e) =>
            {
                closeTimer.Stop();
                closeTimer.Dispose();
                Application.Exit();
            };

            if (string.IsNullOrEmpty(iconPath) || !File.Exists(iconPath))  return;

            if (iconPath.EndsWith(".ico", StringComparison.OrdinalIgnoreCase)) {
                try
                {
                    using (Icon ico = new Icon(iconPath))
                    {
                        icon.BackgroundImage = ico.ToBitmap();
                        icon.BackgroundImageLayout = ImageLayout.Zoom;
                        Debug.WriteLine($"Loaded as .ico file: {iconPath}");
                        return;
                    }
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"Failed to load as icon: {ex.Message}");
                }
            }

            try
            {
                byte[] bytes = File.ReadAllBytes(iconPath);
                using (var ms = new MemoryStream(bytes))
                {
                    ms.Position = 0;
                    icon.BackgroundImage = Image.FromStream(ms);
                    icon.BackgroundImageLayout = ImageLayout.Zoom;
                }
                System.Diagnostics.Debug.WriteLine($"Icon loaded OK: {iconPath}");
                return;
            }
            catch (OutOfMemoryException ex)
            {
                System.Diagnostics.Debug.WriteLine($"Invalid image format: {iconPath}\n{ex.Message}");
            }
            catch (ArgumentException ex)
            {
                System.Diagnostics.Debug.WriteLine($"Invalid parameter / bad stream: {ex.Message}");
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Icon load failed: {ex}");
            }
        }

    }
}
