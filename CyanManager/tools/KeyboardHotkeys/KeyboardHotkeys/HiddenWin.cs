
using Microsoft.Win32;
using System.Runtime.InteropServices;
using System.Security.Policy;
using System.Windows.Forms;
using static System.Windows.Forms.VisualStyles.VisualStyleElement;

namespace KeyboardHotkeys
{
    public partial class HiddenWin : Form
    {
        private Dictionary<string, (int key, int modifier)> keyMap;
        const string RegPath = "CyanHotkey";
        DateTime lastSentTime = DateTime.MinValue;
        System.Windows.Forms.Timer clearRegistry;
        private NotifyIcon trayIcon;
        private ContextMenuStrip trayMenu;

        public HiddenWin()
        {
            InitializeComponent();
            WindowState = FormWindowState.Minimized;
            Load += (s, e) => Hide();
            keyRevealer.KeyDown += findKey;
            keyID.KeyDown += findKey;
            modifierID.KeyDown += findKey;
            combination_view.View = View.Details;
            combination_view.Columns.Add("Modifiers", 330);
            combination_view.Columns.Add("Action", 330);
            clearRegistry = new System.Windows.Forms.Timer() { Enabled = true, Interval = 200 };
            using (var k = Registry.CurrentUser.OpenSubKey(RegPath, writable: true)) k?.DeleteValue("function", false);
            clearRegistry.Tick += (o, e) =>
            {
                // string value = getFunction();
                if (DateTime.UtcNow - lastSentTime > TimeSpan.FromMilliseconds(500)) deleteFunction();
            };
            InitializeTrayIcon();
        }

        private string getFunction()
        {
            string strValue = "";
            try
            {
                using (var k = Registry.CurrentUser.CreateSubKey(RegPath))
                {
                    if (k != null)
                    {
                        object value = k.GetValue("function");
                        if (value != null) strValue = (string)value;
                    }
                }
            }
            catch { }
            return strValue;
        }

        private void setFunction(string value)
        {
            string strValue = "";
            try 
            {
                using (var k = Registry.CurrentUser.CreateSubKey(RegPath))
                {
                    object cur_value = k.GetValue("function");
                    if (cur_value != null) strValue = (string)cur_value;

                    string functionName = value;
                    int repetition = 0;

                    if (strValue != "")
                    {
                        string[] parts = strValue.Split('x');
                        if (parts[0] == value)
                        {
                            functionName = parts[0];
                            repetition = int.Parse(parts[1]);
                        }
                    }
                    k.SetValue("function", functionName + "x" + (repetition + 1).ToString(), RegistryValueKind.String);
                }
            }
            catch { }
        }

