namespace KeyboardHotkeys
{
    using System.Globalization;
    using System.Text.Json;
    static class Program
    {
        public static HiddenWin win;

        public class Hotkey
        {
            public int key { get; set; }
            public int modifier { get; set; }
        }

        /// <summary>
        ///  The main entry point for the application.
        /// </summary>
        [STAThread]
        static void Main(string[] args)
        {
            // To customize application configuration such as set high DPI settings or default font,
            // see https://aka.ms/applicationconfiguration.
            ApplicationConfiguration.Initialize();

            if (args.Length > 0)
            {
                string jsonArg = args[0];
                try
                {
                    var jsonMap = JsonSerializer.Deserialize<Dictionary<string, List<Hotkey>>>(jsonArg);
                    win = new HiddenWin();
                    win.RegisterHotkeys(jsonMap.ToDictionary(
                        kvp => kvp.Key,
                        kvp => kvp.Value
                            .Select(hk => (hk.key, hk.modifier))
                            .ToList()
                    ));
                }
                catch (Exception e)
                {
                    MessageBox.Show(e.ToString());
                    return;
                }
            }
            else
            {
                win = new HiddenWin();
                win.RegisterHotkeys(new Dictionary<string, List<(int key, int modifier)>>
                {
                    { "funct1", new List<(int key, int modifier)>(){(107, 0), (107, 1) } },
                    { "funct3", new List<(int key, int modifier)>(){(107, 2) } },
                });
            }
            Application.Run(win);
        }
    }
}