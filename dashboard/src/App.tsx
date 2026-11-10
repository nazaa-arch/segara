import React, { useState, useEffect, useRef } from 'react';
import {
  AlertTriangle,
  Activity,
  Radio,
  Play,
  Pause,
  RotateCcw,
  SkipForward,
  MapPin,
  Thermometer,
  ShieldAlert,
  Flame,
  Droplets,
  CheckCircle2,
  XCircle,
  TrendingUp,
  Cpu,
  BarChart3,
  Send,
  RefreshCw,
  Bell,
  Sliders,
  Check,
  Zap,
} from 'lucide-react';
import L from 'leaflet';

// Definisi Tipe Data
interface NodeData {
  id: number;
  name: string;
  region: string;
  latitude: number;
  longitude: number;
  mmm_sst: number;
  bleaching_threshold: number;
  depth_m: number;
  battery: number;
  latest_measurement?: {
    temperature: number;
    ph: number;
    salinity: number;
    turbidity: number;
    battery: number;
    counter: number;
    timestamp: string;
  };
  latest_thermal?: {
    sst: number;
    mmm: number;
    hotspot: number;
    dhw: number;
    alert_level: number;
    alert_label: string;
    compound_stress: number;
  };
}

interface ThermalHistoryPoint {
  timestamp: string;
  sst: number;
  mmm: number;
  hotspot: number;
  dhw: number;
  alert_level: number;
  alert_label: string;
  compound_stress: number;
}

interface AlertItem {
  id: number;
  node_id: number;
  node_name: string;
  timestamp: string;
  alert_level: number;
  alert_type: string;
  message: string;
  acknowledged: boolean;
}

interface QCSummary {
  total_samples: number;
  valid_samples: number;
  pass_rate_percent: number;
  flags_breakdown: {
    range_violations: number;
    spike_violations: number;
    stuck_sensors: number;
    drift_sensors: number;
    packet_loss_events: number;
    total_packets_dropped: number;
    battery_low_warnings: number;
  };
}

interface EvaluationMetrics {
  packet_loss_monte_carlo?: {
    [key: string]: {
      target_loss_rate_pct: number;
      monte_carlo_runs: number;
      telemetry_interval_hours: number;
      missing_packet_strategy: string;
      reference_design: string;
      measured_pdr_mean: number;
      measured_pdr_std: number;
      dhw_error_mae_mean: number;
      dhw_error_mae_std: number;
      max_dhw_bias_mean: number;
      alert_1_delay_days_mean: number | null;
      alert_1_delay_days_std: number | null;
      alert_1_delay_valid_runs: number;
      alert_1_delay_unavailable_runs: number;
    };
  };
  quality_control_functional_verification?: {
    test_type: string;
    scope_note: string;
    clean_control: {
      cycles: number;
      design: string;
      critical_flag_counts_per_rule: { [rule: string]: number };
    };
    spike_sensitivity_curve: {
      [key: string]: {
        spike_delta_celsius: number;
        threshold_celsius: number;
        trials: number;
        detected_count: number;
        detection_rate_pct: number;
        expected: string;
      };
    };
    stuck_rule_case: { [key: string]: any };
    drift_rule_case: { [key: string]: any };
    range_rule_case: { [key: string]: any };
    spike_false_positive_control: { [key: string]: any };
    limitations: string[];
  };
  dhw_algorithmic_verification?: {
    verification_type: string;
    reference_source: {
      file: string;
      provenance_status: string;
      records_node_1: number;
      cadence_days: number;
      reference_kind: string;
    };
    agreement_with_reference_column: {
      mae_celsius_weeks: number;
      rmse_celsius_weeks: number;
      pearson_correlation: number | null;
      note: string;
    };
    internal_consistency_check: {
      observation_span_days: number;
      window_days: number;
      window_covers_entire_series: boolean;
      computed_dhw_decrease_steps: number;
      reference_dhw_decrease_steps: number;
      reference_first_decrease_index: number | null;
      verdict: string;
    };
    noaa_alert_system_version: {
      implemented_version: string;
      levels: string[];
      note_on_2023_revision: string;
    };
  };
  forecasting_multi_horizon_evaluation?: {
    status: string;
    reason: string;
    data_source: string;
    cadence_days: number;
    samples_node_1: number;
    horizon_benchmarks: {
      [key: string]: {
        horizon_days: number;
        horizon_steps: number;
        evaluated_origins: number;
        model_mae: number;
        baseline_mae: number;
        model_beats_persistence: boolean;
        improvement_vs_persistence_pct: number | null;
      };
    } | null;
  };
  in_process_execution_latency?: {
    benchmark_scope: string;
    excluded_layers: string[];
    total_runs: number;
    mean_latency_ms: number;
    median_latency_ms: number;
    p95_latency_ms: number;
    p99_latency_ms: number;
  };
}

