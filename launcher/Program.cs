// PokéMelee Builder: drop a Melee 1.02 (USA) ISO and a Pokémon Colosseum (USA) ISO on the window (or on the exe),
// press Build, get PokeMelee.iso / .xdelta and the AniMelee pair. Everything runs from the bundled engine folder:
// engine/python (embedded Python + the pokemelee package), engine/dotnet and engine/runtime (the pinned tools).
using System.Diagnostics;
using System.Drawing.Drawing2D;
using System.Text;

namespace PokeMeleeBuilder;

static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new BuilderForm(args));
    }
}

enum DiscKind { Melee, Colosseum }

static class Discs
{
    public const long FullSize = 1459978240;     // every untrimmed GameCube disc image

    /// <summary>Which disc a file is, or why it can't be used.</summary>
    public static (DiscKind? Kind, string Problem) Identify(string path)
    {
        try
        {
            var info = new FileInfo(path);
            if (!info.Exists)
                return (null, "is not a file.");
            var head = new byte[8];
            using (var stream = File.OpenRead(path))
                if (stream.Read(head, 0, head.Length) < head.Length)
                    return (null, "is too small to be a disc image.");
            var id = Encoding.ASCII.GetString(head, 0, 6);
            if (id == "GALE01")
            {
                if (head[7] != 2)
                    return (null, $"is Melee version 1.0{head[7]}. PokéMelee needs Melee 1.02 (USA).");
                return info.Length == FullSize ? (DiscKind.Melee, null)
                    : (null, "is a trimmed or compressed Melee image (NKit?). Use a full-size 1.36 GB .iso.");
            }
            if (id == "GC6E01")
                return info.Length == FullSize ? (DiscKind.Colosseum, null)
                    : (null, "is a trimmed or compressed Colosseum image (NKit?). Use a full-size 1.36 GB .iso.");
            if (id.StartsWith("GAL"))
                return (null, "is Melee, but not the USA release. PokéMelee needs Melee 1.02 (USA).");
            if (id.StartsWith("GC6"))
                return (null, "is Pokémon Colosseum, but not the USA release.");
            return (null, "isn't a Melee or Pokémon Colosseum disc image. Compressed formats (.rvz, .ciso, .gcz, .nkit) " +
                          "don't work; use a full-size .iso.");
        }
        catch (Exception e)
        {
            return (null, "can't be read: " + e.Message);
        }
    }
}

sealed class BuilderForm : Form
{
    const long NeededSpace = 20L * 1024 * 1024 * 1024;
    const int TotalSteps = 23;     // 13 shared steps, then per version: stages, pictures, costumes, project, disc
    static readonly (string Folder, string Name)[] Results = { ("normal", "PokeMelee"), ("animelee", "PokeMelee AniMelee") };
    static readonly Dictionary<string, string> StepNames = new()
    {
        ["melee-files"] = "Reading the Melee disc",
        ["cast"] = "Rebuilding the Pokémon models",
        ["stock-art"] = "Stock icons",
        ["css-icons"] = "Character select icons",
        ["colors"] = "Alternate colours",
        ["portraits"] = "Character portraits",
        ["color-portraits"] = "Alternate colour portraits",
        ["menu-sources"] = "Menu art",
        ["menus"] = "Menus",
        ["voices"] = "Voices",
        ["announcer"] = "Announcer",
        ["menu-sounds"] = "Menu sounds",
        ["music"] = "Music",
        ["stages"] = "Stages",
        ["stage-pictures"] = "Stage pictures",
        ["costumes"] = "Costumes",
        ["project"] = "Putting the disc together",
        ["disc"] = "Writing the ISO and xdelta",
    };

    readonly TextBox meleeBox = ReadOnlyBox(), coloBox = ReadOnlyBox(), outBox = new() { Dock = DockStyle.Fill };
    readonly Button buildButton = new() { Text = "Build", AutoSize = true, Padding = new Padding(18, 4, 18, 4) };
    readonly Button cancelButton = new() { Text = "Cancel", AutoSize = true, Enabled = false };
    readonly Button openButton = new() { Text = "Open folder", AutoSize = true, Enabled = false };
    readonly ProgressBar bar = new() { Dock = DockStyle.Fill, Maximum = TotalSteps, Height = 22 };
    readonly Label status = new() { Dock = DockStyle.Fill, AutoSize = true, Text = "Drop your two ISOs to start." };
    readonly TextBox log = new()
    {
        Dock = DockStyle.Fill, Multiline = true, ReadOnly = true, ScrollBars = ScrollBars.Both, WordWrap = false,
        Font = new Font("Consolas", 9f), BackColor = SystemColors.Window,
    };
    readonly System.Windows.Forms.Timer clock = new() { Interval = 1000 };
    readonly string[] startArgs;
    string engine, work, output;
    Process process;
    StreamWriter logFile;
    DateTime started;
    int step;       // steps finished; several run at once, so the status names the running ones
    readonly List<string> running = new();
    string stepText = "", lastError = "";
    bool cancelling;

