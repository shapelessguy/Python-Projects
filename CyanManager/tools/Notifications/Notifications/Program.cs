using System.Diagnostics;
using System.Reflection;

namespace Notifications
{
    internal static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            string iconPath = "c:\\Users\\shape\\Documents\\codebase\\sharedCode\\CyanManager\\icons\\a.png";
            string title = "Default Notification Title";
            string message = "Default Notification Message";
            string timeout_str = "5";

            // Parse arguments
            if (args.Length >= 1) iconPath = args[0];
            if (args.Length >= 2) title = args[1];
            if (args.Length >= 3) message = args[2];
            if (args.Length >= 4) timeout_str = args[3];
            int timeout = (int)(float.Parse(timeout_str) * 1000);

            ApplicationConfiguration.Initialize();

            string exeName = Path.GetFileNameWithoutExtension(Assembly.GetExecutingAssembly().Location);
            foreach (var proc in Process.GetProcessesByName(exeName))
            {
                try
                {
                    if (proc.Id == Process.GetCurrentProcess().Id) continue;
                    Debug.WriteLine($"Killing old instance PID {proc.Id}");
                    proc.Kill();
                }
                catch (Exception ex)
                {
                    Debug.WriteLine($"Kill failed for PID {proc.Id}: {ex.Message}");
                }
            }

            Screen[] screens = Screen.AllScreens;

            foreach (Screen screen in Screen.AllScreens)
            {
                var form = new NotificationForm(iconPath, title, message, timeout);
                form.StartPosition = FormStartPosition.Manual;
                form.Location = new Point(screen.Bounds.Left, screen.Bounds.Top);
                form.Opacity = 0;
                form.Show();
                form.Refresh();
                Application.DoEvents();
                form.Opacity = 1.0;
            }
            Application.Run();
        }
    }
}