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

        public MainWindow()
        {
            InitializeComponent();
            LoadLogFiles();
            StartLogTailer();

            VerificationModeCombo.SelectedIndex = 0; // Blink

            WriteLog("RGSStartup", "Windows RGS initialized - Verification=Blink");
            WriteLog("AgentDetection", "Scanning for local agents...");

            // Run multi-agent detection on startup
            DetectConnectedAgents();

            AddDisplayIcon("CYD-001");
            AddDisplayIcon("Cardputer-01");
            AddDisplayIcon("Core2-Dev");

            SimulateRawCommunication();
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
            catch { /* ignore */ }
        }

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
            MessageBox.Show($"Applied verification mode: {mode}");
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

        // === MULTI-AGENT DETECTION ===
        private void DetectConnectedAgents()
        {
            // Simulated agent discovery (will be replaced with real detection later)
            var detectedAgents = new List<AgentType> 
            { 
                AgentType.Hermes, 
                AgentType.Claude 
            };

            int agentCount = detectedAgents.Count;

            WriteLog("AgentDetection", $"Found {agentCount} agents");

            // Show in raw comms box
            RawCommsBox.AppendText($"\n[RGS] AgentCount: {agentCount}\n");
            foreach (var agent in detectedAgents)
            {
                RawCommsBox.AppendText($"[RGS]   <agentType>{agent}</agentType>\n");
            }

            WriteLog("AgentDetection", $"<agentcount>{agentCount}</agentcount>");
        }

        private void SimulateRawCommunication()
        {
            RawCommsBox.AppendText("[Android] → [RGS]     Register: AgentType=Claude, Device=Pixel7\n");
            RawCommsBox.AppendText("[RGS]     → [Android] RegisterAck: SessionId=RAAM-7842\n");
            RawCommsBox.AppendText("[Linux]   → [RGS]     Heartbeat: AgentCount=3 (Hermes, Claude, Unknown)\n");
            RawCommsBox.AppendText("[RGS]     → [CYD-001] AgentUpdate: Hermes token burn rate 42/min\n");
            RawCommsBox.AppendText("[Cardputer-01] → [RGS] Status: Connected\n");
        }
    }

    public enum AgentType
    {
        Hermes,
        Claude,
        Unknown
    }
}