        private void deleteFunction()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(RegPath, writable: true)) k?.DeleteValue("function", false);
            }
            catch {}
        }

        [DllImport("user32.dll")]
        [return: MarshalAs(UnmanagedType.Bool)]
        public static extern bool SetForegroundWindow(IntPtr hWnd);
        private void ShowForm()
        {
            Show();
            WindowState = FormWindowState.Normal;
            TopMost = true;
            Activate();
            SetForegroundWindow(Handle);
        }

        private void ExitApp()
        {
            trayIcon.Visible = false;
            trayIcon.Dispose();
            Application.Exit();
        }

        private void InitializeTrayIcon()
        {
            trayMenu = new ContextMenuStrip();
            trayMenu.Items.Add("Open", null, (s, e) => ShowForm());
            trayMenu.Items.Add(new ToolStripSeparator());
            trayMenu.Items.Add("Exit", null, (s, e) => ExitApp());

            trayIcon = new NotifyIcon
            {
                Icon = Properties.Resources.MainIcon,
                Text = "Keyboard Hotkeys",
                ContextMenuStrip = trayMenu,
                Visible = true
            };

            trayIcon.DoubleClick += (s, e) => ShowForm();
        }

        public void RegisterHotkeys(Dictionary<string, (int key, int modifier)> keyMap)
        {
            this.keyMap = keyMap;
            int i = 0;
            foreach (var kvp in keyMap)
            {
                i += 1;
                Keys k = (Keys)kvp.Value.key;
                string modifiers = getFriendlyModifiers((KeyModifier)kvp.Value.modifier);
                modifiers += k.ToString();

                var item = new ListViewItem(modifiers);
                item.SubItems.Add(kvp.Key);
                combination_view.Items.Add(item);

                if (!RegisterHotKey(Handle, i, kvp.Value.modifier, k.GetHashCode()))
                    MessageBox.Show($"Failed to register hotkey {kvp.Key}");
            }
        }
        
        private string getFriendlyModifiers(KeyModifier modifier, Keys excludeKey = Keys.None)
        {
            
            bool ctrl = (modifier & KeyModifier.Control) != 0;
            bool alt = (modifier & KeyModifier.Alt) != 0;
            bool shift = (modifier & KeyModifier.Shift) != 0;
            bool win = (modifier & KeyModifier.WinKey) != 0;

            string modifiers = "";
            if (shift && excludeKey != Keys.ShiftKey) modifiers += "Shift +";
            if (ctrl && excludeKey != Keys.ControlKey) modifiers += "Ctrl +";
            if (alt && excludeKey != Keys.Menu) modifiers += "Alt +";
            if (win && excludeKey != Keys.LWin) modifiers += "Win +";
            return modifiers;
        }
        private void writeKeyText(Keys key, KeyModifier modifier)
        {
            if (!keyRevealer.Focused & !keyID.Focused & !modifierID.Focused)
            {
                keyRevealer.Text = "";
                keyID.Text = "";
                modifierID.Text = "";
            }
            else
            {
                string modifiers = getFriendlyModifiers(modifier, key);
                modifiers += " ";
                string key_str = key.ToString();
                if (key_str.EndsWith("Key")) key_str = key_str.Substring(0, key_str.Length - 3);
                if (key_str == "Menu") key_str = "Alt";
                keyRevealer.Text = modifiers + key_str;
                keyID.Text = ((int)key).ToString();
                modifierID.Text = ((int)modifier).ToString();
            }
        }
        private void findKey(object o, KeyEventArgs e)
        {
            keyRevealer.Text = "";
            keyID.Text = "";
            modifierID.Text = "";
            e.SuppressKeyPress = true;
            Keys key = e.KeyCode;
            KeyModifier modifiers = KeyModifier.None;
            if (e.Control) modifiers = modifiers | KeyModifier.Control;
            if (e.Shift) modifiers = modifiers | KeyModifier.Shift;
            if (e.Alt) modifiers = modifiers | KeyModifier.Alt;
            writeKeyText(key, modifiers);
        }


        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool RegisterHotKey(IntPtr hWnd, int id, int fsModifiers, int vk);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        private static extern bool UnregisterHotKey(IntPtr hWnd, int id);

        enum KeyModifier
        {
            None = 0,
            Alt = 1,
            Control = 2,
            Shift = 4,
            WinKey = 8
        }

        private static int WM_QUERYENDSESSION = 0x11;
        private static int WM_ENDSESSION = 0x16;
        public const uint SHUTDOWN_NORETRY = 0x00000001;
        protected override void WndProc(ref Message m)
        {
            if (m.Msg.Equals(WM_QUERYENDSESSION) || m.Msg.Equals(WM_ENDSESSION) || m.Msg.Equals(SHUTDOWN_NORETRY))
            {
                FormClosing(null, null);
            }
            if (m.Msg == 0x0312)
            {
                Keys key = (Keys)(((int)m.LParam >> 16) & 0xFFFF);
                KeyModifier modifier = (KeyModifier)((int)m.LParam & 0xFFFF);
                if (!keyRevealer.Focused & !keyID.Focused & !modifierID.Focused)
                {
                    foreach (var kvp in keyMap)
                    {
                        var keyId = (int)((Keys)kvp.Value.key);
                        var modId = (int)kvp.Value.modifier;
                        if ((int)key == keyId & (int)modifier == modId)
                        {
                            setFunction(kvp.Key);
                            lastSentTime = DateTime.UtcNow;
                        }
                    }
                }
                else
                {
                    writeKeyText(key, modifier);
                }
            }
            base.WndProc(ref m);
        }

        protected override void OnFormClosing(FormClosingEventArgs e)
        {
            if (e.CloseReason == CloseReason.UserClosing)
            {
                e.Cancel = true;
                Hide();
            }
            else
            {
                base.OnFormClosing(e);
            }
        }

        private void FormClosing(object sender, FormClosingEventArgs e)
        {
            UnregisterHotKey(Handle, 0);
        }

        private void copy_btn_Click(object sender, EventArgs e)
        {
            string keyId = keyID.Text;
            string modifierId = modifierID.Text;
            Clipboard.SetText("(" + keyId + ", " + modifierId + ")");
        }
    }
}
