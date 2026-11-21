using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;

namespace KeyboardHotkeys
{
    /// <summary>The window's look: CyanManager's dark palette (web_ui/src/styles.css), laid out in code.</summary>
    public partial class HiddenWin
    {
        static readonly Color Bg = Color.FromArgb(0x15, 0x1a, 0x20);
        static readonly Color Surface = Color.FromArgb(0x1b, 0x21, 0x29);
        static readonly Color Surface3 = Color.FromArgb(0x23, 0x2a, 0x34);
        static readonly Color Line = Color.FromArgb(0x33, 0x3d, 0x4a);
        static readonly Color TextColor = Color.FromArgb(0xe7, 0xeb, 0xf0);
        static readonly Color Text2 = Color.FromArgb(0xaa, 0xb4, 0xc0);
        static readonly Color Muted = Color.FromArgb(0x74, 0x80, 0x8f);
        static readonly Color Accent = Color.FromArgb(0x2e, 0xc4, 0xd6);

        readonly Dictionary<TextBox, Panel> fieldHosts = new();
        Label? finderTitle, listTitle;

        /// <summary>A key as the page names it: Num 4, Vol +, Ctrl…</summary>
        internal static string KeyName(Keys k) => k switch
        {
            >= Keys.NumPad0 and <= Keys.NumPad9 => $"Num {k - Keys.NumPad0}",
            >= Keys.D0 and <= Keys.D9 => $"{k - Keys.D0}",
            Keys.Subtract => "Num −",
            Keys.Add => "Num +",
            Keys.Multiply => "Num *",
            Keys.Divide => "Num /",
            Keys.Decimal => "Num .",
            Keys.VolumeUp => "Vol +",
            Keys.VolumeDown => "Vol −",
            Keys.VolumeMute => "Mute",
            Keys.MediaNextTrack => "Next track",
            Keys.MediaPreviousTrack => "Prev track",
            Keys.MediaPlayPause => "Play/Pause",
            Keys.ControlKey or Keys.LControlKey or Keys.RControlKey => "Ctrl",
            Keys.ShiftKey or Keys.LShiftKey or Keys.RShiftKey => "Shift",
            Keys.Menu or Keys.LMenu or Keys.RMenu => "Alt",
            Keys.LWin or Keys.RWin => "Win",
            Keys.Return => "Enter",
            Keys.Back => "Backspace",
            Keys.Next => "PgDn",
            Keys.Prior => "PgUp",
            _ => k.ToString(),
        };

        void ApplyTheme()
        {
            SuspendLayout();
            Font = new Font("Segoe UI", 9.75F);
            BackColor = Bg;
            ForeColor = TextColor;
            ClientSize = new Size(LogicalToDeviceUnits(760), LogicalToDeviceUnits(560));
            MinimumSize = new Size(LogicalToDeviceUnits(620), LogicalToDeviceUnits(360));
            Text = "Keyboard Hotkeys";

            finderTitle = SectionLabel("KEY FINDER");
            listTitle = SectionLabel("BINDINGS");
            Controls.Add(finderTitle);
            Controls.Add(listTitle);

            foreach (var l in new[] { keyLabel, key_id_lbl, modifiers_lbl })
            {
                l.ForeColor = Muted;
                l.Font = new Font("Segoe UI Semibold", 8.25F);
                l.AutoSize = true;
            }
            keyLabel.Text = "PRESS A COMBINATION";
            key_id_lbl.Text = "KEY CODE";
            modifiers_lbl.Text = "MODIFIERS";

            foreach (var tb in new[] { keyRevealer, keyID, modifierID }) HostField(tb);
            keyRevealer.PlaceholderText = "Click here, then press the keys";
            keyID.ReadOnly = modifierID.ReadOnly = true;
            keyID.TextAlign = modifierID.TextAlign = HorizontalAlignment.Center;

            copy_btn.FlatStyle = FlatStyle.Flat;
            copy_btn.FlatAppearance.BorderColor = Line;
            copy_btn.FlatAppearance.MouseOverBackColor = Color.FromArgb(0x2c, 0x34, 0x40);
            copy_btn.FlatAppearance.MouseDownBackColor = Line;
            copy_btn.BackColor = Surface3;
            copy_btn.ForeColor = TextColor;
            copy_btn.Cursor = Cursors.Hand;
            copy_btn.Text = "Copy (key, mods)";

            StyleList();
            Resize += (_, _) => LayoutUi();
            ResumeLayout(false);
            LayoutUi();
        }

        Label SectionLabel(string text) => new()
        {
            Text = text,
            AutoSize = true,
            ForeColor = Text2,
            Font = new Font("Segoe UI Semibold", 8.5F),
            BackColor = Color.Transparent,
        };

