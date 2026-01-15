using Microsoft.Win32;
using System.Reflection.Emit;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using static System.Windows.Forms.VisualStyles.VisualStyleElement;

namespace Timer
{
    public partial class TimerWin : Form
    {
        public bool alert = false;
        private bool entered = false;
        const string RegPath = "CyanHotkey";
        DateTime lastSentTime = DateTime.MinValue;
        System.Windows.Forms.Timer operativeTimer, alarmT, recoverT, lastPositionT, clearRegistry;
        int hours, minutes, seconds;

        private void DisposeAll()
        {
            try
            {
                if (operativeTimer != null) operativeTimer.Dispose();
                if (alarmT != null) alarmT.Dispose();
                if (recoverT != null) recoverT.Dispose();
                if (lastPositionT != null) lastPositionT.Dispose();
            }
            catch (Exception) { }
            // Program.Log("Chronometer disposed");
            alert = false;
        }
        public TimerWin()
        {
            InitializeComponent();
            Visible = true;
            initializeTimers();

            using (var k = Registry.CurrentUser.OpenSubKey(RegPath, writable: true)) k?.DeleteValue("alarm", false);
            clearRegistry = new System.Windows.Forms.Timer() { Enabled = true, Interval = 200 };
            clearRegistry.Tick += (o, e) =>
            {
                if (DateTime.UtcNow - lastSentTime > TimeSpan.FromMilliseconds(500)) deleteAlarm();
            };
            timerFront.BackColor = Color.LightYellow;
            FormClosing += (o, e) => { DisposeAll(); };
            //if (args != null)
            //{
            //    setTimer(args.hours, args.minutes, 0);
            //    if (args.title != null) textBox1.Text = args.title;
            //}
        }

        [DllImport("user32.dll")]
        static public extern bool SetForegroundWindow(IntPtr hWnd);
        [DllImport("user32.dll", CharSet = CharSet.Auto, SetLastError = true)]
        static public extern IntPtr GetForegroundWindow();
        void initializeTimers()
        {
            operativeTimer = new System.Windows.Forms.Timer() { Enabled = true, Interval = 100, };
            alarmT = new System.Windows.Forms.Timer() { Enabled = true, Interval = 500, };
            recoverT = new System.Windows.Forms.Timer() { Enabled = true, Interval = 600, };
            lastPositionT = new System.Windows.Forms.Timer() { Enabled = true, Interval = 20, };

            SetForegroundWindow(this.Handle);
            this.TopMost = true;
            timerFront.KeyDown += KeyEnter;
            notes.KeyDown += KeyEnter;
        }

        void RealTimer(object sender, EventArgs e)
        {
            try
            {
                if (!alert)
                {
                    IntPtr win = this.Handle;
                    if (seconds == 0) { seconds = 59; minutes--; } else seconds--;
                    if (minutes == -1) { minutes = 59; hours--; }
                    if (hours == -1) { seconds = 0; minutes = 0; hours = 0; overlay.Text = "ALERT"; Alarm(); }
                }
                if (alarmTime.Year > 2000) if ((int)(DateTime.Now.Subtract(alarmTime).TotalSeconds + 0.01f) > 2) Close();
                if (overlay.Text != "ALERT") overlay.Text = SetLabelText(hours, minutes, seconds);
            }
            catch (Exception) { DisposeAll(); }
        }
        protected override void OnDeactivate(EventArgs e)
        {
            base.OnDeactivate(e);
            if (!entered) Close();
        }


        void setTimer(int hours, int minutes, int seconds)
        {
            this.hours = hours;
            this.minutes = minutes;
            this.seconds = seconds;
            entered = true;
            if (hours == 0 && minutes == 0 && seconds == 0)
            { SendKeys.Send("{RIGHT}"); lastPositionT.Tick += LastPosition; return; }
            operativeTimer.Interval = 1000;
            operativeTimer.Tick += RealTimer;
            timerFront.Hide();
            overlay.Text = SetLabelText(hours, minutes, seconds);
            overlay.Show();
        }

        void KeyEnter(object sender, KeyEventArgs e)
        {
            if (entered) return;
            if (e.KeyCode == Keys.Enter)
            {
                e.SuppressKeyPress = true;
                hours = timerFront.Value.Hour;
                minutes = timerFront.Value.Minute;
                seconds = timerFront.Value.Second;
                setTimer(hours, minutes, seconds);
            }
        }
        void LastPosition(object sender, EventArgs e)
        {
            try
            {
                hours = timerFront.Value.Hour;
                minutes = timerFront.Value.Minute;
                seconds = timerFront.Value.Second;
                lastPositionT.Tick -= LastPosition;
                operativeTimer.Interval = 1000;
                operativeTimer.Tick += RealTimer;
                timerFront.Hide();
                overlay.Text = SetLabelText(hours, minutes, seconds);
                overlay.Show();
            }
            catch (Exception) { DisposeAll(); }
        }

        string SetLabelText(int ore, int minuti, int secondi)
        {
            string aus1 = "", aus2 = "";
            if (minuti < 10) aus1 = "0";
            if (secondi < 10) aus2 = "0";
            string output = ore + ":" + aus1 + minuti + ":" + aus2 + secondi;
            return output;
        }

        DateTime alarmTime;
        void Alarm()
        {
            alert = true;
            alarmTime = DateTime.Now;
            setAlarm();
        }

        private void setAlarm()
        {
            try
            {
                using (var k = Registry.CurrentUser.CreateSubKey(RegPath))
                {
                    k.SetValue("alarm", "ALARM", RegistryValueKind.String);
                }
            }
            catch { }
        }

        private void deleteAlarm()
        {
            try
            {
                using (var k = Registry.CurrentUser.OpenSubKey(RegPath, writable: true)) k?.DeleteValue("alarm", false);
            }
            catch { }
        }
    }

}
