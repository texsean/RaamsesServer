using System;
using System.Collections.ObjectModel;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;

namespace Raamses.RGS.Windows
{
    public partial class MainWindow : Window
    {
        private DispatcherTimer _logTimer;
        private string _currentLogPath = "gateway.log"; // default debug log

        public MainWindow()
        {
            InitializeComponent();
            LoadLogFiles();
            StartLogTailer();

            // Default verification mode
            VerificationModeCombo.SelectedIndex = 0; // Blink
        }

        private void LoadLogFiles()
        {
            // Placeholder - in real impl scan logs/ folder
            LogFileList.Items.Add("gateway.log");
            LogFileList.Items.Add("agent_hermes.log");
            LogFileList.Items.Add("agent_claude.log");
            LogFileList.SelectedIndex = 0;
        }

        private void StartLogTailer()
        {
            _logTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
            _logTimer.Tick += (s, e) => TailCurrentLog();
            _logTimer.Start();
        }

        private void TailCurrentLog()
        {
            if (!File.Exists(_currentLogPath)) return;

            try
            {
                var lines = File.ReadAllLines(_currentLogPath);
                var lastLines = lines.Length > 20 ? lines[^20..] : lines;

                LogTailBox.Text = string.Join(Environment.NewLine, lastLines);
                LogTailBox.ScrollToEnd();
            }
            catch { /* ignore file lock */ }
        }

        // Helper to write logs in the exact requested format: mmddyy-hhmmss.nnn
        public void WriteLog(string method, string detail)
        {
            string timestamp = DateTime.Now.ToString("MMddyy-HHmmss.fff");
            string logLine = $"{timestamp}\t{method}\t{detail}";

            try
            {
                File.AppendAllText(_currentLogPath, logLine + Environment.NewLine);
            }
            catch { /* ignore */ }
        }

        private void ApplyConfig_Click(object sender, RoutedEventArgs e)
        {
            string mode = ((ComboBoxItem)VerificationModeCombo.SelectedItem).Content.ToString();
            // TODO: Apply to running RGS service / config file
            MessageBox.Show($"Applied verification mode: {mode}");
        }

        // Placeholder for adding display icons dynamically
        public void AddDisplayIcon(string displayName)
        {
            var icon = new TextBlock { Text = "🖥️ " + displayName, Margin = new Thickness(8,0,8,0) };
            DisplayIconsPanel.Children.Add(icon);
        }
    }

    // AgentType enum as requested
    public enum AgentType
    {
        Hermes,
        Claude,
        Unknown
    }
}