        /// <summary>A borderless text box inside a rounded outline, cyan while it has focus.</summary>
        void HostField(TextBox tb)
        {
            var host = new Panel { BackColor = Bg, Padding = new Padding(LogicalToDeviceUnits(10), 0, LogicalToDeviceUnits(10), 0) };
            int index = Controls.GetChildIndex(tb);
            Controls.Remove(tb);
            tb.BorderStyle = BorderStyle.None;
            tb.BackColor = Surface;
            tb.ForeColor = TextColor;
            tb.Font = new Font("Segoe UI", 10.5F);
            host.Controls.Add(tb);
            Controls.Add(host);
            Controls.SetChildIndex(host, index);
            host.Paint += (_, e) =>
            {
                e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
                var r = new Rectangle(0, 0, host.Width - 1, host.Height - 1);
                using var path = Rounded(r, LogicalToDeviceUnits(7));
                using var fill = new SolidBrush(Surface);
                using var pen = new Pen(tb.Focused ? Accent : Line);
                e.Graphics.FillPath(fill, path);
                e.Graphics.DrawPath(pen, path);
            };
            host.Resize += (_, _) =>
            {
                tb.Width = host.ClientSize.Width - host.Padding.Horizontal;
                tb.Location = new Point(host.Padding.Left, (host.Height - tb.Height) / 2);
            };
            host.Click += (_, _) => tb.Focus();
            tb.GotFocus += (_, _) => host.Invalidate();
            tb.LostFocus += (_, _) => host.Invalidate();
            fieldHosts[tb] = host;
        }

        void StyleList()
        {
            var lv = combination_view;
            lv.Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right;
            lv.BorderStyle = BorderStyle.None;
            lv.BackColor = Surface;
            lv.ForeColor = TextColor;
            lv.FullRowSelect = true;
            lv.HeaderStyle = ColumnHeaderStyle.Nonclickable;
            lv.OwnerDraw = true;
            // Taller rows: a list's rows are as tall as its small image list
            lv.SmallImageList = new ImageList { ImageSize = new Size(1, LogicalToDeviceUnits(30)) };
            if (lv.Columns.Count >= 2)
            {
                lv.Columns[0].Text = "KEYS";
                lv.Columns[1].Text = "FUNCTION";
            }
            lv.HandleCreated += (_, _) => SetWindowTheme(lv.Handle, "DarkMode_Explorer", null);
            if (lv.IsHandleCreated) SetWindowTheme(lv.Handle, "DarkMode_Explorer", null);
            lv.Resize += (_, _) => FitColumns();

            lv.DrawColumnHeader += (_, e) =>
            {
                using (var bg = new SolidBrush(Surface)) e.Graphics.FillRectangle(bg, e.Bounds);
                using (var line = new Pen(Line)) e.Graphics.DrawLine(line, e.Bounds.Left, e.Bounds.Bottom - 1, e.Bounds.Right, e.Bounds.Bottom - 1);
                using var f = new Font("Segoe UI Semibold", 8.25F);
                var r = new Rectangle(e.Bounds.X + LogicalToDeviceUnits(14), e.Bounds.Y, e.Bounds.Width, e.Bounds.Height);
                TextRenderer.DrawText(e.Graphics, e.Header!.Text, f, r, Muted, TextFormatFlags.VerticalCenter | TextFormatFlags.Left);
            };
            lv.DrawItem += (_, e) => { /* the sub-items draw the row */ };
            lv.DrawSubItem += (_, e) =>
            {
                var g = e.Graphics;
                bool selected = e.Item!.Selected;
                using (var bg = new SolidBrush(selected ? Color.FromArgb(0x1d, 0x3a, 0x42) : Surface)) g.FillRectangle(bg, e.Bounds);
                using (var line = new Pen(Color.FromArgb(0x22, 0x29, 0x33))) g.DrawLine(line, e.Bounds.Left, e.Bounds.Bottom - 1, e.Bounds.Right, e.Bounds.Bottom - 1);
                var r = new Rectangle(e.Bounds.X + LogicalToDeviceUnits(14), e.Bounds.Y, e.Bounds.Width - LogicalToDeviceUnits(18), e.Bounds.Height);
                if (e.ColumnIndex == 0)
                {
                    DrawKeyCaps(g, e.SubItem!.Text, r);
                }
                else
                {
                    using var mono = new Font("Cascadia Mono", 9F);
                    TextRenderer.DrawText(g, e.SubItem!.Text, mono, r, selected ? Accent : Text2,
                                          TextFormatFlags.VerticalCenter | TextFormatFlags.Left | TextFormatFlags.EndEllipsis);
                }
            };
        }