    public BuilderForm(string[] args)
    {
        startArgs = args;
        Text = "PokéMelee Builder";
        Font = new Font("Segoe UI", 10f);
        ClientSize = new Size(760, 600);
        MinimumSize = new Size(620, 480);
        StartPosition = FormStartPosition.CenterScreen;
        try { Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath); } catch { }

        var drop = new Panel { Dock = DockStyle.Fill, Height = 96, Margin = new Padding(0, 0, 0, 8), Padding = new Padding(4) };
        var dropText = new Label
        {
            Dock = DockStyle.Fill, TextAlign = ContentAlignment.MiddleCenter, ForeColor = SystemColors.GrayText,
            Text = "Drop your Melee 1.02 (USA) and Pokémon Colosseum (USA) ISOs here",
            Font = new Font("Segoe UI", 12f),
        };
        drop.Controls.Add(dropText);
        drop.Paint += (_, e) =>
        {
            using var pen = new Pen(SystemColors.GrayText, 2) { DashStyle = DashStyle.Dash };
            e.Graphics.DrawRectangle(pen, 1, 1, drop.Width - 3, drop.Height - 3);
        };
        drop.Resize += (_, _) => drop.Invalidate();

        var grid = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 3, Padding = new Padding(14) };
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100));
        grid.ColumnStyles.Add(new ColumnStyle(SizeType.AutoSize));
        grid.Controls.Add(drop, 0, 0);
        grid.SetColumnSpan(drop, 3);
        grid.RowStyles.Add(new RowStyle(SizeType.Absolute, 104));
        AddRow(grid, 1, "Melee 1.02 ISO", meleeBox, Browse("Melee 1.02 (USA) ISO"));
        AddRow(grid, 2, "Colosseum ISO", coloBox, Browse("Pokémon Colosseum (USA) ISO"));
        var outBrowse = new Button { Text = "Browse…", AutoSize = true };
        outBrowse.Click += (_, _) =>
        {
            using var dialog = new FolderBrowserDialog { Description = "Where should the finished ISOs go?" };
            if (dialog.ShowDialog(this) == DialogResult.OK)
                outBox.Text = dialog.SelectedPath;
        };
        AddRow(grid, 3, "Save to", outBox, outBrowse);

        var buttons = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, Margin = new Padding(0, 8, 0, 4) };
        buttons.Controls.AddRange(new Control[] { buildButton, cancelButton, openButton });
        grid.Controls.Add(buttons, 0, 4);
        grid.SetColumnSpan(buttons, 3);
        grid.Controls.Add(bar, 0, 5);
        grid.SetColumnSpan(bar, 3);
        grid.Controls.Add(status, 0, 6);
        grid.SetColumnSpan(status, 3);
        grid.Controls.Add(log, 0, 7);
        grid.SetColumnSpan(log, 3);
        for (var i = 1; i <= 6; i++)
            grid.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        grid.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        Controls.Add(grid);

        HookDrop(this);
        buildButton.Click += (_, _) => StartBuild();
        cancelButton.Click += (_, _) => Cancel();
        openButton.Click += (_, _) => Process.Start(new ProcessStartInfo("explorer.exe", $"\"{output}\"") { UseShellExecute = true });
        clock.Tick += (_, _) => ShowStatus();
        FormClosing += OnClosing;
        Shown += (_, _) => OnShown();
    }

    static TextBox ReadOnlyBox() => new() { Dock = DockStyle.Fill, ReadOnly = true, BackColor = SystemColors.Window };

    static void AddRow(TableLayoutPanel grid, int row, string label, Control box, Control button)
    {
        grid.Controls.Add(new Label { Text = label, AutoSize = true, Anchor = AnchorStyles.Left, Margin = new Padding(0, 6, 10, 0) }, 0, row);
        grid.Controls.Add(box, 1, row);
        grid.Controls.Add(button, 2, row);
    }

    Button Browse(string title)
    {
        var button = new Button { Text = "Browse…", AutoSize = true };
        button.Click += (_, _) =>
        {
            using var dialog = new OpenFileDialog { Title = title, Filter = "GameCube disc image (*.iso;*.gcm)|*.iso;*.gcm|All files|*.*" };
            if (dialog.ShowDialog(this) == DialogResult.OK)
                Accept(new[] { dialog.FileName });
        };
        return button;
    }

    void HookDrop(Control control)
    {
        control.AllowDrop = true;
        control.DragEnter += (_, e) =>
            e.Effect = process == null && e.Data.GetDataPresent(DataFormats.FileDrop) ? DragDropEffects.Copy : DragDropEffects.None;
        control.DragDrop += (_, e) =>
        {
            if (process == null && e.Data.GetData(DataFormats.FileDrop) is string[] files)
                Accept(files);
        };
        foreach (Control child in control.Controls)
            HookDrop(child);
    }

    void OnShown()
    {
        engine = Path.Combine(AppContext.BaseDirectory, "engine");
        if (!File.Exists(Path.Combine(engine, "python", "python.exe")))
        {
            MessageBox.Show(this, "The engine folder is missing. Extract the whole PokéMelee Builder folder from the zip " +
                                  "and run the program from there.", Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            Close();
            return;
        }
        var files = new List<string>();
        var autoStart = false;
        for (var i = 0; i < startArgs.Length; i++)
        {
            if (startArgs[i] == "--start") autoStart = true;
            else if (startArgs[i] == "--out" && i + 1 < startArgs.Length) outBox.Text = startArgs[++i];
            else files.Add(startArgs[i]);
        }
        if (files.Count > 0)
            Accept(files);
        if (autoStart)
            StartBuild();
    }

    void Accept(IEnumerable<string> paths)
    {
        var problems = new List<string>();
        foreach (var path in paths)
        {
            var (kind, problem) = Discs.Identify(path);
            if (kind == DiscKind.Melee) meleeBox.Text = path;
            else if (kind == DiscKind.Colosseum) coloBox.Text = path;
            else problems.Add($"{Path.GetFileName(path)} {problem}");
        }
        if (meleeBox.Text.Length > 0 && outBox.Text.Length == 0)
            outBox.Text = Path.Combine(Path.GetDirectoryName(meleeBox.Text) ?? "", "PokeMelee");
        if (problems.Count > 0)
            MessageBox.Show(this, string.Join("\n\n", problems), Text, MessageBoxButtons.OK, MessageBoxIcon.Warning);
        status.Text = meleeBox.Text.Length == 0 ? "Now drop your Melee 1.02 (USA) ISO."
            : coloBox.Text.Length == 0 ? "Now drop your Pokémon Colosseum (USA) ISO."
            : "Ready. Press Build (it takes about 10 minutes).";
    }

    void StartBuild()
    {
        if (process != null)
            return;
        if (meleeBox.Text.Length == 0 || coloBox.Text.Length == 0)
        {
            MessageBox.Show(this, "Drop both ISOs first: Melee 1.02 (USA) and Pokémon Colosseum (USA).", Text);
            return;
        }
        output = outBox.Text.Trim();
        if (output.Length == 0 || !Path.IsPathRooted(output))
        {
            MessageBox.Show(this, "Choose a folder to save the finished ISOs in.", Text);
            return;
        }
        try
        {
            Directory.CreateDirectory(output);
            var free = new DriveInfo(Path.GetPathRoot(Path.GetFullPath(output))).AvailableFreeSpace;
            if (free < NeededSpace)
            {
                MessageBox.Show(this, $"The build needs about 20 GB of free space while it runs (it cleans up afterwards). " +
                                      $"{Path.GetPathRoot(output)} has {free / (1024.0 * 1024 * 1024):0.0} GB free.", Text);
                return;
            }
            var existing = Results.SelectMany(r => new[] { r.Name + ".iso", r.Name + ".xdelta" })
                                  .Where(n => File.Exists(Path.Combine(output, n))).ToList();
            if (existing.Count > 0 && MessageBox.Show(this, "This folder already has " + string.Join(", ", existing) +
                    ". Replace them?", Text, MessageBoxButtons.YesNo, MessageBoxIcon.Question) != DialogResult.Yes)
                return;
            foreach (var old in Directory.GetDirectories(output, "pokemelee-work-*"))
                if (Directory.Exists(Path.Combine(old, "components")) || !Directory.EnumerateFileSystemEntries(old).Any())
                    Directory.Delete(old, true);
            work = Path.Combine(output, "pokemelee-work-" + DateTime.Now.ToString("yyyyMMdd-HHmmss"));
            logFile = new StreamWriter(Path.Combine(output, "PokeMelee build log.txt"), false, new UTF8Encoding(false)) { AutoFlush = true };
        }
        catch (Exception e)
        {
            MessageBox.Show(this, "Can't use that folder: " + e.Message, Text);
            return;
        }

        var python = Path.Combine(engine, "python", "python.exe");
        var dotnet = Path.Combine(engine, "dotnet");
        var info = new ProcessStartInfo(python)
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = engine,
            RedirectStandardOutput = true, RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8,
        };
        foreach (var arg in new[] { "-u", "-m", "pokemelee", "build", "--melee", meleeBox.Text, "--colosseum", coloBox.Text,
                                    "--out", work, "--runtime", Path.Combine(engine, "runtime") })
            info.ArgumentList.Add(arg);
        foreach (var name in new[] { "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "DOTNET_ROLL_FORWARD" })
            info.Environment.Remove(name);
        info.Environment["PATH"] = dotnet + ";" + Path.Combine(engine, "python") + ";" + Environment.GetEnvironmentVariable("PATH");
        info.Environment["DOTNET_ROOT"] = dotnet;
        info.Environment["DOTNET_ROOT_X64"] = dotnet;
        info.Environment["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1";
        info.Environment["DOTNET_NOLOGO"] = "1";
        info.Environment["PYTHONUTF8"] = "1";
        info.Environment["PYTHONIOENCODING"] = "utf-8";
        info.Environment["PYTHONDONTWRITEBYTECODE"] = "1";

        log.Clear();
        Write($"PokéMelee Builder\nMelee:     {meleeBox.Text}\nColosseum: {coloBox.Text}\nOutput:    {output}\n");
        step = 0;
        running.Clear();
        stepText = "Starting";
        lastError = "";
        cancelling = false;
        bar.Value = 0;
        started = DateTime.Now;
        try
        {
            var p = new Process { StartInfo = info, EnableRaisingEvents = true };
            p.OutputDataReceived += (_, e) => { if (e.Data != null) BeginInvoke(new Action(() => OnLine(e.Data, false))); };
            p.ErrorDataReceived += (_, e) => { if (e.Data != null) BeginInvoke(new Action(() => OnLine(e.Data, true))); };
            // wait for the output streams to drain first, so every log line is queued before Finished runs
            p.Exited += (_, _) => { p.WaitForExit(); BeginInvoke(new Action(Finished)); };
            process = p;
            process.Start();
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();
        }
        catch (Exception e)
        {
            process = null;
            Write("Could not start the engine: " + e.Message);
            status.Text = "Could not start the engine: " + e.Message;
            return;
        }
        SetRunning(true);
        clock.Start();
        ShowStatus();
    }

    void OnLine(string line, bool error)
    {
        Write(line);
        if (line.StartsWith("Building ") || line.StartsWith("Finished "))
        {
            var name = line[9..].Trim();
            if (line.StartsWith("Building "))
                running.Add(name);
            else
            {
                name = name.Split(" in ")[0];
                running.Remove(name);
                step = Math.Min(TotalSteps, step + 1);
                bar.Value = step;
            }
            stepText = running.Count == 0 ? "Finishing"
                : string.Join(", ", running.Take(3).Select(Friendly)) + (running.Count > 3 ? $" and {running.Count - 3} more" : "");
            ShowStatus();
        }
        if (error && line.StartsWith("pokemelee: "))
            lastError = line[11..];
    }

    static string Friendly(string name)
    {
        var profile = name.StartsWith("normal-") ? " (normal)" : name.StartsWith("animelee-") ? " (AniMelee)" : "";
        var key = profile.Length > 0 ? name[(name.IndexOf('-') + 1)..] : name;
        return (StepNames.TryGetValue(key, out var friendly) ? friendly : key) + profile;
    }

    void Write(string text)
    {
        foreach (var line in text.Split('\n'))
        {
            logFile?.WriteLine(line);
            log.AppendText(line + Environment.NewLine);
        }
    }

    void ShowStatus()
    {
        if (process == null)
            return;
        var elapsed = DateTime.Now - started;
        status.Text = $"{step} of {TotalSteps} steps done. Now: {stepText}   ({(int)elapsed.TotalMinutes}:{elapsed.Seconds:00} so far)";
    }

    void Finished()
    {
        if (process == null)
            return;
        var code = process.ExitCode;
        process.Dispose();
        process = null;
        clock.Stop();
        SetRunning(false);
        var minutes = (int)(DateTime.Now - started).TotalMinutes;
        if (cancelling)
        {
            Cleanup();
            status.Text = "Cancelled.";
            Write("Cancelled.");
        }
        else if (code == 0)
        {
            try
            {
                foreach (var (folder, name) in Results)
                    foreach (var ext in new[] { ".iso", ".xdelta" })
                        File.Move(Path.Combine(work, folder, "pokemelee" + ext), Path.Combine(output, name + ext), true);
                Cleanup();
                bar.Value = TotalSteps;
                status.Text = $"Done in {minutes} minutes: PokeMelee.iso, PokeMelee AniMelee.iso and their .xdelta patches.";
                Write(status.Text);
                openButton.Enabled = true;
            }
            catch (Exception e)
            {
                status.Text = "The build finished but the files could not be moved: " + e.Message;
                Write(status.Text + $"\nThey are in {work}.");
            }
        }
        else
        {
            var kept = KeepStepLogs();
            Cleanup();
            var reason = Explain(lastError);
            status.Text = "The build stopped. " + reason;
            Write($"Build failed (exit code {code}). " + reason);
            MessageBox.Show(this, "The build stopped.\n\n" + reason + "\n\nThe log is \"PokeMelee build log.txt\" in " + output +
                                  (kept ? ", and the failed step's own logs are in the \"PokeMelee build logs\" folder beside it." : "."),
                            Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
            openButton.Enabled = true;
        }
        logFile?.Dispose();
        logFile = null;
    }

    static string Explain(string error)
    {
        if (error.Contains("input differs from the expected disc file"))
            return "One of the ISOs isn't a clean copy (it may be modded or a different release). Use unmodified dumps.";
        var script = System.Text.RegularExpressions.Regex.Match(error, @"([\w-]+\.py)'");
        if (error.StartsWith("Command ") && script.Success)
            return $"A build step ({script.Groups[1].Value}) failed.";
        return error.Length > 0 ? error : "See the log for details.";
    }

    /// <summary>Before the work folder goes: copy every step log and failure record out of it, and put the tail of the
    /// newest one in the main log.</summary>
    bool KeepStepLogs()
    {
        try
        {
            if (work == null || !Directory.Exists(work))
                return false;
            var logs = Directory.EnumerateFiles(work, "*.*", SearchOption.AllDirectories)
                .Where(f => f.EndsWith(".log", StringComparison.OrdinalIgnoreCase) || Path.GetFileName(f) == "failed.json")
                .Select(f => new FileInfo(f)).Where(f => f.Length < 20_000_000).ToList();
            if (logs.Count == 0)
                return false;
            var folder = Path.Combine(output, "PokeMelee build logs");
            if (Directory.Exists(folder))
                Directory.Delete(folder, true);
            Directory.CreateDirectory(folder);
            foreach (var f in logs)
                File.Copy(f.FullName, Path.Combine(folder, Path.GetRelativePath(work, f.FullName).Replace(Path.DirectorySeparatorChar, '-')), true);
            var newest = logs.Where(f => f.Extension == ".log").OrderBy(f => f.LastWriteTimeUtc).LastOrDefault();
            if (newest != null)
            {
                Write($"--- last lines of {Path.GetRelativePath(work, newest.FullName)} ---");
                foreach (var line in File.ReadAllLines(newest.FullName).TakeLast(40))
                    Write(line);
            }
            return true;
        }
        catch (Exception e)
        {
            Write("Could not keep the step logs: " + e.Message);
            return false;
        }
    }

    void Cleanup()
    {
        for (var attempt = 0; attempt < 10 && work != null && Directory.Exists(work); attempt++)
        {
            try { Directory.Delete(work, true); }
            catch { Thread.Sleep(500); }
        }
    }

    void Cancel()
    {
        if (process == null)
            return;
        cancelling = true;
        status.Text = "Cancelling…";
        try { process.Kill(entireProcessTree: true); } catch { }
    }

    void SetRunning(bool running)
    {
        buildButton.Enabled = !running;
        cancelButton.Enabled = running;
        openButton.Enabled = false;
        outBox.ReadOnly = running;
    }

    void OnClosing(object sender, FormClosingEventArgs e)
    {
        if (process == null)
            return;
        if (MessageBox.Show(this, "A build is running. Stop it and close?", Text, MessageBoxButtons.YesNo,
                MessageBoxIcon.Question) != DialogResult.Yes)
        {
            e.Cancel = true;
            return;
        }
        cancelling = true;
        try { process.Kill(entireProcessTree: true); process.WaitForExit(10000); } catch { }
        Cleanup();
    }
}
