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
        private string _currentLogPath = "gateway.log";

        // Multi-agent tracking
        private int _agentCount = 0;
        private ObservableCollection<AgentType> _detectedAgents = new ObservableCollection<AgentType>();

        public MainWindow()
        {
            InitializeComponent();
            LoadLogFiles();
            StartLogTailer();

            VerificationModeCombo.SelectedIndex = 0; // Blink

            WriteLog("RGSStartup", "Windows RGS initialized - Verification=Blink");

            DetectAgents();
            PopulateDisplayIcons();
        }

        private void LoadLogFiles()
        {
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
            catch { }
        }

        public void WriteLog(string method, string detail)
        {
            string timestamp = DateTime.Now.ToString("MMddyy-HHmmss.fff");
            string logLine = $"{timestamp}\t{method}\t{detail}";

            try
            {
                File.AppendAllText(_currentLogPath, logLine + Environment.NewLine);
            }
            catch { }
        }

        // === RAW COMMUNICATION LOGGING (for middle panel) ===
        public void LogRawCommunication(string direction, string message)
        {
            string timestamp = DateTime.Now.ToString("MMddyy-HHmmss.fff");
            string logLine = $"{timestamp}\tRAW_{direction}\t{message}";

            try
            {
                File.AppendAllText(_currentLogPath, logLine + Environment.NewLine);
            }
            catch { }

            // Also show in the Raw Comms box
            RawCommsBox.AppendText($"[{timestamp}] {direction}: {message}\n");
            RawCommsBox.ScrollToEnd();
        }

        // === MULTI-AGENT DETECTION ===
        private void DetectAgents()
        {
            _detectedAgents.Clear();

            // TODO: Replace with real process/config scanning
            _detectedAgents.Add(AgentType.Hermes);
            _detectedAgents.Add(AgentType.Claude);

            _agentCount = _detectedAgents.Count;

            WriteLog("AgentDetection", $"<agentcount>{_agentCount}</agentcount>");
            WriteLog("AgentDetection", $"<agentType>{string.Join(",", _detectedAgents)}</agentType>");
        }

        // === DISPLAY ICONS ===
        private void PopulateDisplayIcons()
        {
            DisplayIconsPanel.Children.Clear();

            AddDisplayIcon("CYD-01");
            AddDisplayIcon("Cardputer-Alpha");
            AddDisplayIcon("Core2-Beta");
            AddDisplayIcon("Android-Client");
        }

        public void AddDisplayIcon(string displayName)
        {
            var icon = new TextBlock
            {
                Text = "🖥️ " + displayName,
                Margin = new Thickness(8, 0, 8, 0),
                FontSize = 14
            };
            DisplayIconsPanel.Children.Add(icon);
        }

        private void ApplyConfig_Click(object sender, RoutedEventArgs e)
        {
            string mode = ((ComboBoxItem)VerificationModeCombo.SelectedItem).Content.ToString();
            WriteLog("ConfigApply", $"Verification mode changed to {mode}");
            MessageBox.Show($"Applied verification mode: {mode}");
        }
    }

    public enum AgentType
    {
        Hermes,
        Claude,
        Unknown
    }
}