        /// <summary>"Ctrl + Num 4" drawn as key caps.</summary>
        void DrawKeyCaps(Graphics g, string combo, Rectangle r)
        {
            g.SmoothingMode = SmoothingMode.AntiAlias;
            using var f = new Font("Segoe UI Semibold", 8.75F);
            int x = r.X, h = LogicalToDeviceUnits(20), y = r.Y + (r.Height - h) / 2;
            var parts = combo.Split(" + ");
            for (int i = 0; i < parts.Length; i++)
            {
                var size = TextRenderer.MeasureText(g, parts[i], f, Size.Empty, TextFormatFlags.NoPadding);
                var cap = new Rectangle(x, y, size.Width + LogicalToDeviceUnits(14), h);
                using (var path = Rounded(cap, LogicalToDeviceUnits(5)))
                using (var fill = new SolidBrush(Surface3))
                using (var pen = new Pen(Line))
                {
                    g.FillPath(fill, path);
                    g.DrawPath(pen, path);
                }
                TextRenderer.DrawText(g, parts[i], f, cap, TextColor, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
                x = cap.Right + LogicalToDeviceUnits(4);
                if (i < parts.Length - 1)
                {
                    TextRenderer.DrawText(g, "+", f, new Rectangle(x, y, LogicalToDeviceUnits(12), h), Muted,
                                          TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
                    x += LogicalToDeviceUnits(16);
                }
            }
        }

        void FitColumns()
        {
            var lv = combination_view;
            if (lv.Columns.Count < 2) return;
            int w = lv.ClientSize.Width;
            lv.Columns[0].Width = (int)(w * 0.45);
            lv.Columns[1].Width = w - lv.Columns[0].Width;
        }

        void LayoutUi()
        {
            if (finderTitle == null || listTitle == null) return;
            int pad = LogicalToDeviceUnits(22), gap = LogicalToDeviceUnits(12);
            int fieldH = LogicalToDeviceUnits(34), labelGap = LogicalToDeviceUnits(6);
            int w = ClientSize.Width - 2 * pad;

            finderTitle.Location = new Point(pad, LogicalToDeviceUnits(18));
            int labelsY = finderTitle.Bottom + LogicalToDeviceUnits(12);
            int fieldsY = labelsY + keyLabel.Height + labelGap;

            int copyW = LogicalToDeviceUnits(140), smallW = LogicalToDeviceUnits(96);
            int revealW = w - copyW - 2 * smallW - 3 * gap;
            int x = pad;
            Place(keyRevealer, keyLabel, x, revealW); x += revealW + gap;
            Place(keyID, key_id_lbl, x, smallW); x += smallW + gap;
            Place(modifierID, modifiers_lbl, x, smallW); x += smallW + gap;
            copy_btn.Bounds = new Rectangle(x, fieldsY, copyW, fieldH);

            void Place(TextBox tb, Label label, int px, int width)
            {
                label.Location = new Point(px + LogicalToDeviceUnits(2), labelsY);
                fieldHosts[tb].Bounds = new Rectangle(px, fieldsY, width, fieldH);
            }

            listTitle.Location = new Point(pad, fieldsY + fieldH + LogicalToDeviceUnits(26));
            listTitle.Text = $"BINDINGS  ·  {combination_view.Items.Count}";
            int listY = listTitle.Bottom + LogicalToDeviceUnits(10);
            combination_view.Bounds = new Rectangle(pad, listY, w, ClientSize.Height - listY - pad);
            FitColumns();
        }

        protected override void OnHandleCreated(EventArgs e)
        {
            base.OnHandleCreated(e);
            try
            {
                int on = 1;
                DwmSetWindowAttribute(Handle, 20, ref on, sizeof(int)); // DWMWA_USE_IMMERSIVE_DARK_MODE
                int caption = Bg.R | (Bg.G << 8) | (Bg.B << 16);
                DwmSetWindowAttribute(Handle, 35, ref caption, sizeof(int)); // DWMWA_CAPTION_COLOR (Windows 11)
                int border = Line.R | (Line.G << 8) | (Line.B << 16);
                DwmSetWindowAttribute(Handle, 34, ref border, sizeof(int)); // DWMWA_BORDER_COLOR
            }
            catch { }
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            // A thin rounded frame round the list, so it reads as a card
            var r = combination_view.Bounds;
            r.Inflate(1, 1);
            e.Graphics.SmoothingMode = SmoothingMode.AntiAlias;
            using var path = Rounded(r, LogicalToDeviceUnits(6));
            using var pen = new Pen(Line);
            e.Graphics.DrawPath(pen, path);
        }

        static GraphicsPath Rounded(Rectangle r, int radius)
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

        /// <summary>The tray icon's menu in the same colours.</summary>
        internal sealed class DarkMenuColors : ProfessionalColorTable
        {
            public override Color ToolStripDropDownBackground => Surface;
            public override Color ImageMarginGradientBegin => Surface;
            public override Color ImageMarginGradientMiddle => Surface;
            public override Color ImageMarginGradientEnd => Surface;
            public override Color MenuBorder => Line;
            public override Color MenuItemBorder => Color.FromArgb(0x1d, 0x3a, 0x42);
            public override Color MenuItemSelected => Color.FromArgb(0x1d, 0x3a, 0x42);
            public override Color SeparatorDark => Line;
            public override Color SeparatorLight => Surface;
        }

        [DllImport("uxtheme.dll", CharSet = CharSet.Unicode)] static extern int SetWindowTheme(IntPtr hWnd, string? app, string? idList);
        [DllImport("dwmapi.dll")] static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int value, int size);
    }
}