// Pesan alert lama tersimpan dengan markup Markdown Telegram (* ` _); tampilkan bersih.
function cleanAlertMessage(message: string): string {
  const body = message.split('━━━━━━━━━━━━━━━━━━━━━━')[1]?.trim() || message;
  return body.replace(/[*`_]/g, '');
}

export default function App() {
  const [nodes, setNodes] = useState<NodeData[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<number>(1);
  const [thermalHistory, setThermalHistory] = useState<ThermalHistoryPoint[]>([]);
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [qcSummary, setQcSummary] = useState<QCSummary | null>(null);
  const [evalMetrics, setEvalMetrics] = useState<EvaluationMetrics | null>(null);
  const [forecastData, setForecastData] = useState<any>(null);

  // Status Simulator
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [scenario, setScenario] = useState<string>('normal');
  const [packetLossRate, setPacketLossRate] = useState<number>(0.0);
  const [stepCount, setStepCount] = useState<number>(0);
  const [activeTab, setActiveTab] = useState<'analytics' | 'qc' | 'alerts' | 'eval'>('analytics');
  const [loading, setLoading] = useState<boolean>(false);
  // Status koneksi ke backend: null = belum diketahui
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);
  const pollingRef = useRef<boolean>(false);

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const markersRef = useRef<{ [key: number]: L.CircleMarker }>({});

  // 1. Ambil data utama dari API
  const fetchData = async () => {
    try {
      const [resNodes, resAlerts, resQC, resSim] = await Promise.all([
        fetch('/api/nodes'),
        fetch('/api/alerts?limit=15'),
        fetch('/api/analytics/qc-summary'),
        fetch('/api/simulator/status'),
      ]);

      setServerOnline(resNodes.ok);
      if (resNodes.ok) {
        const nodesData = await resNodes.json();
        setNodes(nodesData);
      }
      if (resAlerts.ok) {
        const alertsData = await resAlerts.json();
        setAlerts(alertsData);
      }
      if (resQC.ok) {
        const qcData = await resQC.json();
        setQcSummary(qcData);
      }
      if (resSim.ok) {
        const simData = await resSim.json();
        setIsRunning(simData.state.is_running);
        setScenario(simData.state.scenario);
        setStepCount(simData.state.step_count);
        setPacketLossRate(simData.state.packet_loss_rate);
      }
    } catch (err) {
      setServerOnline(false);
      console.error('Error fetching system data:', err);
    }
  };

  // 2. Ambil data spesifik node terpilih
  const fetchNodeDetails = async (nodeId: number) => {
    try {
      const [resDhw, resFc] = await Promise.all([
        fetch(`/api/analytics/dhw/${nodeId}?limit=35`),
        fetch(`/api/analytics/forecast/${nodeId}?horizon_days=14`),
      ]);

      if (resDhw.ok) {
        const dhwJson = await resDhw.json();
        setThermalHistory(dhwJson.history || []);
      }
      if (resFc.ok) {
        const fcJson = await resFc.json();
        setForecastData(fcJson.forecast);
      }
    } catch (err) {
      console.error('Error fetching node details:', err);
    }
  };

  // 3. Ambil data benchmark evaluasi
  const fetchEvaluationMetrics = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/evaluation/metrics');
      if (res.ok) {
        const data = await res.json();
        setEvalMetrics(data);
      }
    } catch (err) {
      console.error('Error fetching evaluation metrics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Polling 2,5 dtk: tidak menumpuk bila server lambat (menunggu putaran sebelumnya
    // selesai) dan berhenti saat tab tidak terlihat untuk menghemat beban server.
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    let first = true;
    const tick = async () => {
      if (cancelled) return;
      // Pemuatan pertama selalu dijalankan, walau halaman dibuka di tab latar
      if ((first || !document.hidden) && !pollingRef.current) {
        first = false;
        pollingRef.current = true;
        try {
          await Promise.all([fetchData(), fetchNodeDetails(selectedNodeId)]);
        } finally {
          pollingRef.current = false;
        }
      }
      if (!cancelled) timer = setTimeout(tick, 2500);
    };

    const onVisible = () => {
      if (!document.hidden) {
        if (timer) clearTimeout(timer);
        tick();
      }
    };

    tick();
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [selectedNodeId]);

  // Inisialisasi Peta Leaflet
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = L.map(mapRef.current, {
      center: [-2.5, 122.0], // Titik tengah Kepulauan Indonesia
      zoom: 5,
      zoomControl: true,
      attributionControl: true,
    });
    map.attributionControl.setPrefix(false);

    // Basemap Esri World Ocean (tanpa API key; tile CARTO kini mewajibkan key)
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Ocean/World_Ocean_Base/MapServer/tile/{z}/{y}/{x}',
      {
        maxZoom: 13,
        attribution: 'Tiles &copy; Esri — GEBCO, NOAA, NGDC, dkk.',
      },
    ).addTo(map);

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Perbarui Marker Peta saat data node berubah
  useEffect(() => {
    if (!mapInstanceRef.current || nodes.length === 0) return;

    const map = mapInstanceRef.current;

    nodes.forEach((node) => {
      const alertLvl = node.latest_thermal?.alert_level || 0;
      let color = '#10b981'; // No stress (hijau status)
      if (alertLvl === 1) color = '#facc15'; // Watch (kuning)
      if (alertLvl === 2) color = '#FF8A1F'; // Warning (Warning Orange brand)
      if (alertLvl === 3) color = '#EB505B'; // Alert 1 (Coral Red brand)
      if (alertLvl >= 4) color = '#B3261C'; // Alert 2 (coral gelap)

      const isSelected = node.id === selectedNodeId;

      if (!markersRef.current[node.id]) {
        const marker = L.circleMarker([node.latitude, node.longitude], {
          radius: isSelected ? 12 : 8,
          fillColor: color,
          color: '#ffffff',
          weight: isSelected ? 3 : 1.5,
          opacity: 1,
          fillOpacity: 0.85,
        }).addTo(map);

        marker.on('click', () => {
          setSelectedNodeId(node.id);
        });

        markersRef.current[node.id] = marker;
      } else {
        const marker = markersRef.current[node.id];
        marker.setStyle({
          fillColor: color,
          radius: isSelected ? 13 : 8,
          weight: isSelected ? 3 : 1.5,
        });
      }

      // Bind Popup Informasi
      const popupContent = `
        <div style="font-family: Montserrat, sans-serif; font-size: 12px; color: #0B2A44; min-width: 160px;">
          <b style="font-size: 13px;">${node.name}</b><br/>
          <span style="color: #456C91;">${node.region}</span><br/><hr style="margin: 4px 0; border: 0; border-top: 1px solid #D7E2EE;"/>
          🌡️ SST: <b>${node.latest_thermal?.sst?.toFixed(2) || '-'} °C</b><br/>
          📈 MMM: <b>${node.mmm_sst?.toFixed(2)} °C</b><br/>
          🔥 DHW: <b>${node.latest_thermal?.dhw?.toFixed(2) || '0.00'} °C-w</b><br/>
          🚨 Status: <b style="color: ${color};">${node.latest_thermal?.alert_label || 'Normal'}</b><br/>
          🔋 Baterai: <b>${node.battery}%</b>
        </div>
      `;
      markersRef.current[node.id].bindPopup(popupContent);
    });
  }, [nodes, selectedNodeId]);

  // Aksi Kontrol Simulator
  const handleControl = async (action: string, newScenario?: string, lossRate?: number) => {
    try {
      await fetch('/api/simulator/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          scenario: newScenario !== undefined ? newScenario : scenario,
          packet_loss_rate: lossRate !== undefined ? lossRate : packetLossRate,
        }),
      });
      fetchData();
      fetchNodeDetails(selectedNodeId);
    } catch (err) {
      console.error('Failed to control simulator:', err);
    }
  };

  // Injeksi Gangguan Sensor
  const handleInjectFault = async (faultType: string, param: string = 'temperature', magnitude: number = 3.5) => {
    try {
      await fetch('/api/simulator/inject-fault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          node_id: selectedNodeId,
          fault_type: faultType,
          param,
          magnitude,
        }),
      });
      fetchData();
      fetchNodeDetails(selectedNodeId);
    } catch (err) {
      console.error('Failed to inject fault:', err);
    }
  };

  // Acknowledge Alert
  const handleAcknowledge = async (alertId: number) => {
    try {
      await fetch(`/api/alerts/${alertId}/acknowledge`, { method: 'POST' });
      fetchData();
    } catch (err) {
      console.error('Failed to acknowledge alert:', err);
    }
  };

  // Bisa undefined pada render pertama, sebelum /api/nodes selesai di-fetch
  const selectedNode: typeof nodes[number] | undefined =
    nodes.find((n) => n.id === selectedNodeId) || nodes[0];
  const maxDhwAllNodes = Math.max(...nodes.map((n) => n.latest_thermal?.dhw || 0), 0);
  const highestAlertLevel = Math.max(...nodes.map((n) => n.latest_thermal?.alert_level || 0), 0);

  const getAlertBadgeColor = (lvl: number) => {
    if (lvl === 0) return 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40';
    if (lvl === 1) return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/40';
    if (lvl === 2) return 'bg-orange-500/20 text-orange-400 border-orange-500/40';
    if (lvl === 3) return 'bg-rose-500/20 text-rose-400 border-rose-500/40';
    return 'bg-pink-500/20 text-pink-400 border-pink-500/40';
  };

  const getAlertLabel = (lvl: number) => {
    if (lvl === 0) return 'No Stress';
    if (lvl === 1) return 'Bleaching Watch';
    if (lvl === 2) return 'Bleaching Warning';
    if (lvl === 3) return 'Alert Level 1';
    return 'Alert Level 2 (Severe Mortality)';
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* 1. HEADER UTAMA */}
      <header className="border-b border-slate-800/80 bg-slate-900/90 backdrop-blur sticky top-0 z-50 px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <img
            src="/brand/segara-icon-192.png"
            alt="Logo SEGARA"
            width={44}
            height={44}
            className="h-11 w-11 rounded-xl shadow-lg shadow-cyan-900/40"
          />
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-wide text-white">
                SEGARA
              </h1>
              <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-950 border border-cyan-800 text-cyan-300 font-mono">
                v1.0 • LoRaWAN 12-Byte
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Sistem Early-warning Gangguan termal Atas terumbu kaRAng (NOAA CRW Methodology)
            </p>
          </div>
        </div>

        {/* Panel Pengendali Simulator Telemetri */}
        <div className="flex items-center flex-wrap gap-2.5 bg-slate-950/70 p-1.5 rounded-xl border border-slate-800">
          <div className="flex items-center space-x-1 px-2 text-xs text-slate-400">
            <Radio className={`h-3.5 w-3.5 ${isRunning ? 'text-emerald-400 animate-pulse' : 'text-slate-500'}`} />
            <span>Siklus: <b>#{stepCount}</b></span>
          </div>

          {/* Status koneksi backend */}
          <div
            role="status"
            aria-live="polite"
            className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11px] font-medium ${
              serverOnline === false
                ? 'bg-rose-500/15 text-rose-300 border border-rose-500/40'
                : 'text-slate-400'
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                serverOnline === false ? 'bg-rose-500 animate-pulse' : serverOnline ? 'bg-emerald-400' : 'bg-slate-500'
              }`}
            />
            {serverOnline === false ? 'Server tidak merespons' : serverOnline ? 'Terhubung' : 'Menghubungkan…'}
          </div>

          {/* Skenario Selector */}
          <select
            value={scenario}
            onChange={(e) => {
              setScenario(e.target.value);
              handleControl('control', e.target.value);
            }}
            className="bg-slate-900 text-xs text-slate-200 rounded-lg border border-slate-700 px-2.5 py-1.5 focus:outline-none focus:border-cyan-500"
          >
            <option value="normal">Skenario: Normal Ocean</option>
            <option value="heatwave">Skenario: Marine Heatwave (MHW)</option>
            <option value="storm">Skenario: Badai & Kekeruhan Air</option>
            <option value="historical_replay">Replay: Data Historis Nyata NOAA</option>
          </select>

          {/* Play/Pause Button */}
          <button
            onClick={() => handleControl(isRunning ? 'stop' : 'start')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition-all ${
              isRunning
                ? 'bg-amber-600/20 text-amber-300 border border-amber-500/40 hover:bg-amber-600/30'
                : 'bg-emerald-600/20 text-emerald-300 border border-emerald-500/40 hover:bg-emerald-600/30'
            }`}
          >
            {isRunning ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            <span>{isRunning ? 'Pause' : 'Start'}</span>
          </button>

          {/* Step 1 siklus manual */}
          <button
            onClick={() => handleControl('step')}
            title="Kirim 1 siklus telemetri manual"
            className="p-1.5 bg-slate-800 hover:bg-slate-700 rounded-lg text-slate-300 border border-slate-700 transition"
          >
            <SkipForward className="h-3.5 w-3.5" />
          </button>

          {/* Reset */}
          <button
            onClick={() => handleControl('reset')}
            title="Reset Simulator"
            className="p-1.5 bg-slate-800 hover:bg-rose-950/40 hover:text-rose-400 rounded-lg text-slate-400 border border-slate-700 transition"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      {/* 2. RINGKASAN METRIK NASIONAL (KPI CARDS) */}
      <section className="px-6 py-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Status Peringatan Stres Termal */}
        <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Status Peringatan Nasional</span>
            <ShieldAlert className="h-4 w-4 text-rose-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className={`text-base font-bold px-2.5 py-1 rounded-lg border ${getAlertBadgeColor(highestAlertLevel)}`}>
              {getAlertLabel(highestAlertLevel)}
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            {highestAlertLevel >= 3
              ? 'Terjadi ancaman pemutihan karang signifikan di perairan terpilih!'
              : highestAlertLevel >= 1
              ? 'Suhu melampaui rata-rata klimatologi terpanas.'
              : 'Ekosistem karang dalam batas termal aman.'}
          </p>
        </div>

        {/* Card 2: DHW Maksimum Terakumulasi */}
        <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Degree Heating Weeks Puncak</span>
            <Flame className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold font-mono text-amber-300">
              {maxDhwAllNodes.toFixed(2)}
            </span>
            <span className="text-xs text-slate-400">°C-minggu</span>
          </div>
          <div className="mt-2 w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                maxDhwAllNodes >= 8 ? 'bg-rose-500' : maxDhwAllNodes >= 4 ? 'bg-orange-500' : 'bg-emerald-500'
              }`}
              style={{ width: `${Math.min(100, (maxDhwAllNodes / 8.0) * 100)}%` }}
            />
          </div>
          <p className="mt-1.5 text-[11px] text-slate-500">Ambang Kematian Massal: ≥ 8.0 °C-minggu</p>
        </div>

        {/* Card 3: Status Pelampung IoT Virtual */}
        <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Stasiun Pelampung Aktif</span>
            <Activity className="h-4 w-4 text-cyan-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold font-mono text-cyan-300">{nodes.length}</span>
            <span className="text-xs text-slate-400">/ 5 Node Kawasan</span>
          </div>
          <p className="mt-2 text-xs text-slate-400 flex items-center space-x-1">
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
            <span>Format Biner Kompak: <b>12 Byte Uplink</b></span>
          </p>
        </div>

        {/* Card 4: Quality Control & Packet Delivery */}
        <div className="bg-slate-900/70 border border-slate-800/80 rounded-2xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-slate-400">Laju Kelulusan QC Data</span>
            <Sliders className="h-4 w-4 text-teal-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold font-mono text-teal-300">
              {qcSummary ? qcSummary.pass_rate_percent.toFixed(1) : '100.0'}%
            </span>
            <span className="text-xs text-slate-400">
              ({qcSummary?.valid_samples || 0}/{qcSummary?.total_samples || 0})
            </span>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Paket Hilang Terdeteksi: <b className="text-rose-400">{qcSummary?.flags_breakdown.total_packets_dropped || 0}</b>
          </p>
        </div>
      </section>

      {/* 3. AREA UTAMA: PETA INTERAKTIF & PANEL KONTROL */}
      <main className="px-6 pb-6 flex-1 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* KOLOM KIRI (5 Kolom): PETA & PEMILIH STASIUN */}
        <div className="lg:col-span-5 flex flex-col space-y-4">
          {/* Card Peta Laut */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col h-[400px]">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                <MapPin className="h-4 w-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-slate-200">Peta Sebaran Pelampung Terumbu Karang</h3>
              </div>
              <span className="text-[11px] text-slate-400">Klik marker untuk analisis</span>
            </div>
            <div ref={mapRef} className="flex-1 rounded-xl overflow-hidden border border-slate-800" />
          </div>

          {/* Daftar Stasiun Pelampung */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
            <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center justify-between">
              <span>Stasiun Pengamatan ({nodes.length})</span>
              <span className="text-xs font-normal text-slate-400">Pilih untuk detail analitik</span>
            </h3>
            <div className="space-y-2">
              {nodes.map((node) => {
                const isSel = node.id === selectedNodeId;
                const thermal = node.latest_thermal;
                const alertLvl = thermal?.alert_level || 0;

                return (
                  <button
                    key={node.id}
                    onClick={() => setSelectedNodeId(node.id)}
                    className={`w-full text-left p-3 rounded-xl border transition-all flex items-center justify-between ${
                      isSel
                        ? 'bg-cyan-950/40 border-cyan-500/60 shadow-sm'
                        : 'bg-slate-950/50 border-slate-800 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start space-x-3">
                      <div
                        className={`h-7 w-7 rounded-lg flex items-center justify-center font-bold text-xs ${
                          isSel ? 'bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {node.id}
                      </div>
                      <div>
                        <div className="text-xs font-semibold text-slate-200">{node.name}</div>
                        <div className="text-[11px] text-slate-400">{node.region}</div>
                      </div>
                    </div>

                    <div className="text-right">
                      <div className="text-xs font-mono font-medium text-slate-200">
                        {thermal?.sst?.toFixed(2)} °C
                      </div>
                      <span className={`text-[10px] px-1.5 py-0.5 rounded border ${getAlertBadgeColor(alertLvl)}`}>
                        {thermal?.alert_label || 'Normal'}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* KOLOM KANAN (7 Kolom): DETAIL ANALITIK, QC, & EVALUASI */}
        <div className="lg:col-span-7 flex flex-col space-y-4">
          {/* TAB NAVIGASI */}
          <div className="flex border-b border-slate-800 space-x-2 text-xs">
            <button
              onClick={() => setActiveTab('analytics')}
              className={`pb-2.5 px-3 font-medium transition flex items-center space-x-1.5 ${
                activeTab === 'analytics'
                  ? 'border-b-2 border-cyan-400 text-cyan-300'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <BarChart3 className="h-4 w-4" />
              <span>Stres Termal & Forecast</span>
            </button>
            <button
              onClick={() => setActiveTab('qc')}
              className={`pb-2.5 px-3 font-medium transition flex items-center space-x-1.5 ${
                activeTab === 'qc'
                  ? 'border-b-2 border-cyan-400 text-cyan-300'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Sliders className="h-4 w-4" />
              <span>Kendali Mutu (QC) & Injeksi Gangguan</span>
            </button>
            <button
              onClick={() => setActiveTab('alerts')}
              className={`pb-2.5 px-3 font-medium transition flex items-center space-x-1.5 ${
                activeTab === 'alerts'
                  ? 'border-b-2 border-cyan-400 text-cyan-300'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Bell className="h-4 w-4" />
              <span>Log Notifikasi ({alerts.length})</span>
            </button>
            <button
              onClick={() => {
                setActiveTab('eval');
                fetchEvaluationMetrics();
              }}
              className={`pb-2.5 px-3 font-medium transition flex items-center space-x-1.5 ${
                activeTab === 'eval'
                  ? 'border-b-2 border-cyan-400 text-cyan-300'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <TrendingUp className="h-4 w-4" />
              <span>Evaluasi Ilmiah & Benchmark</span>
            </button>
          </div>

          {/* KONTEN TAB 1: ANALITIK STRES TERMAL & DHW */}
          {/* Data node belum termuat: tampilkan status muat, bukan crash */}
          {!selectedNode && (activeTab === 'analytics' || activeTab === 'qc') && (
            <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-8 flex flex-col items-center justify-center gap-3 text-sm text-slate-400">
              <img src="/brand/segara-icon-192.png" alt="" aria-hidden="true" className="h-12 w-12 rounded-xl animate-pulse" />
              Memuat data stasiun pelampung…
            </div>
          )}

          {activeTab === 'analytics' && selectedNode && (
            <div className="space-y-4">
              {/* Header Info Node Terpilih */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-bold text-slate-100">{selectedNode.name}</h2>
                  <p className="text-xs text-slate-400">{selectedNode.region} • Kedalaman Sensor: {selectedNode.depth_m} m</p>
                </div>
                <div className="flex items-center space-x-4 text-xs font-mono">
                  <div className="text-center">
                    <span className="text-[10px] text-slate-500 block uppercase">MMM</span>
                    <span className="font-bold text-slate-200">{selectedNode.mmm_sst?.toFixed(2)} °C</span>
                  </div>
                  <div className="text-center">
                    <span className="text-[10px] text-slate-500 block uppercase">Ambang Bleach</span>
                    <span className="font-bold text-amber-400">{selectedNode.bleaching_threshold?.toFixed(2)} °C</span>
                  </div>
                  <div className="text-center">
                    <span className="text-[10px] text-slate-500 block uppercase">DHW Terkini</span>
                    <span className="font-bold text-rose-400">
                      {selectedNode.latest_thermal?.dhw?.toFixed(2) || '0.00'} °C-w
                    </span>
                  </div>
                  <div className="text-center">
                    <span className="text-[10px] text-slate-500 block uppercase">Baterai</span>
                    <span className="font-bold text-emerald-400">{selectedNode.battery}%</span>
                  </div>
                </div>
              </div>

              {/* Grafik 1: Suhu Permukaan Laut (SST) vs MMM & Bleaching Threshold */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <Thermometer className="h-4 w-4 text-cyan-400" />
                    <h4 className="text-xs font-semibold text-slate-200">
                      Deret Waktu Suhu Permukaan Laut (SST) vs Ambang Batas
                    </h4>
                  </div>
                  <div className="flex items-center space-x-3 text-[11px]">
                    <span className="flex items-center space-x-1">
                      <span className="w-2.5 h-0.5 bg-cyan-400 inline-block" />
                      <span className="text-slate-400">SST</span>
                    </span>
                    <span className="flex items-center space-x-1">
                      <span className="w-2.5 h-0.5 bg-emerald-400 dashed inline-block" />
                      <span className="text-slate-400">MMM ({selectedNode.mmm_sst}°C)</span>
                    </span>
                    <span className="flex items-center space-x-1">
                      <span className="w-2.5 h-0.5 bg-rose-400 inline-block" />
                      <span className="text-slate-400">Threshold (+1°C)</span>
                    </span>
                  </div>
                </div>

                {/* Visualisasi Garis Grafis Sederhana Responsif SVG */}
                <div className="h-44 w-full pt-3">
                  {thermalHistory.length > 0 ? (
                    <svg className="w-full h-full overflow-visible" viewBox="0 0 600 140">
                      {/* Grid Lines */}
                      <line x1="0" y1="20" x2="600" y2="20" stroke="#1A3D5F" strokeDasharray="4" />
                      <line x1="0" y1="70" x2="600" y2="70" stroke="#1A3D5F" strokeDasharray="4" />
                      <line x1="0" y1="120" x2="600" y2="120" stroke="#1A3D5F" strokeDasharray="4" />

                      {/* Ambang Batas Garis Horisontal */}
                      {/* Range suhu: 28.0°C (y=130) sampai 32.0°C (y=10) */}
                      {(() => {
                        const minT = 28.0;
                        const maxT = 32.5;
                        const getY = (val: number) => 130 - ((val - minT) / (maxT - minT)) * 120;

                        const mmmY = getY(selectedNode.mmm_sst);
                        const threshY = getY(selectedNode.bleaching_threshold);

                        // Titik data SST
                        const points = thermalHistory.map((pt, idx) => {
                          const x = (idx / Math.max(1, thermalHistory.length - 1)) * 580 + 10;
                          const y = getY(pt.sst);
                          return `${x},${y}`;
                        }).join(' ');

                        return (
                          <>
                            {/* Garis MMM */}
                            <line x1="10" y1={mmmY} x2="590" y2={mmmY} stroke="#10b981" strokeWidth="1.5" strokeDasharray="4" />
                            {/* Garis Bleaching Threshold */}
                            <line x1="10" y1={threshY} x2="590" y2={threshY} stroke="#EB505B" strokeWidth="1.5" strokeDasharray="3" />

                            {/* Jalur SST */}
                            <polyline
                              fill="none"
                              stroke="#45C5E8"
                              strokeWidth="2.5"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              points={points}
                            />

                            {/* Titik-titik data */}
                            {thermalHistory.map((pt, idx) => {
                              const x = (idx / Math.max(1, thermalHistory.length - 1)) * 580 + 10;
                              const y = getY(pt.sst);
                              const isHotspot = pt.hotspot >= 1.0;
                              return (
                                <circle
                                  key={idx}
                                  cx={x}
                                  cy={y}
                                  r={isHotspot ? 3.5 : 2}
                                  fill={isHotspot ? '#EB505B' : '#45C5E8'}
                                />
                              );
                            })}
                          </>
                        );
                      })()}
                    </svg>
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-slate-500">
                      Menunggu akumulasi telemetri deret waktu...
                    </div>
                  )}
                </div>
              </div>

              {/* Grafik 2: Akumulasi Degree Heating Weeks (DHW) */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center space-x-2">
                    <Flame className="h-4 w-4 text-amber-400" />
                    <h4 className="text-xs font-semibold text-slate-200">
                      Akumulasi Degree Heating Weeks (DHW) 12-Minggu
                    </h4>
                  </div>
                  <span className="text-[11px] text-slate-400">
                    Nilai Terkini:{' '}
                    <b className="text-amber-300 font-mono">
                      {selectedNode.latest_thermal?.dhw?.toFixed(2) || '0.00'} °C-w
                    </b>
                  </span>
                </div>

                <div className="h-32 w-full pt-2">
                  {thermalHistory.length > 0 ? (
                    <svg className="w-full h-full overflow-visible" viewBox="0 0 600 110">
                      {/* Ambang batas DHW 4.0 (Alert 1) dan 8.0 (Alert 2) */}
                      {(() => {
                        const maxDHW = 10.0;
                        const getY = (val: number) => 100 - (val / maxDHW) * 90;
                        const alert1Y = getY(4.0);
                        const alert2Y = getY(8.0);

                        const points = thermalHistory.map((pt, idx) => {
                          const x = (idx / Math.max(1, thermalHistory.length - 1)) * 580 + 10;
                          const y = getY(pt.dhw);
                          return `${x},${y}`;
                        }).join(' ');

                        return (
                          <>
                            {/* Garis Alert 1 */}
                            <line x1="10" y1={alert1Y} x2="590" y2={alert1Y} stroke="#FF8A1F" strokeWidth="1" strokeDasharray="3" />
                            <text x="592" y={alert1Y + 3} fill="#FF8A1F" fontSize="9">4.0</text>
                            {/* Garis Alert 2 */}
                            <line x1="10" y1={alert2Y} x2="590" y2={alert2Y} stroke="#B3261C" strokeWidth="1" strokeDasharray="3" />
                            <text x="592" y={alert2Y + 3} fill="#B3261C" fontSize="9">8.0</text>

                            {/* Poligon Isi Area DHW */}
                            <polygon
                              fill="rgba(245, 158, 11, 0.15)"
                              points={`10,100 ${points} 590,100`}
                            />
                            {/* Garis Kurva DHW */}
                            <polyline
                              fill="none"
                              stroke="#FF8A1F"
                              strokeWidth="2.5"
                              points={points}
                            />
                          </>
                        );
                      })()}
                    </svg>
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-slate-500">
                      Data DHW belum tersedia
                    </div>
                  )}
                </div>
              </div>

              {/* Panel 3: Proyeksi Peramalan 14 Hari (Forecasting) */}
              {forecastData && (
                <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex items-center space-x-2">
                      <TrendingUp className="h-4 w-4 text-teal-400" />
                      <h4 className="text-xs font-semibold text-slate-200">
                        Proyeksi Trajektori Suhu & DHW (14 Hari ke Depan)
                      </h4>
                    </div>
                    <span className="text-[11px] text-teal-300 font-mono">
                      Proyeksi:{' '}
                      <b className="px-1.5 py-0.5 rounded bg-teal-950 border border-teal-800">
                        {forecastData.projected_alert_level}
                      </b>
                    </span>
                  </div>

                  <div className="grid grid-cols-3 gap-3 text-center text-xs">
                    <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
                      <span className="text-[11px] text-slate-400 block">Lead Time ke Warning</span>
                      <span className="text-sm font-bold font-mono text-amber-300">
                        {forecastData.days_to_warning ? `${forecastData.days_to_warning} Hari` : 'Aman (>14h)'}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
                      <span className="text-[11px] text-slate-400 block">Lead Time ke Alert 1</span>
                      <span className="text-sm font-bold font-mono text-rose-300">
                        {forecastData.days_to_alert_1 ? `${forecastData.days_to_alert_1} Hari` : 'Aman (>14h)'}
                      </span>
                    </div>
                    <div className="p-2.5 rounded-xl bg-slate-950/60 border border-slate-800">
                      <span className="text-[11px] text-slate-400 block">Akurasi Model vs Baseline</span>
                      <span className="text-sm font-bold font-mono text-cyan-300">
                        MAE: {forecastData.metrics?.model_mae ?? forecastData.metrics?.mae ?? 'tidak tersedia'}{forecastData.metrics?.model_mae || forecastData.metrics?.mae ? ' °C' : ''}
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* KONTEN TAB 2: QUALITY CONTROL & INJEKSI GANGGUAN */}
          {activeTab === 'qc' && selectedNode && (
            <div className="space-y-4">
              {/* Ringkasan Status QC Flag */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center space-x-2">
                  <Sliders className="h-4 w-4 text-cyan-400" />
                  <span>Statistik Filter Kendali Mutu (QC Flags)</span>
                </h3>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <span className="text-slate-400 block">Lonjakan (Spikes)</span>
                    <span className="text-lg font-mono font-bold text-amber-400">
                      {qcSummary?.flags_breakdown.spike_violations || 0}
                    </span>
                  </div>
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <span className="text-slate-400 block">Sensor Macet (Stuck)</span>
                    <span className="text-lg font-mono font-bold text-rose-400">
                      {qcSummary?.flags_breakdown.stuck_sensors || 0}
                    </span>
                  </div>
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <span className="text-slate-400 block">Penyimpangan (Drift)</span>
                    <span className="text-lg font-mono font-bold text-purple-400">
                      {qcSummary?.flags_breakdown.drift_sensors || 0}
                    </span>
                  </div>
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <span className="text-slate-400 block">Di Luar Rentang Fisik</span>
                    <span className="text-lg font-mono font-bold text-red-400">
                      {qcSummary?.flags_breakdown.range_violations || 0}
                    </span>
                  </div>
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <span className="text-slate-400 block">Paket Hilang (Loss)</span>
                    <span className="text-lg font-mono font-bold text-orange-400">
                      {qcSummary?.flags_breakdown.total_packets_dropped || 0}
                    </span>
                  </div>
                  <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                    <span className="text-slate-400 block">Baterai Rendah</span>
                    <span className="text-lg font-mono font-bold text-yellow-400">
                      {qcSummary?.flags_breakdown.battery_low_warnings || 0}
                    </span>
                  </div>
                </div>
              </div>

              {/* Sandbox Injeksi Gangguan Terkontrol */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-2 flex items-center space-x-2">
                  <Zap className="h-4 w-4 text-amber-400" />
                  <span>Sandbox Injeksi Gangguan Terkontrol (Uji Ketahanan Pipeline)</span>
                </h3>
                <p className="text-xs text-slate-400 mb-4">
                  Suntikkan galat sensor pada <b className="text-cyan-300">{selectedNode.name}</b> untuk menguji apakah pipeline QC secara otomatis mendeteksi dan mengisolasi data anomali.
                </p>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                  <button
                    onClick={() => handleInjectFault('spike', 'temperature', 3.5)}
                    className="p-2.5 rounded-xl bg-amber-950/30 border border-amber-800/60 hover:bg-amber-900/40 text-left transition"
                  >
                    <span className="text-xs font-semibold text-amber-300 block">Injeksi Lonjakan Suhu</span>
                    <span className="text-[10px] text-slate-400">+3.5 °C (Spike Test)</span>
                  </button>

                  <button
                    onClick={() => handleInjectFault('stuck', 'temperature', 0)}
                    className="p-2.5 rounded-xl bg-rose-950/30 border border-rose-800/60 hover:bg-rose-900/40 text-left transition"
                  >
                    <span className="text-xs font-semibold text-rose-300 block">Injeksi Sensor Macet</span>
                    <span className="text-[10px] text-slate-400">Konstan 8 Siklus (Stuck)</span>
                  </button>

                  <button
                    onClick={() => handleInjectFault('drift', 'ph', 0)}
                    className="p-2.5 rounded-xl bg-purple-950/30 border border-purple-800/60 hover:bg-purple-900/40 text-left transition"
                  >
                    <span className="text-xs font-semibold text-purple-300 block">Injeksi Drift pH</span>
                    <span className="text-[10px] text-slate-400">Penyimpangan elektroda</span>
                  </button>

                  <button
                    onClick={() => handleInjectFault('out_of_range', 'temperature', 0)}
                    className="p-2.5 rounded-xl bg-red-950/30 border border-red-800/60 hover:bg-red-900/40 text-left transition"
                  >
                    <span className="text-xs font-semibold text-red-300 block">Injeksi Di Luar Batas</span>
                    <span className="text-[10px] text-slate-400">Suhu 48.5 °C (Range Test)</span>
                  </button>

                  <button
                    onClick={() => handleControl('control', 'heatwave')}
                    className="p-2.5 rounded-xl bg-cyan-950/30 border border-cyan-800/60 hover:bg-cyan-900/40 text-left transition"
                  >
                    <span className="text-xs font-semibold text-cyan-300 block">Simulasi Gelombang Panas</span>
                    <span className="text-[10px] text-slate-400">Marine Heatwave (+2.2°C)</span>
                  </button>

                  <button
                    onClick={() => handleControl('control', 'normal')}
                    className="p-2.5 rounded-xl bg-emerald-950/30 border border-emerald-800/60 hover:bg-emerald-900/40 text-left transition"
                  >
                    <span className="text-xs font-semibold text-emerald-300 block">Bersihkan Gangguan</span>
                    <span className="text-[10px] text-slate-400">Pulihkan ke Kondisi Normal</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* KONTEN TAB 3: LOG PERINGATAN DINI & TELEGRAM PREVIEW */}
          {activeTab === 'alerts' && (
            <div className="space-y-4">
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                <h3 className="text-sm font-semibold text-slate-200 mb-3 flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <Bell className="h-4 w-4 text-rose-400" />
                    <span>Riwayat Peringatan Dini Stres Termal ({alerts.length})</span>
                  </div>
                  <span className="text-xs text-slate-400">Auto-deduplicated</span>
                </h3>

                <div className="space-y-2.5 max-h-[460px] overflow-y-auto pr-1">
                  {alerts.length > 0 ? (
                    alerts.map((al) => (
                      <div
                        key={al.id}
                        className={`p-3 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 ${
                          al.alert_level >= 3
                            ? 'bg-rose-950/20 border-rose-800/60'
                            : 'bg-amber-950/20 border-amber-800/60'
                        }`}
                      >
                        <div className="flex items-start space-x-2.5">
                          <AlertTriangle
                            className={`h-4 w-4 mt-0.5 shrink-0 ${
                              al.alert_level >= 3 ? 'text-rose-400' : 'text-amber-400'
                            }`}
                          />
                          <div>
                            <div className="flex items-center space-x-2">
                              <span className="text-xs font-bold text-slate-200">{al.node_name}</span>
                              <span
                                className={`text-[10px] px-1.5 py-0.2 rounded border font-mono ${getAlertBadgeColor(
                                  al.alert_level
                                )}`}
                              >
                                {al.alert_type}
                              </span>
                            </div>
                            <p className="text-[11px] text-slate-300 mt-1 whitespace-pre-line font-mono">
                              {cleanAlertMessage(al.message)}
                            </p>
                          </div>
                        </div>

                        {!al.acknowledged ? (
                          <button
                            onClick={() => handleAcknowledge(al.id)}
                            className="text-xs px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-emerald-950 hover:text-emerald-300 border border-slate-700 transition flex items-center space-x-1 shrink-0"
                          >
                            <Check className="h-3 w-3" />
                            <span>Tindak Lanjuti</span>
                          </button>
                        ) : (
                          <span className="text-[11px] text-emerald-400 flex items-center space-x-1 shrink-0">
                            <CheckCircle2 className="h-3.5 w-3.5" />
                            <span>Ditindaklanjuti</span>
                          </span>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="py-8 text-center text-xs text-slate-500">
                      Tidak ada peringatan aktif. Seluruh perairan dalam ambang aman.
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* KONTEN TAB 4: EVALUASI ILMIAH & BENCHMARK */}
          {activeTab === 'eval' && (
            <div className="space-y-4">
              <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-4">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-2">
                    <TrendingUp className="h-4 w-4 text-cyan-400" />
                    <h3 className="text-sm font-semibold text-slate-200">
                      Hasil Pengujian & Evaluasi Ilmiah (Fase 6)
                    </h3>
                  </div>
                  <button
                    onClick={fetchEvaluationMetrics}
                    disabled={loading}
                    className="text-xs px-2.5 py-1 bg-cyan-950/60 hover:bg-cyan-900/80 text-cyan-300 border border-cyan-800 rounded-lg flex items-center space-x-1 transition"
                  >
                    <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                    <span>Perbarui Benchmark</span>
                  </button>
                </div>

                {evalMetrics ? (
                  <div className="space-y-4 text-xs">
                    {/* 1. Dampak Packet Loss terhadap Galat DHW & Keterlambatan Peringatan */}
                    <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-slate-200 block">
                          1. Dampak Rugi Paket terhadap DHW (Monte Carlo Simulasi Berpasangan)
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                          {evalMetrics.packet_loss_monte_carlo
                            ? `${Object.values(evalMetrics.packet_loss_monte_carlo)[0]?.monte_carlo_runs ?? 0} Seed per Tingkat`
                            : 'Data tidak tersedia'}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mb-2.5">
                        Desain: {evalMetrics.packet_loss_monte_carlo
                          ? Object.values(evalMetrics.packet_loss_monte_carlo)[0]?.reference_design
                          : '-'} &bull; Interval{' '}
                        {evalMetrics.packet_loss_monte_carlo
                          ? Object.values(evalMetrics.packet_loss_monte_carlo)[0]?.telemetry_interval_hours
                          : '-'}{' '}
                        jam &bull; {evalMetrics.packet_loss_monte_carlo
                          ? Object.values(evalMetrics.packet_loss_monte_carlo)[0]?.missing_packet_strategy
                          : '-'}
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-center">
                        {evalMetrics.packet_loss_monte_carlo &&
                          Object.entries(evalMetrics.packet_loss_monte_carlo).map(([key, val]) => (
                            <div key={key} className="p-2.5 bg-slate-900 rounded-lg border border-slate-800/80 text-left">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-[11px] font-bold text-amber-300">Loss {val.target_loss_rate_pct}%</span>
                                <span className="text-[10px] text-slate-400">
                                  PDR {val.measured_pdr_mean} &plusmn; {val.measured_pdr_std}%
                                </span>
                              </div>
                              <div className="text-[11px] text-slate-300 space-y-0.5">
                                <div>
                                  Galat DHW: <b className="font-mono text-cyan-300">{val.dhw_error_mae_mean} &plusmn; {val.dhw_error_mae_std} &deg;C-w</b>
                                </div>
                                <div>
                                  Bias Maksimum: <b className="font-mono text-rose-300">{val.max_dhw_bias_mean} &deg;C-w</b>
                                </div>
                                <div>
                                  Tunda Alert 1:{' '}
                                  <b className="font-mono text-amber-400">
                                    {val.alert_1_delay_days_mean === null
                                      ? 'tidak terukur'
                                      : `${val.alert_1_delay_days_mean} \u00b1 ${val.alert_1_delay_days_std} hari`}
                                  </b>
                                  <span className="text-[10px] text-slate-500">
                                    {' '}({val.alert_1_delay_valid_runs}/{val.monte_carlo_runs} run)
                                  </span>
                                </div>
                              </div>
                            </div>
                          ))}
                      </div>
                      <p className="text-[10px] text-slate-500 mt-2">
                        Semua nilai berasal dari jalur SST sintetis yang sama per seed (paired), bukan data lapangan. Kebocoran paket dibangkitkan Bernoulli independen.
                      </p>
                    </div>

                    {/* 2. Uji Fungsional Logika Aturan QC */}
                    <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-slate-200 block">
                          2. Uji Fungsional Aturan Quality Control (Rule Verification Test)
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                          {evalMetrics.quality_control_functional_verification?.test_type ?? 'Tidak dijalankan'}
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-400 mb-2">
                        {evalMetrics.quality_control_functional_verification?.scope_note}
                      </p>

                      <div className="mb-2">
                        <span className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
                          Kontrol Bersih ({evalMetrics.quality_control_functional_verification?.clean_control.cycles} siklus)
                        </span>
                        <div className="grid grid-cols-4 gap-2 text-center">
                          {Object.entries(
                            evalMetrics.quality_control_functional_verification?.clean_control
                              .critical_flag_counts_per_rule ?? {}
                          ).map(([rule, count]) => (
                            <div key={rule} className="p-2 bg-slate-900 rounded-lg">
                              <span className="text-[10px] text-slate-400 block">{rule.replace('_FAIL', '')}</span>
                              <span
                                className={`text-sm font-bold font-mono ${
                                  count === 0 ? 'text-emerald-300' : 'text-rose-400'
                                }`}
                              >
                                {count}
                              </span>
                            </div>
                          ))}
                        </div>
                        <p className="text-[10px] text-slate-500 mt-1">
                          {evalMetrics.quality_control_functional_verification?.clean_control.design}
                        </p>
                      </div>

                      <div className="mb-2">
                        <span className="text-[10px] uppercase tracking-wide text-slate-500 block mb-1">
                          Kurva Sensitivitas Lonjakan (ambang 1,5 &deg;C, 5 ulangan per titik)
                        </span>
                        <div className="space-y-1">
                          {Object.entries(
                            evalMetrics.quality_control_functional_verification?.spike_sensitivity_curve ?? {}
                          ).map(([k, s]) => (
                            <div key={k} className="flex items-center justify-between px-2 py-1 bg-slate-900 rounded-lg">
                              <span className="text-[11px] font-mono text-slate-300">
                                &Delta; {s.spike_delta_celsius} &deg;C
                              </span>
                              <span className="text-[10px] text-slate-500">vs ambang {s.threshold_celsius} &deg;C</span>
                              <span
                                className={`text-[11px] font-mono font-bold ${
                                  s.detected_count === 0 ? 'text-slate-400' : 'text-amber-300'
                                }`}
                              >
                                {s.detected_count}/{s.trials} terdeteksi
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">Stuck (jendela 6)</span>
                          <span className="text-xs font-bold font-mono text-cyan-300">
                            deteksi ke-{evalMetrics.quality_control_functional_verification?.stuck_rule_case.first_detection_cycle ?? '-'}
                          </span>
                          <span className="text-[10px] text-slate-500 block">
                            {evalMetrics.quality_control_functional_verification?.stuck_rule_case.detected_cycles ?? 0} siklus
                          </span>
                        </div>
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">Drift (jendela 24)</span>
                          <span className="text-xs font-bold font-mono text-teal-300">
                            deteksi ke-{evalMetrics.quality_control_functional_verification?.drift_rule_case.first_detection_cycle ?? '-'}
                          </span>
                          <span className="text-[10px] text-slate-500 block">
                            {evalMetrics.quality_control_functional_verification?.drift_rule_case.detected_cycles ?? 0} siklus
                          </span>
                        </div>
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">Range</span>
                          <span className="text-xs font-bold font-mono text-emerald-300">
                            {evalMetrics.quality_control_functional_verification?.range_rule_case.detected_count ?? 0}/
                            {evalMetrics.quality_control_functional_verification?.range_rule_case.trials ?? 0}
                          </span>
                          <span className="text-[10px] text-slate-500 block">nilai di luar 20&ndash;35 &deg;C</span>
                        </div>
                      </div>

                      <div className="mt-2 p-2 bg-slate-900/60 rounded-lg border border-slate-800/60">
                        <span className="text-[10px] uppercase tracking-wide text-slate-500 block mb-0.5">
                          Kontrol Positif Palsu Lonjakan
                        </span>
                        <span className="text-[11px] text-slate-300">
                          {evalMetrics.quality_control_functional_verification?.spike_false_positive_control.cycles ?? 0} siklus dengan
                          lonjakan {evalMetrics.quality_control_functional_verification?.spike_false_positive_control.subthreshold_bumps_celsius ?? 0} &deg;C
                          &rarr; {evalMetrics.quality_control_functional_verification?.spike_false_positive_control.spike_flag_count ?? 0} flag
                        </span>
                      </div>

                      {Array.isArray(evalMetrics.quality_control_functional_verification?.limitations) && (
                        <ul className="mt-2 text-[10px] text-slate-500 list-disc pl-4 space-y-0.5">
                          {evalMetrics.quality_control_functional_verification?.limitations.map((lim, i) => (
                            <li key={i}>{lim}</li>
                          ))}
                        </ul>
                      )}
                    </div>

                    {/* 3. Uji Konsistensi Internal Algoritma DHW */}
                    <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                      <span className="font-semibold text-slate-200 block mb-1">
                        3. Uji Konsistensi Internal Algoritma DHW (bukan validasi NOAA)
                      </span>
                      <p className="text-[11px] text-slate-400 mb-2">
                        Pembanding: {evalMetrics.dhw_algorithmic_verification?.reference_source.reference_kind ?? '-'} &bull; Status provenans:{' '}
                        {evalMetrics.dhw_algorithmic_verification?.reference_source.provenance_status ?? '-'}
                      </p>
                      <div className="grid grid-cols-3 gap-2 text-center">
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">MAE vs Kolom Pembanding</span>
                          <span className="text-sm font-bold font-mono text-amber-300">
                            {evalMetrics.dhw_algorithmic_verification?.agreement_with_reference_column.mae_celsius_weeks ?? '-'} &deg;C-w
                          </span>
                        </div>
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">RMSE</span>
                          <span className="text-sm font-bold font-mono text-cyan-300">
                            {evalMetrics.dhw_algorithmic_verification?.agreement_with_reference_column.rmse_celsius_weeks ?? '-'} &deg;C-w
                          </span>
                        </div>
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">Korelasi Pearson</span>
                          <span className="text-sm font-bold font-mono text-emerald-300">
                            {evalMetrics.dhw_algorithmic_verification?.agreement_with_reference_column.pearson_correlation ?? 'n/a'}
                          </span>
                        </div>
                      </div>
                      <p className="text-[10px] text-slate-500 mt-1">
                        {evalMetrics.dhw_algorithmic_verification?.agreement_with_reference_column.note}
                      </p>
                      <div className="mt-2 p-2 bg-rose-950/30 rounded-lg border border-rose-900/40">
                        <span className="text-[10px] uppercase tracking-wide text-rose-300/80 block mb-0.5">
                          Pemeriksaan Konsistensi Akumulasi 84 Hari
                        </span>
                        <span className="text-[11px] text-slate-300">
                          Rentang observasi {evalMetrics.dhw_algorithmic_verification?.internal_consistency_check.observation_span_days ?? '-'} hari
                          &lt; jendela {evalMetrics.dhw_algorithmic_verification?.internal_consistency_check.window_days ?? '-'} hari.
                          DHW komputasi turun {evalMetrics.dhw_algorithmic_verification?.internal_consistency_check.computed_dhw_decrease_steps ?? '-'} langkah,
                          kolom pembanding turun {evalMetrics.dhw_algorithmic_verification?.internal_consistency_check.reference_dhw_decrease_steps ?? '-'} langkah.
                        </span>
                        <p className="text-[11px] text-rose-200/90 mt-1">
                          {evalMetrics.dhw_algorithmic_verification?.internal_consistency_check.verdict}
                        </p>
                      </div>
                      <div className="mt-2 text-[10px] text-slate-500">
                        Skema peringatan: {evalMetrics.dhw_algorithmic_verification?.noaa_alert_system_version.implemented_version}
                        {' \u2014 '}
                        {evalMetrics.dhw_algorithmic_verification?.noaa_alert_system_version.note_on_2023_revision}
                      </div>
                    </div>

                    {/* 4. Evaluasi Peramalan Multi-Horizon vs Persistence Baseline */}
                    {evalMetrics.forecasting_multi_horizon_evaluation && (
                      <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-semibold text-slate-200 block">
                            4. Evaluasi Akurasi Peramalan Multi-Horizon vs Baseline Persistence
                          </span>
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded border ${
                              evalMetrics.forecasting_multi_horizon_evaluation.status === 'ok'
                                ? 'bg-emerald-950/60 text-emerald-300 border-emerald-800'
                                : 'bg-slate-800 text-slate-400 border-slate-700'
                            }`}
                          >
                            status: {evalMetrics.forecasting_multi_horizon_evaluation.status}
                          </span>
                        </div>
                        {evalMetrics.forecasting_multi_horizon_evaluation.status !== 'ok' ? (
                          <div className="text-[11px] text-slate-400 space-y-1">
                            <p>{evalMetrics.forecasting_multi_horizon_evaluation.reason}</p>
                            <p className="text-[10px] text-slate-500">
                              Sumber: {evalMetrics.forecasting_multi_horizon_evaluation.data_source} &bull; sampel node 1:{' '}
                              {evalMetrics.forecasting_multi_horizon_evaluation.samples_node_1} &bull; cadence{' '}
                              {evalMetrics.forecasting_multi_horizon_evaluation.cadence_days} hari
                            </p>
                            <p className="text-[10px] text-rose-200/80">
                              Tidak ada angka MAE per horizon yang dipublikasikan.
                            </p>
                          </div>
                        ) : (
                          <div className="grid grid-cols-3 gap-2 text-center mt-2">
                            {Object.entries(
                              evalMetrics.forecasting_multi_horizon_evaluation.horizon_benchmarks ?? {}
                            ).map(([hKey, hVal]) => (
                              <div key={hKey} className="p-2 bg-slate-900 rounded-lg">
                                <span className="text-[10px] text-slate-400 block uppercase">
                                  {hKey.replace('horizon_', '').replace('_', ' ')}
                                </span>
                                <div className="text-xs font-mono font-bold text-cyan-300 mt-0.5">
                                  Model: {hVal.model_mae} &deg;C
                                </div>
                                <div className="text-[10px] font-mono text-slate-400">
                                  Base: {hVal.baseline_mae} &deg;C
                                  {hVal.improvement_vs_persistence_pct === null
                                    ? ''
                                    : ` (${hVal.improvement_vs_persistence_pct > 0 ? '+' : ''}${hVal.improvement_vs_persistence_pct}%)`}
                                </div>
                                <div className="text-[10px] text-slate-500">
                                  {hVal.evaluated_origins} origin &bull; {hVal.horizon_steps} langkah
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}

                    {/* 5. Latensi Komputasi Dalam-Proses CPU */}
                    <div className="p-3 bg-slate-950/60 rounded-xl border border-slate-800">
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-semibold text-slate-200 block">
                          5. Profil Latensi Komputasi Dalam-Proses CPU (In-Process Latency)
                        </span>
                        <span className="text-[10px] text-slate-400">Enkoder &rarr; Dekoder &rarr; QC &rarr; SQLite</span>
                      </div>
                      <p className="text-[11px] text-slate-400 mb-2">
                        *Cakupan ukur hanya fungsi di dalam proses ({evalMetrics.in_process_execution_latency?.total_runs ?? 0} run).
                        Tidak mencakup:
                      </p>
                      <ul className="text-[10px] text-slate-500 list-disc pl-4 mb-2 space-y-0.5">
                        {(evalMetrics.in_process_execution_latency?.excluded_layers ?? []).map((layer, i) => (
                          <li key={i}>{layer}</li>
                        ))}
                      </ul>
                      <div className="grid grid-cols-4 gap-2 text-center">
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">Rata-rata</span>
                          <span className="text-xs font-bold font-mono text-cyan-300">
                            {evalMetrics.in_process_execution_latency?.mean_latency_ms} ms
                          </span>
                        </div>
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">Median</span>
                          <span className="text-xs font-bold font-mono text-teal-300">
                            {evalMetrics.in_process_execution_latency?.median_latency_ms} ms
                          </span>
                        </div>
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">P95</span>
                          <span className="text-xs font-bold font-mono text-amber-300">
                            {evalMetrics.in_process_execution_latency?.p95_latency_ms} ms
                          </span>
                        </div>
                        <div className="p-2 bg-slate-900 rounded-lg">
                          <span className="text-[10px] text-slate-400 block">P99</span>
                          <span className="text-xs font-bold font-mono text-rose-300">
                            {evalMetrics.in_process_execution_latency?.p99_latency_ms} ms
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="py-8 text-center text-xs text-slate-500">
                    Klik tombol "Perbarui Benchmark" untuk menjalankan evaluasi numerik komprehensif.
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>

      {/* FOOTER */}
      <footer className="border-t border-slate-900 px-6 py-3 bg-slate-950 text-slate-500 text-[11px] flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <img src="/brand/favicon-32.png" alt="" aria-hidden="true" width={16} height={16} className="h-4 w-4 rounded" />
          <span>
            SEGARA • Sistem Perangkat Lunak Peringatan Dini Pemutihan Karang Berbasis Simulasi IoT & NOAA CRW
            <span className="italic text-slate-400"> — “Laut lebih aman untuk masa depan.”</span>
          </span>
        </div>
        <div className="font-mono text-slate-600">
          Mosquitto MQTT • TimescaleDB/SQLite • FastAPI • React Leaflet
        </div>
      </footer>
    </div>
  );
}
