$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -ReferencedAssemblies System.Windows.Forms,System.Drawing,System.Web.Extensions -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

public class CodeWeaverTray : ApplicationContext {
    public class WindowState {
        public string id;
        public string label;
        public string title;
        public bool visible;
    }
    public class DesktopState {
        public WindowState[] widgets = new WindowState[0];
        public WindowState dashboard;
    }
    private readonly NotifyIcon icon = new NotifyIcon();
    private readonly JavaScriptSerializer json = new JavaScriptSerializer();
    private readonly ConcurrentQueue<string> input = new ConcurrentQueue<string>();
    private readonly System.Windows.Forms.Timer timer = new System.Windows.Forms.Timer();
    private DesktopState state = new DesktopState();
    private DateTime lastHeartbeat = DateTime.UtcNow;
    private volatile bool inputClosed;
    private string lastMenu = "";
    private string lastWindows = "";
    private Icon ownedIcon;

    private delegate bool WindowCallback(IntPtr handle, IntPtr parameter);
    [DllImport("user32.dll")] private static extern bool EnumWindows(WindowCallback callback, IntPtr parameter);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr handle);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr handle, out uint processId);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] private static extern int GetWindowText(IntPtr handle, StringBuilder title, int count);
    [DllImport("user32.dll", EntryPoint="GetWindowLongW")] private static extern int GetWindowLong(IntPtr handle, int index);
    [DllImport("user32.dll", EntryPoint="SetWindowLongW")] private static extern int SetWindowLong(IntPtr handle, int index, int value);
    [DllImport("user32.dll")] private static extern bool SetWindowPos(IntPtr handle, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] private static extern bool DestroyIcon(IntPtr handle);

    public CodeWeaverTray() {
        using (var bitmap = new Bitmap(32, 32)) {
            using (var graphics = Graphics.FromImage(bitmap))
            using (var brush = new SolidBrush(Color.FromArgb(84, 214, 185)))
            using (var font = new Font("Segoe UI", 11, FontStyle.Bold)) {
                graphics.Clear(Color.FromArgb(10, 14, 18));
                graphics.DrawString("CW", font, brush, 1, 6);
            }
            IntPtr handle = bitmap.GetHicon();
            using (var temporary = Icon.FromHandle(handle)) ownedIcon = (Icon)temporary.Clone();
            DestroyIcon(handle);
        }
        icon.Icon = ownedIcon;
        icon.Text = "Code Weaver — widgets and dashboard";
        icon.MouseClick += delegate(object sender, MouseEventArgs e) {
            if (e.Button == MouseButtons.Left) Send("show-all", null);
        };
        BuildMenu();
        icon.Visible = true;
        var reader = new Thread(delegate() {
            try {
                string line;
                while ((line = Console.ReadLine()) != null) input.Enqueue(line);
            } finally { inputClosed = true; }
        });
        reader.IsBackground = true;
        reader.Start();
        timer.Interval = 500;
        timer.Tick += delegate { Tick(); };
        timer.Start();
        Console.WriteLine("{\"event\":\"ready\"}");
        Console.Out.Flush();
    }

    private void Send(string action, string id) {
        Console.WriteLine(json.Serialize(new { action = action, id = id }));
        Console.Out.Flush();
    }

    private ToolStripMenuItem Item(string label, string action, string id) {
        var item = new ToolStripMenuItem(label.Replace("&", "&&"));
        item.Click += delegate { Send(action, id); };
        return item;
    }

    private void BuildMenu() {
        var menu = new ContextMenuStrip();
        menu.Items.Add(Item("Show all widgets", "show-all", null));
        menu.Items.Add(Item("Hide all widgets", "hide-all", null));
        menu.Items.Add(new ToolStripSeparator());
        foreach (var window in state.widgets) {
            var entry = new ToolStripMenuItem(window.label.Replace("&", "&&"));
            entry.DropDownItems.Add(Item(window.visible ? "Hide widget" : "Show widget", "toggle-widget", window.id));
            entry.DropDownItems.Add(Item("Open dashboard for this window", "dashboard", window.id));
            menu.Items.Add(entry);
        }
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(Item("Open full dashboard", "dashboard", null));
        menu.Items.Add(Item("Hide dashboard", "hide-dashboard", null));
        menu.Items.Add(Item("Collect evidence now", "collect", null));
        menu.Items.Add(new ToolStripSeparator());
        menu.Items.Add(Item("Quit Code Weaver", "quit", null));
        var oldMenu = icon.ContextMenuStrip;
        icon.ContextMenuStrip = menu;
        if (oldMenu != null) oldMenu.Dispose();
    }

    private static bool Matches(string actual, string expected) {
        // WSLg may append the distribution name to a projected window title.
        return actual == expected || (actual.StartsWith(expected + " (", StringComparison.Ordinal) && actual.EndsWith(")"));
    }

    private void EnforceWindows() {
        var targets = new List<WindowState>(state.widgets);
        if (state.dashboard != null) targets.Add(state.dashboard);
        var observed = new List<object>();
        WindowCallback callback = delegate(IntPtr handle, IntPtr parameter) {
            if (!IsWindowVisible(handle)) return true;
            var title = new StringBuilder(1024);
            GetWindowText(handle, title, title.Capacity);
            WindowState target = targets.Find(w => w.visible && Matches(title.ToString(), w.title));
            if (target == null) return true;
            uint processId;
            GetWindowThreadProcessId(handle, out processId);
            try {
                using (var process = Process.GetProcessById((int)processId)) {
                    if (process.ProcessName != "msrdc" && process.ProcessName != "mstsc") return true;
                }
            } catch (ArgumentException) { return true; }
            // WSLg does not reliably project Electron's skipTaskbar/topmost
            // hints. Apply them to only these exact Code Weaver HWNDs.
            int style = GetWindowLong(handle, -20);
            int desired = (style | 0x80) & ~0x40000; // TOOLWINDOW; clear APPWINDOW.
            bool changed = style != desired;
            if (changed) SetWindowLong(handle, -20, desired);
            if (changed || (style & 8) == 0) {
                // NOMOVE | NOSIZE | NOACTIVATE, plus FRAMECHANGED when needed.
                SetWindowPos(handle, new IntPtr(-1), 0, 0, 0, 0, (uint)(0x13 | (changed ? 0x20 : 0)));
            }
            int actual = GetWindowLong(handle, -20);
            observed.Add(new { id = target.id, handle = handle.ToInt64(), topmost = (actual & 8) != 0,
                skipTaskbar = (actual & 0x80) != 0 && (actual & 0x40000) == 0 });
            return true;
        };
        EnumWindows(callback, IntPtr.Zero);
        string snapshot = json.Serialize(observed);
        if (snapshot != lastWindows) {
            lastWindows = snapshot;
            Console.WriteLine("{\"event\":\"windows\",\"windows\":" + snapshot + "}");
            Console.Out.Flush();
        }
    }

    private void Tick() {
        string line;
        string newest = null;
        while (input.TryDequeue(out line)) newest = line;
        if (newest != null) {
            lastHeartbeat = DateTime.UtcNow;
            state = json.Deserialize<DesktopState>(newest);
            if (state == null || state.widgets == null) throw new InvalidOperationException("Invalid desktop state");
            if (newest != lastMenu && (icon.ContextMenuStrip == null || !icon.ContextMenuStrip.Visible)) {
                lastMenu = newest;
                BuildMenu();
            }
        }
        if (inputClosed || (DateTime.UtcNow - lastHeartbeat).TotalSeconds > 20) {
            ExitThread();
            return;
        }
        EnforceWindows();
    }

    protected override void ExitThreadCore() {
        timer.Stop();
        icon.Visible = false;
        icon.Dispose();
        ownedIcon.Dispose();
        timer.Dispose();
        base.ExitThreadCore();
    }

    public static void Run() {
        Application.EnableVisualStyles();
        using (var context = new CodeWeaverTray()) Application.Run(context);
    }
}
'@
[CodeWeaverTray]::Run()
