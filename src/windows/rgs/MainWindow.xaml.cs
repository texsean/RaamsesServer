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

        // Multi-agent tracking
        private int _agentCount = 0;
        private ObservableCollection<AgentType> _detectedAgents = new ObservableCollection<AgentType>();

        public MainWindow()
        {
            InitializeComponent();
            LoadLogFiles();
            StartLogTailer();

            // Default verification mode
            VerificationModeCombo.SelectedIndex = 0; // Blink

            // Seed some sample logs on startup
            WriteLog("RGSStartup", "Windows RGS initialized - Verification=Blink");

            // Multi-agent detection on startup
            DetectAgents();

            // Populate display icons (placeholder)
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

        // === MULTI-AGENT DETECTION (stub for now) ===
        private void DetectAgents()
        {
            _detectedAgents.Clear();

            // TODO: Real implementation will scan processes / config / network
            // For now we seed Hermes + Claude as example
            _detectedAgents.Add(AgentType.Hermes);
            _detectedAgents.Add(AgentType.Claude);

            _agentCount = _detectedAgents.Count;

            WriteLog("AgentDetection", $"Detected {_agentCount} agents: {string.Join(", ", _detectedAgents)}");
            WriteLog("AgentDetection", $"<agentcount>{_agentCount}</agentcount> <agentType>{string.Join(",", _detectedAgents)}</agentType>");
        }

        // === DYNAMIC DISPLAY ICONS ===
        private void PopulateDisplayIcons()
        {
            DisplayIconsPanel.Children.Clear();

            // Example connected displays (will be dynamic later)
            AddDisplayIcon("CYD-01");
            AddDisplayIcon("Cardputer-Alpha");
            AddDisplayIcon("Core2-Beta");
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

    // AgentType enum as requested
    public enum AgentType
    {
        Hermes,
        Claude,
        Unknown
    }
}