using Microsoft.Win32;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace Timer
{
    /// <summary>
    /// A countdown opened by CyanManager's SHOW_ALARM: type a time, Enter starts it, and when it ends
    /// HKCU\CyanHotkey "alarm" = "ALARM" tells CyanManager's Hotkeys service to ring the alarm.
    /// Before it starts it closes when it loses focus (it is a quick pop-up), but only once it had focus.
    /// </summary>
    public partial class TimerWin : Form
    {
        // CyanManager's page colours (web_ui/src/styles.css)
        internal static readonly Color Bg = Color.FromArgb(0x15, 0x1a, 0x20);
        internal static readonly Color Surface = Color.FromArgb(0x1b, 0x21, 0x29);
        internal static readonly Color Line = Color.FromArgb(0x33, 0x3d, 0x4a);
        internal static readonly Color TextColor = Color.FromArgb(0xe7, 0xeb, 0xf0);
        internal static readonly Color Muted = Color.FromArgb(0x74, 0x80, 0x8f);
        internal static readonly Color Accent = Color.FromArgb(0x2e, 0xc4, 0xd6);
        internal static readonly Color Bad = Color.FromArgb(0xff, 0x6b, 0x6b);

        const string RegPath = "CyanHotkey";
        const int CloseAfterAlarmMs = 3000;

        readonly TimeDisplay display;
        readonly TextBox notes;
        readonly System.Windows.Forms.Timer tick, clearRegistry;
        readonly ToolTip tips;

        bool started, alerting, hadFocus, closeHover;
        DateTime end, alarmSetAt = DateTime.MinValue, alarmTime;
        TimeSpan total;

        /// <summary>Counting down (or ringing): a newer timer leaves it open.</summary>
        public bool Started => started;

        public TimerWin()
        {
            InitializeComponent();
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            ShowInTaskbar = false;
            TopMost = true;
            KeyPreview = true;
            DoubleBuffered = true;
            BackColor = Bg;
            ClientSize = new Size(LogicalToDeviceUnits(360), LogicalToDeviceUnits(196));

            tips = new ToolTip(components);
            display = new TimeDisplay { TabIndex = 0 };
            tips.SetToolTip(display, "Type the time · ← → field · ↑ ↓ or wheel to change · Enter to start");
            notes = new TextBox
            {
                BorderStyle = BorderStyle.None,
                BackColor = Surface,
                ForeColor = TextColor,
                Font = new Font("Segoe UI", 10.5F),
                PlaceholderText = "Label (optional)",
                TabIndex = 1,
            };
            Controls.Add(display);
            Controls.Add(notes);
            LayoutControls();

            tick = new System.Windows.Forms.Timer(components) { Interval = 100 };
            tick.Tick += (_, _) => OnTick();

            // CyanManager deletes the key when it reads it; this only clears an alarm nobody read.
            DeleteAlarm();
            clearRegistry = new System.Windows.Forms.Timer(components) { Interval = 200, Enabled = true };
            clearRegistry.Tick += (_, _) =>
            {
                if (alarmSetAt != DateTime.MinValue && DateTime.UtcNow - alarmSetAt > TimeSpan.FromMilliseconds(1500))
                {
                    DeleteAlarm();
                    alarmSetAt = DateTime.MinValue;
                }
            };

            Activated += (_, _) => hadFocus = true;
            Shown += (_, _) =>
            {
                // Here, not in the constructor: the window must be on screen to take the foreground.
                Activate();
                SetForegroundWindow(Handle);
                display.Focus();
            };
            FormClosing += (_, _) => { tick.Stop(); clearRegistry.Stop(); };
        }

        // ---- Window chrome: rounded corners, shadow, dragging ----

        protected override CreateParams CreateParams
        {
            get
            {
                var cp = base.CreateParams;
                cp.ClassStyle |= 0x20000; // CS_DROPSHADOW
                return cp;
            }
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            try
            {
                int round = 2; // DWMWCP_ROUND (Windows 11)
                DwmSetWindowAttribute(Handle, 33, ref round, sizeof(int));
                int border = Line.R | (Line.G << 8) | (Line.B << 16); // COLORREF
                DwmSetWindowAttribute(Handle, 34, ref border, sizeof(int));
            }
            catch { /* older Windows: square corners */ }
        }

        Rectangle CloseRect => new(ClientSize.Width - LogicalToDeviceUnits(40), LogicalToDeviceUnits(8),
                                   LogicalToDeviceUnits(30), LogicalToDeviceUnits(26));

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            if (e.Button != MouseButtons.Left) return;
            if (CloseRect.Contains(e.Location)) { Close(); return; }
            ReleaseCapture();
            SendMessage(Handle, 0xA1 /* WM_NCLBUTTONDOWN */, (IntPtr)2 /* HTCAPTION */, IntPtr.Zero);
        }

        protected override void OnMouseMove(MouseEventArgs e)
        {
            base.OnMouseMove(e);
            bool hover = CloseRect.Contains(e.Location);
            if (hover != closeHover) { closeHover = hover; Invalidate(CloseRect); }
        }

        protected override void OnMouseLeave(EventArgs e)
        {
            base.OnMouseLeave(e);
            if (closeHover) { closeHover = false; Invalidate(CloseRect); }
        }

        void LayoutControls()
        {
            int pad = LogicalToDeviceUnits(20);
            display.Bounds = new Rectangle(pad, LogicalToDeviceUnits(40), ClientSize.Width - 2 * pad, LogicalToDeviceUnits(86));
            int nh = notes.PreferredHeight;
            notes.Bounds = new Rectangle(pad + LogicalToDeviceUnits(12), LogicalToDeviceUnits(146) + (LogicalToDeviceUnits(32) - nh) / 2,
                                         ClientSize.Width - 2 * pad - LogicalToDeviceUnits(24), nh);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            int pad = LogicalToDeviceUnits(20);

            // Header
            using (var f = new Font("Segoe UI Semibold", 8.5F))
            using (var b = new SolidBrush(alerting ? Bad : started ? Accent : Muted))
            {
                string head = alerting ? "TIME'S UP" : started ? "RUNNING" : "TIMER";
                g.DrawString(head, f, b, pad - LogicalToDeviceUnits(2), LogicalToDeviceUnits(14));
            }

            // Close button
            var cr = CloseRect;
            if (closeHover)
                using (var hb = new SolidBrush(Color.FromArgb(40, Bad)))
                using (var path = Rounded(cr, LogicalToDeviceUnits(6)))
                    g.FillPath(hb, path);
            using (var pen = new Pen(closeHover ? Bad : Muted, LogicalToDeviceUnits(2)) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                int cx = cr.X + cr.Width / 2, cy = cr.Y + cr.Height / 2, d = LogicalToDeviceUnits(5);
                g.DrawLine(pen, cx - d, cy - d, cx + d, cy + d);
                g.DrawLine(pen, cx + d, cy - d, cx - d, cy + d);
            }

            var box = new Rectangle(pad, LogicalToDeviceUnits(146), ClientSize.Width - 2 * pad, LogicalToDeviceUnits(32));
            if (!started)
            {
                // The label's field
                using var path = Rounded(box, LogicalToDeviceUnits(7));
                using var fill = new SolidBrush(Surface);
                using var pen = new Pen(notes.Focused ? Accent : Line);
                g.FillPath(fill, path);
                g.DrawPath(pen, path);
            }
            else
            {
                // The label, then how much is left as a bar
                if (notes.Text.Length > 0)
                    using (var f = new Font("Segoe UI", 10.5F))
                    using (var b = new SolidBrush(TextColor))
                    {
                        var fmt = new StringFormat { Alignment = StringAlignment.Center, Trimming = StringTrimming.EllipsisCharacter, FormatFlags = StringFormatFlags.NoWrap };
                        g.DrawString(notes.Text, f, b, new RectangleF(box.X, box.Y - LogicalToDeviceUnits(4), box.Width, box.Height), fmt);
                    }
                var bar = new Rectangle(pad, ClientSize.Height - LogicalToDeviceUnits(18), ClientSize.Width - 2 * pad, LogicalToDeviceUnits(4));
                using (var track = new SolidBrush(Surface)) using (var p = Rounded(bar, bar.Height / 2)) g.FillPath(track, p);
                double left = alerting ? 0 : Math.Clamp((end - DateTime.Now).TotalMilliseconds / total.TotalMilliseconds, 0, 1);
                if (left > 0)
                {
                    var fillRect = new Rectangle(bar.X, bar.Y, Math.Max(bar.Height, (int)(bar.Width * left)), bar.Height);
                    using var fb = new SolidBrush(Accent);
                    using var p = Rounded(fillRect, bar.Height / 2);
                    g.FillPath(fb, p);
                }
            }
        }

        internal static GraphicsPath Rounded(Rectangle r, int radius)
        {
            int d = radius * 2;
            var p = new GraphicsPath();
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        // ---- Behaviour ----

        protected override void OnDeactivate(EventArgs e)
        {
            base.OnDeactivate(e);
            // A pop-up dismissed by clicking elsewhere; never before it had focus at all,
            // which is when it would vanish as soon as it appeared.
            if (!started && hadFocus) Close();
        }

        protected override bool ProcessCmdKey(ref Message msg, Keys keyData)
        {
            if (keyData == Keys.Escape) { Close(); return true; }
            if (keyData == Keys.Enter && !started) { Start(); return true; }
            return base.ProcessCmdKey(ref msg, keyData);
        }

        protected override void OnControlAdded(ControlEventArgs e)
        {
            base.OnControlAdded(e);
            e.Control!.GotFocus += (_, _) => Invalidate();
            e.Control.LostFocus += (_, _) => Invalidate();
        }

        void Start()
        {
            var t = display.Value;
            if (t <= TimeSpan.Zero) { display.Shake(); return; }
            started = true;
            total = t;
            end = DateTime.Now + t;
            notes.Visible = false;
            display.Running = true;
            display.Focus();
            tick.Start();
            OnTick();
        }

        void OnTick()
        {
            if (!alerting)
            {
                var left = end - DateTime.Now;
                if (left <= TimeSpan.Zero)
                {
                    alerting = true;
                    alarmTime = DateTime.Now;
                    display.Value = TimeSpan.Zero;
                    display.Alert = true;
                    SetAlarm();
                }
                else
                {
                    display.Value = TimeSpan.FromSeconds(Math.Ceiling(left.TotalSeconds));
                }
            }
            else
            {
                display.Blink = (DateTime.Now - alarmTime).TotalMilliseconds % 600 < 300;
                if ((DateTime.Now - alarmTime).TotalMilliseconds > CloseAfterAlarmMs) Close();
            }
            Invalidate();
        }

        void SetAlarm()
        {
            try
            {
                using var k = Registry.CurrentUser.CreateSubKey(RegPath);
                k.SetValue("alarm", "ALARM", RegistryValueKind.String);
                alarmSetAt = DateTime.UtcNow;
            }
            catch { }
        }

        static void DeleteAlarm()
        {
            try
            {
                using var k = Registry.CurrentUser.OpenSubKey(RegPath, writable: true);
                k?.DeleteValue("alarm", false);
            }
            catch { }
        }

        [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll")] static extern bool ReleaseCapture();
        [DllImport("user32.dll")] static extern IntPtr SendMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    }

    /// <summary>
    /// The big H:MM:SS. Before the start it is the editor: one field selected, digits typed into it
    /// (two fill it and move on), ← → between fields, ↑ ↓ or the wheel to change one, a click to pick one.
    /// </summary>
    internal class TimeDisplay : Control
    {
        static readonly int[] Max = { 99, 59, 59 };
        readonly int[] vals = new int[3];
        int field = 1;        // 0 hours, 1 minutes, 2 seconds: minutes first, the usual case
        bool typedOne;        // the selected field has one digit typed so far
        bool running, alert, blink;
        int shakeLeft;
        readonly System.Windows.Forms.Timer shakeT;
        RectangleF[] fieldRects = new RectangleF[3];

        public TimeDisplay()
        {
            SetStyle(ControlStyles.AllPaintingInWmPaint | ControlStyles.OptimizedDoubleBuffer | ControlStyles.UserPaint |
                     ControlStyles.Selectable | ControlStyles.ResizeRedraw, true);
            BackColor = TimerWin.Bg;
            Cursor = Cursors.IBeam;
            shakeT = new System.Windows.Forms.Timer { Interval = 30 };
            shakeT.Tick += (_, _) => { if (--shakeLeft <= 0) shakeT.Stop(); Invalidate(); };
        }

        [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
        public TimeSpan Value
        {
            get => new(vals[0], vals[1], vals[2]);
            set
            {
                vals[0] = Math.Min(99, (int)value.TotalHours);
                vals[1] = value.Minutes;
                vals[2] = value.Seconds;
                Invalidate();
            }
        }

        [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
        public bool Running { get => running; set { running = value; Cursor = value ? Cursors.Default : Cursors.IBeam; Invalidate(); } }
        [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
        public bool Alert { get => alert; set { alert = value; Invalidate(); } }
        [System.ComponentModel.DesignerSerializationVisibility(System.ComponentModel.DesignerSerializationVisibility.Hidden)]
        public bool Blink { get => blink; set { if (blink != value) { blink = value; Invalidate(); } } }

        public void Shake() { shakeLeft = 10; shakeT.Start(); }

        protected override bool IsInputKey(Keys keyData) =>
            keyData is Keys.Left or Keys.Right or Keys.Up or Keys.Down || base.IsInputKey(keyData);

        protected override void OnKeyDown(KeyEventArgs e)
        {
            base.OnKeyDown(e);
            if (running) return;
            switch (e.KeyCode)
            {
                case Keys.Left: Select(Math.Max(0, field - 1)); break;
                case Keys.Right: Select(Math.Min(2, field + 1)); break;
                case Keys.Up: Step(+1); break;
                case Keys.Down: Step(-1); break;
                case Keys.Back:
                case Keys.Delete: vals[field] = 0; typedOne = false; break;
                default:
                    int d = e.KeyCode is >= Keys.D0 and <= Keys.D9 ? e.KeyCode - Keys.D0
                          : e.KeyCode is >= Keys.NumPad0 and <= Keys.NumPad9 ? e.KeyCode - Keys.NumPad0 : -1;
                    if (d < 0) return;
                    if (!typedOne) { vals[field] = d; typedOne = true; }
                    else
                    {
                        vals[field] = Math.Min(Max[field], vals[field] * 10 + d);
                        typedOne = false;
                        if (field < 2) field++;
                    }
                    break;
            }
            e.Handled = e.SuppressKeyPress = true;
            Invalidate();
        }

        void Select(int f) { field = f; typedOne = false; Invalidate(); }

        void Step(int delta)
        {
            int n = Max[field] + 1;
            vals[field] = ((vals[field] + delta) % n + n) % n;
            typedOne = false;
            Invalidate();
        }

        int FieldAt(Point p)
        {
            for (int i = 0; i < 3; i++)
                if (p.X < fieldRects[i].Right + 6) return i;
            return 2;
        }

        protected override void OnMouseDown(MouseEventArgs e)
        {
            base.OnMouseDown(e);
            Focus();
            if (!running) Select(FieldAt(e.Location));
        }

        protected override void OnMouseWheel(MouseEventArgs e)
        {
            base.OnMouseWheel(e);
            if (running) return;
            field = FieldAt(e.Location);
            Step(e.Delta > 0 ? +1 : -1);
        }

        protected override void OnGotFocus(EventArgs e) { base.OnGotFocus(e); Invalidate(); }
        protected override void OnLostFocus(EventArgs e) { base.OnLostFocus(e); Invalidate(); }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.Clear(BackColor);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.AntiAliasGridFit;

            using var font = new Font("Segoe UI Semibold", 40F, GraphicsUnit.Point);
            using var colonFont = new Font("Segoe UI Light", 36F, GraphicsUnit.Point);
            var fmt = StringFormat.GenericTypographic;
            string[] parts = { vals[0].ToString("00"), vals[1].ToString("00"), vals[2].ToString("00") };

            // Each field is two digits wide whatever they are (Segoe UI's digits are all one width)
            SizeF digits = g.MeasureString("00", font, PointF.Empty, fmt);
            SizeF colon = g.MeasureString(":", colonFont, PointF.Empty, fmt);
            float gap = LogicalToDeviceUnits(10);
            float fieldW = digits.Width + gap * 2;
            float totalW = fieldW * 3 + colon.Width * 2;
            float x = (Width - totalW) / 2 + (shakeLeft > 0 ? (shakeLeft % 2 == 0 ? 6 : -6) : 0);
            float y = (Height - digits.Height) / 2 - LogicalToDeviceUnits(2);

            Color digitColor = alert ? (blink ? TimerWin.Bad : Color.FromArgb(120, TimerWin.Bad))
                             : running ? TimerWin.Accent : TimerWin.TextColor;

            for (int i = 0; i < 3; i++)
            {
                var r = new RectangleF(x, y - LogicalToDeviceUnits(6), fieldW, digits.Height + LogicalToDeviceUnits(12));
                fieldRects[i] = r;
                bool selected = !running && Focused && i == field;
                if (selected)
                {
                    using var path = TimerWin.Rounded(Rectangle.Round(r), LogicalToDeviceUnits(10));
                    using var fill = new SolidBrush(Color.FromArgb(36, TimerWin.Accent));
                    using var pen = new Pen(Color.FromArgb(150, TimerWin.Accent), LogicalToDeviceUnits(1));
                    g.FillPath(fill, path);
                    g.DrawPath(pen, path);
                }
                using (var b = new SolidBrush(selected ? TimerWin.Accent : digitColor))
                    g.DrawString(parts[i], font, b, x + gap, y, fmt);
                if (selected && typedOne)
                {
                    // One digit typed: a caret under the field says the second is awaited
                    using var cb = new SolidBrush(TimerWin.Accent);
                    g.FillRectangle(cb, x + gap, r.Bottom - LogicalToDeviceUnits(5), digits.Width, LogicalToDeviceUnits(2));
                }
                x += fieldW;
                if (i < 2)
                {
                    using var cbrush = new SolidBrush(running || alert ? Color.FromArgb(140, digitColor) : TimerWin.Muted);
                    g.DrawString(":", colonFont, cbrush, x, y + (digits.Height - colon.Height) / 2 - LogicalToDeviceUnits(6), fmt);
                    x += colon.Width;
                }
            }
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) shakeT.Dispose();
            base.Dispose(disposing);
        }
    }
}
