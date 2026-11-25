import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  CircleMarker,
  MapContainer,
  Rectangle,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import {
  Activity,
  CalendarDays,
  ChevronDown,
  CircleHelp,
  Download,
  Flame,
  Image as ImageIcon,
  Layers3,
  MapPin,
  Upload,
} from "lucide-react";

const MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
const CURRENT_DATE = new Date().toISOString().slice(0, 10);
const CURRENT_YEAR = Number(CURRENT_DATE.slice(0, 4));
const ANALYSIS_YEAR = 2024;
const DOWNLOAD_YEARS = Array.from({ length: CURRENT_YEAR - 1999 }, (_, index) => CURRENT_YEAR - index);
const NUMBER_FORMAT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const FACTOR_FORMAT = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
const INITIAL_FILTERS = {
  start: `${ANALYSIS_YEAR}-01-01`,
  end: `${ANALYSIS_YEAR}-12-31`,
  south: "-23",
  north: "-20",
  west: "-50",
  east: "-46",
};
const FIRE_VIEWS = {
  still: {
    label: "Imagem · 24 ago.",
    src: "/imagery/ribeirao-preto-2024-08-24-viirs.jpg",
    alt: "Imagem VIIRS/Suomi-NPP de 24 de agosto de 2024 na região de Ribeirão Preto, com anomalias térmicas destacadas.",
    title: "Anomalias térmicas em 24 de agosto de 2024",
    description: "Composição VIIRS/Suomi-NPP em cores verdadeiras com detecções térmicas destacadas.",
  },
  animation: {
    label: "Animação · 21–31 ago.",
    src: "/imagery/ribeirao-preto-fire-2024-aug.gif",
    alt: "Animação diária de imagens VIIRS/Suomi-NPP e anomalias térmicas na região de Ribeirão Preto, de 21 a 31 de agosto de 2024.",
    title: "Evolução diária de 21 a 31 de agosto de 2024",
    description: "Animação de 11 imagens VIIRS/Suomi-NPP, uma por dia, com a camada de anomalias térmicas.",
  },
};

function areaRequestLabel(status) {
  return {
    queued: "na fila",
    downloading: "baixando",
    harmonizing: "processando dados",
    ready: "concluído",
    partial: "período publicado parcial",
    cancelled: "cancelado",
    error: "erro",
  }[status] || status;
}

function sensorLabel(source) {
  return source === "MODIS_SP" ? "MODIS" : "VIIRS-Suomi-NPP";
}

function queryString(filters) {
  return new URLSearchParams(filters).toString();
}

function formatNumber(value) {
  return NUMBER_FORMAT.format(value || 0);
}

function formatNullable(value) {
  return value == null ? "—" : NUMBER_FORMAT.format(value);
}

function formatFactor(value) {
  return value == null ? "—" : FACTOR_FORMAT.format(value);
}

function formatInterval(calibration) {
  if (calibration?.ci_lower == null || calibration?.ci_upper == null) return "IC bootstrap 95% do fator indisponível";
  return `IC bootstrap 95% do fator ${formatFactor(calibration.ci_lower)}–${formatFactor(calibration.ci_upper)}`;
}

function formatDuration(seconds) {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} h ${remainder} min` : `${hours} h`;
}

function estimateDuration(estimate) {
  if (!estimate) return "";
  return `${formatDuration(estimate.estimated_seconds_min)}–${formatDuration(estimate.estimated_seconds_max)}`;
}

function ingestionLabel(status) {
  return {
    waiting_for_key: "AGUARDANDO CHAVE FIRMS",
    backfilling: "CARGA HISTÓRICA",
    harmonizing: "HARMONIZANDO",
    syncing: "ATUALIZANDO",
    ready: "ATUALIZADO",
    on_demand: "COLETA SOB DEMANDA",
    error: "ERRO NA COLETA",
  }[status] || "CONECTANDO À NASA FIRMS";
}

function FitMap({ bounds }) {
  const map = useMap();
  useEffect(() => {
    map.fitBounds(bounds, { padding: [28, 28], maxZoom: 7 });
  }, [bounds, map]);
  return null;
}

function MapAreaDrawer({ active, onComplete, onCancel }) {
  const [firstCorner, setFirstCorner] = useState(null);
  const [previewCorner, setPreviewCorner] = useState(null);

  useMapEvents({
    click(event) {
      if (!active) return;
      if (!firstCorner) {
        setFirstCorner(event.latlng);
        setPreviewCorner(event.latlng);
        return;
      }
      onComplete(firstCorner, event.latlng);
      setFirstCorner(null);
      setPreviewCorner(null);
    },
    mousemove(event) {
      if (active && firstCorner) setPreviewCorner(event.latlng);
    },
  });

  useEffect(() => {
    if (!active) {
      setFirstCorner(null);
      setPreviewCorner(null);
      return undefined;
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setFirstCorner(null);
        setPreviewCorner(null);
        onCancel();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [active, onCancel]);

  if (!firstCorner || !previewCorner) return null;
  return (
    <Rectangle
      bounds={[
        [Math.min(firstCorner.lat, previewCorner.lat), Math.min(firstCorner.lng, previewCorner.lng)],
        [Math.max(firstCorner.lat, previewCorner.lat), Math.max(firstCorner.lng, previewCorner.lng)],
      ]}
      pathOptions={{ color: "#ffc857", weight: 2, dashArray: "6 4", fillOpacity: 0.08 }}
    />
  );
}

function StatCard({ icon: Icon, label, value, note, accent = false, badge }) {
  return (
    <article className={`stat-card${accent ? " stat-card-accent" : ""}`}>
      <div className="stat-label"><span>{label}</span><Icon size={16} aria-hidden="true" /></div>
      {badge && <span className="calibration-badge">{badge}</span>}
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  );
}

function Heatmap({ years }) {
  if (!years.length) {
    return <div className="empty-inline">Não há focos harmonizados para esta área e período. Processe dados já armazenados ou solicite uma nova coleta FIRMS.</div>;
  }
  const recordedValues = years.flatMap((year) => year.months).filter((count) => count != null);
  const max = Math.max(1, ...recordedValues);
  const legendRanges = [1, 2, 3, 4, 5].map((level) => ({
    level,
    max: Math.ceil(max * (level / 5) ** 2),
  }));
  return (
    <div className="heatmap-scroll">
      <div className="heatmap">
        <div className="heatmap-row heatmap-head">
          <span className="year-label">Ano</span>
          {MONTHS.map((month) => <span key={month}>{month}</span>)}
          <span className="year-total">Total</span>
        </div>
        {years.map((year) => (
          <div className="heatmap-row" key={year.year}>
            <strong className="year-label">{year.year}</strong>
            {year.months.map((count, index) => {
              const strength = count > 0
                ? Math.max(1, Math.ceil(Math.sqrt(count / max) * 5))
                : 0;
              const label = count == null
                ? `${MONTHS[index]} ${year.year}: sem registros`
                : `${MONTHS[index]} ${year.year}: ${formatNumber(count)} detecções eq. Aqua`;
              return (
                <span
                  className={`heat-cell${count == null ? " heat-no-data" : strength ? ` heat-${strength}` : " heat-zero"}`}
                  key={`${year.year}-${index}`}
                  title={label}
                  aria-label={label}
                >
                  {count == null ? "—" : count ? formatNumber(count) : "0"}
                </span>
              );
            })}
            <strong className="year-total">{year.total.toLocaleString("pt-BR")}</strong>
          </div>
        ))}
      </div>
      <div className="heatmap-legend">
        <span>0</span>
        {legendRanges.map(({ level, max: upperBound }) => (
          <span className="heat-legend-step" key={level}>
            <i className={`heat-cell heat-${level}`} aria-hidden="true" />
            <small>{level === 1 ? `≤ ${upperBound}` : `≤ ${upperBound}`}</small>
          </span>
        ))}
        <span>Sem dado: —</span>
      </div>
    </div>
  );
}

function AnomalyHistory({ comparison }) {
  if (!comparison) return <div className="empty-inline">Carregando…</div>;
  const values = comparison.yearly_values || [];
  const max = Math.max(1, ...values.map((entry) => entry.value || 0));
  const range = comparison.historical_min == null
    ? "—"
    : `${formatNumber(comparison.historical_min)}–${formatNumber(comparison.historical_max)}`;
  return (
    <section className="panel anomaly-panel" aria-labelledby="anomaly-history-title">
      <div className="panel-heading">
        <div>
          <h2 id="anomaly-history-title">Comparação histórica</h2>
          <p>Mesmo intervalo do mês em cada ano com dados registrados</p>
        </div>
      </div>
      <div className="anomaly-summary">
        <span><strong>{comparison.percentile_rank == null ? "—" : `${Math.round(comparison.percentile_rank)}º`}</strong> percentil</span>
        <span>Mediana: <strong>{formatNullable(comparison.historical_median)}</strong></span>
        <span>Faixa histórica: <strong>{range}</strong></span>
        {!comparison.anomaly_reliable && comparison.anomaly_absolute != null && (
          <span className="anomaly-warning">Mediana baixa: percentual omitido · diferença {comparison.anomaly_absolute > 0 ? "+" : ""}{formatNumber(comparison.anomaly_absolute)}</span>
        )}
      </div>
      <div className="year-bars" role="group" aria-label="Valores históricos para o período selecionado">
        {values.map((entry) => (
          <div
            className="year-bar-item"
            key={entry.year}
            role="img"
            aria-label={`Ano ${entry.year}: ${entry.value == null ? "sem registros" : `${formatNumber(entry.value)} detecções eq. Aqua`}`}
          >
            <div className="year-bar-track">
              <span style={{ height: `${entry.value ? Math.max(4, (entry.value / max) * 100) : 0}%` }} />
            </div>
            <strong>{entry.value == null ? "—" : formatNumber(entry.value)}</strong>
            <small>{entry.year}</small>
          </div>
        ))}
      </div>
    </section>
  );
}

function SeasonBars({ totals }) {
  const max = Math.max(1, ...totals);
  return (
    <div className="season-chart" aria-label="Total de detecções por mês">
      {totals.map((count, index) => (
        <div className="season-column" key={MONTHS[index]} title={count == null ? MONTHS[index] + " · sem registros" : MONTHS[index] + " · " + formatNumber(count) + " detecções"}>
          <div className="season-track">
            <span style={{ height: `${count ? Math.max(4, (count / max) * 100) : 0}%` }} />
          </div>
          <small>{MONTHS[index]}</small>
        </div>
      ))}
    </div>
  );
}

function calibrationAreaStatus(filters, calibrationBounds) {
  if (!calibrationBounds) return "outside";
  const inside = Number(filters.south) >= calibrationBounds.south
    && Number(filters.north) <= calibrationBounds.north
    && Number(filters.west) >= calibrationBounds.west
    && Number(filters.east) <= calibrationBounds.east;
  if (inside) return "inside";
  const intersects = Number(filters.south) <= calibrationBounds.north
    && Number(filters.north) >= calibrationBounds.south
    && Number(filters.west) <= calibrationBounds.east
    && Number(filters.east) >= calibrationBounds.west;
  return intersects ? "partial" : "outside";
}

const ESTIMATE_LABELS = {
  observed: "Aqua observado",
  calibrated: "VIIRS em escala Aqua",
  fused: "Fusão de detecções Aqua e VIIRS",
  mixed: "Composição de estratos",
  extrapolated: "Fator extrapolado no tempo",
  legacy: "Método histórico",
  uploaded: "CSV externo",
};

function App() {
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [applied, setApplied] = useState(INITIAL_FILTERS);
  const [analytics, setAnalytics] = useState(null);
  const [calibration, setCalibration] = useState(null);
  const [calibrationError, setCalibrationError] = useState("");
  const [points, setPoints] = useState([]);
  const [mapTotal, setMapTotal] = useState(null);
  const [mapRecords, setMapRecords] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploading, setUploading] = useState(false);
  const [ingestion, setIngestion] = useState(null);
  const [ingestionError, setIngestionError] = useState("");
  const [areaRequests, setAreaRequests] = useState([]);
  const [requestingArea, setRequestingArea] = useState(false);
  const [areaRequestMessage, setAreaRequestMessage] = useState("");
  const [downloadYear, setDownloadYear] = useState(String(ANALYSIS_YEAR));
  const [downloadEstimate, setDownloadEstimate] = useState(null);
  const [estimateLoading, setEstimateLoading] = useState(false);
  const [estimateError, setEstimateError] = useState("");
  const [fireView, setFireView] = useState("still");
  const [areaDrawing, setAreaDrawing] = useState(false);
  const [areaDrawingMessage, setAreaDrawingMessage] = useState("");
  const appliedFiltersRef = useRef(applied);
  const areaRequestStatusesRef = useRef({});

  const loadData = useCallback(async (selected) => {
    setLoading(true);
    setError("");
    try {
      const suffix = queryString(selected);
      const [analyticsResponse, pointsResponse] = await Promise.all([
        fetch(`/api/analytics/?${suffix}`),
        fetch(`/api/hotspots/?${suffix}&limit=5000`),
      ]);
      const analyticsBody = await analyticsResponse.json();
      const pointsBody = await pointsResponse.json();
      if (!analyticsResponse.ok) throw new Error(analyticsBody.error || "Falha ao carregar as análises.");
      if (!pointsResponse.ok) throw new Error(pointsBody.error || "Falha ao carregar os pontos no mapa.");
      setAnalytics(analyticsBody);
      setPoints(pointsBody.points);
      setMapTotal(pointsBody.total);
      setMapRecords(pointsBody.records ?? pointsBody.points.length);
    } catch (requestError) {
      setError(requestError.message || "Não foi possível conectar à API.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(applied); }, [applied, loadData]);
  useEffect(() => { appliedFiltersRef.current = applied; }, [applied]);

  useEffect(() => {
    let active = true;
    async function loadCalibration() {
      try {
        const response = await fetch("/api/calibration/");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Falha ao carregar os fatores regionais.");
        if (active) {
          setCalibration(result);
          setCalibrationError("");
        }
      } catch (requestError) {
        if (active) setCalibrationError(requestError.message || "Falha ao carregar a calibração regional.");
      }
    }
    loadCalibration();
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setEstimateLoading(true);
      setEstimateError("");
      try {
        const parameters = new URLSearchParams({
          year: downloadYear,
          south: filters.south,
          north: filters.north,
          west: filters.west,
          east: filters.east,
        });
        const response = await fetch(`/api/area-requests/estimate/?${parameters}`, {
          signal: controller.signal,
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Não foi possível estimar a coleta.");
        if (active) setDownloadEstimate(result);
      } catch (estimateRequestError) {
        if (active && estimateRequestError.name !== "AbortError") {
          setDownloadEstimate(null);
          setEstimateError(estimateRequestError.message || "Falha ao estimar o download.");
        }
      } finally {
        if (active) setEstimateLoading(false);
      }
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [downloadYear, filters.east, filters.north, filters.south, filters.west]);

  useEffect(() => {
    let active = true;
    async function refreshIngestion() {
      try {
        const response = await fetch("/api/ingestion-status/");
        const areaResponse = await fetch("/api/area-requests/");
        const result = await response.json();
        const areaResult = await areaResponse.json();
        if (!response.ok) throw new Error(result.error || "Falha ao consultar o sincronizador.");
        if (!areaResponse.ok) throw new Error(areaResult.error || "Falha ao consultar as solicitações de área.");
        if (active) {
          const previousStatuses = areaRequestStatusesRef.current;
          const completedRequest = areaResult.requests.find(
            (item) => ["ready", "partial"].includes(item.status)
              && previousStatuses[item.id] && previousStatuses[item.id] !== item.status,
          );
          areaRequestStatusesRef.current = Object.fromEntries(
            areaResult.requests.map((item) => [item.id, item.status]),
          );
          setIngestion(result);
          setAreaRequests(areaResult.requests);
          setIngestionError("");
          if (completedRequest) {
            setAreaRequestMessage(
              completedRequest.status === "partial"
                ? "Período FIRMS publicado parcial. " + completedRequest.last_error
                : "Solicitação #" + completedRequest.id + " concluída. Registros da área carregados.",
            );
            const selected = appliedFiltersRef.current;
            if (
              completedRequest.start === selected.start &&
              completedRequest.end === selected.end &&
              Number(completedRequest.south) === Number(selected.south) &&
              Number(completedRequest.north) === Number(selected.north) &&
              Number(completedRequest.west) === Number(selected.west) &&
              Number(completedRequest.east) === Number(selected.east)
            ) {
              loadData(selected);
            }
          }
        }
      } catch (statusError) {
        if (active) setIngestionError(statusError.message || "Falha ao consultar o sincronizador.");
      }
    }
    refreshIngestion();
    const timer = window.setInterval(refreshIngestion, 30000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const bounds = useMemo(
    () => [[Number(applied.south), Number(applied.west)], [Number(applied.north), Number(applied.east)]],
    [applied],
  );
  const comparison = analytics?.comparison;
  const selectedFireView = FIRE_VIEWS[fireView];
  const singleMonthSelection = applied.start.slice(0, 7) === applied.end.slice(0, 7);
  const calibrationMonth = singleMonthSelection ? Number(applied.start.slice(5, 7)) : null;
  const countCalibration = calibrationMonth
    ? calibration?.factors.find(
      (item) => item.month === calibrationMonth && item.metric === "count",
    )
    : calibration?.annual?.count;
  const frpCalibration = calibrationMonth
    ? calibration?.factors.find(
      (item) => item.month === calibrationMonth && item.metric === "frp",
    )
    : calibration?.annual?.frp;
  const fusionComparison = calibrationMonth
    ? calibration?.fusion.find((item) => item.month === calibrationMonth)
    : null;
  const calibrationRelation = calibrationAreaStatus(applied, calibration?.bounds);
  const estimateKinds = Object.keys(analytics?.estimate_kinds || {});
  const calibrationBadge = estimateKinds.length > 1
    ? "Métodos mistos"
    : ESTIMATE_LABELS[estimateKinds[0]];
  const maximumIncrease = fusionComparison?.average > 0 && fusionComparison?.maximum != null
    ? (fusionComparison.maximum / fusionComparison.average - 1) * 100
    : null;

  function updateFilter(event) {
    setFilters((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  function applyPeriodShortcut(shortcut) {
    const today = new Date();
    const todayText = today.toISOString().slice(0, 10);
    let start;
    let end = todayText;
    if (shortcut === "current-month") {
      start = `${todayText.slice(0, 7)}-01`;
    } else if (shortcut === "last-12-months") {
      const targetMonth = today.getUTCMonth();
      const targetYear = today.getUTCFullYear() - 1;
      const targetDay = Math.min(
        today.getUTCDate(),
        new Date(Date.UTC(targetYear, targetMonth + 1, 0)).getUTCDate(),
      );
      start = new Date(Date.UTC(targetYear, targetMonth, targetDay)).toISOString().slice(0, 10);
    } else {
      start = `${ANALYSIS_YEAR}-01-01`;
      end = `${ANALYSIS_YEAR}-12-31`;
    }
    const selected = { ...filters, start, end };
    setFilters(selected);
    setApplied(selected);
  }

  const cancelAreaDrawing = useCallback(() => {
    setAreaDrawing(false);
    setAreaDrawingMessage("Desenho cancelado.");
  }, []);

  const completeAreaDrawing = useCallback((firstCorner, secondCorner) => {
    const south = Math.min(firstCorner.lat, secondCorner.lat);
    const north = Math.max(firstCorner.lat, secondCorner.lat);
    const west = Math.min(firstCorner.lng, secondCorner.lng);
    const east = Math.max(firstCorner.lng, secondCorner.lng);
    if (north - south > 20 || east - west > 20 || north === south || east === west) {
      setAreaDrawingMessage("A área precisa ter lados maiores que zero e no máximo 20°.");
      return;
    }
    const southText = south.toFixed(4);
    const northText = north.toFixed(4);
    const westText = west.toFixed(4);
    const eastText = east.toFixed(4);
    if (Number(southText) >= Number(northText) || Number(westText) >= Number(eastText)) {
      setAreaDrawingMessage("A área é pequena demais para ser representada com quatro casas decimais.");
      return;
    }
    const selected = {
      ...applied,
      south: southText,
      north: northText,
      west: westText,
      east: eastText,
    };
    setFilters(selected);
    setApplied(selected);
    setAreaDrawing(false);
    setAreaDrawingMessage("Área desenhada e aplicada aos filtros.");
  }, [applied]);

  async function importCsv(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadMessage("");
    setError("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const response = await fetch("/api/upload/", { method: "POST", body: formData });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Falha ao importar o arquivo.");
      setUploadMessage(
        `${result.inserted.toLocaleString("pt-BR")} novos pontos importados` +
        (result.duplicates ? ` · ${result.duplicates.toLocaleString("pt-BR")} duplicados ignorados` : ""),
      );
      await loadData(applied);
    } catch (uploadError) {
      setError(uploadError.message || "Não foi possível importar o CSV.");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  function downloadCsv() {
    window.location.assign(`/api/hotspots.csv?${queryString(applied)}`);
  }

  function downloadCalendarCsv() {
    window.location.assign(`/api/calendar.csv?${queryString(applied)}`);
  }

  async function requestAreaData(downloadSources) {
    setRequestingArea(true);
    setAreaRequestMessage("");
    try {
      const response = await fetch("/api/area-requests/create/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          year: Number(downloadYear),
          south: filters.south,
          north: filters.north,
          west: filters.west,
          east: filters.east,
          download_sources: downloadSources,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Não foi possível solicitar os dados.");
      setAreaRequestMessage(downloadSources
        ? `Solicitação #${result.id} na fila · estimativa ${estimateDuration(result.estimate)}.`
        : `Solicitação #${result.id} na fila para processar os dados já armazenados, sem consultar a NASA FIRMS.`,
      );
      areaRequestStatusesRef.current = {
        ...areaRequestStatusesRef.current,
        [result.id]: result.status,
      };
      const selectedYear = {
        ...filters,
        start: result.start,
        end: result.end,
      };
      setFilters(selectedYear);
      setApplied(selectedYear);
      const requestsResponse = await fetch("/api/area-requests/");
      const requestsResult = await requestsResponse.json();
      if (!requestsResponse.ok) throw new Error(requestsResult.error || "Falha ao atualizar a fila.");
      setAreaRequests(requestsResult.requests);
    } catch (requestError) {
      setAreaRequestMessage(requestError.message || "Falha ao solicitar dados FIRMS.");
    } finally {
      setRequestingArea(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="PyroHarmonix início">
          <span className="brand-mark"><Flame size={21} /></span>
          <span>pyro<span className="brand-light">harmonix</span><small>MONITORAMENTO DE FOGO</small></span>
        </a>
        <div className="side-section-label">ESPAÇO DE TRABALHO</div>
        <button className="nav-item nav-active"><Layers3 size={17} /> Regimes de fogo</button>
        <a className="nav-item" href="#fire-imagery"><ImageIcon size={17} /> Imagens da queimada</a>
        <div className="sidebar-bottom">
          <div className="data-status"><span className="status-dot" /><span>Base harmonizada<br /><small>MODIS-Aqua + VIIRS-SNPP (onde calibrado)</small></span></div>
          <a href="/api/template.csv" className="help-link"><CircleHelp size={16} /> Formato dos dados</a>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumb">Monitoramento <span>/</span> <strong>Regimes de fogo</strong></div>
          <div className="topbar-meta" title={ingestion?.last_error || ingestionError}>
            <span className={`live-dot${ingestion?.status === "error" ? " status-error" : ""}`} />
            {ingestionLabel(ingestion?.status)}
            {ingestion?.active_source && <><span className="top-divider" /> {ingestion.active_source}</>}
          </div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div>
              <div className="eyebrow"><span /> OBSERVAÇÃO DA TERRA · COBERTURA GLOBAL</div>
              <h1>Regimes de fogo</h1>
              <p>Explore padrões de atividade e compare detecções harmonizadas ao longo do tempo.</p>
            </div>
            <a className="template-link" href="/api/template.csv"><Download size={15} /> Baixar modelo CSV</a>
          </section>

          <section className="filter-panel">
            <div className="filter-heading"><div><MapPin size={16} /><strong>Área e período de análise</strong></div><span>Qualquer região · retângulo até 20° × 20°</span></div>
            <form onSubmit={(event) => { event.preventDefault(); setApplied({ ...filters }); }} className="filters-form">
              <label className="filter-field date-field"><span>DATA INICIAL</span><input name="start" type="date" value={filters.start} onChange={updateFilter} required /></label>
              <label className="filter-field date-field"><span>DATA FINAL</span><input name="end" type="date" value={filters.end} onChange={updateFilter} required /></label>
              <div className="filter-separator" />
              {[
                ["south", "LAT. SUL"], ["north", "LAT. NORTE"], ["west", "LON. OESTE"], ["east", "LON. LESTE"],
              ].map(([name, label]) => (
                <label className="filter-field coordinate-field" key={name}>
                  <span>{label}</span><input name={name} type="number" step="any" value={filters[name]} onChange={updateFilter} required />
                </label>
              ))}
              <button className="apply-button" type="submit"><Activity size={15} /> Aplicar</button>
            </form>
            <div className="period-shortcuts" role="group" aria-label="Atalhos de período">
              <span>Atalhos:</span>
              <button type="button" onClick={() => applyPeriodShortcut("current-month")}>Mês atual</button>
              <button type="button" onClick={() => applyPeriodShortcut("last-12-months")}>Últimos 12 meses</button>
              <button type="button" onClick={() => applyPeriodShortcut("analysis-year")}>Ano 2024</button>
            </div>
            <div className="download-request">
              <label className="filter-field year-field">
                <span>ANO DOS DADOS</span>
                <select value={downloadYear} onChange={(event) => setDownloadYear(event.target.value)}>
                  {DOWNLOAD_YEARS.map((year) => <option value={year} key={year}>{year}</option>)}
                </select>
              </label>
              <div className="request-estimate" aria-live="polite">
                <span>Estimativa de coleta</span>
                <strong>
                  {estimateLoading
                    ? "Calculando…"
                    : estimateError
                      ? "Indisponível"
                      : `~${estimateDuration(downloadEstimate)}`}
                </strong>
                <small>
                  {estimateError ||
                    (downloadEstimate
                      ? `${downloadEstimate.api_requests} chamadas FIRMS · ${downloadEstimate.sources.map(sensorLabel).join(" + ")}`
                      : "A estimativa varia com o volume e a conexão.")}
                </small>
              </div>
              <div className="request-actions">
                <button
                  className="request-button stored-data-button"
                  type="button"
                  onClick={() => requestAreaData(false)}
                  disabled={requestingArea}
                  title="Reprocessa somente detecções FIRMS já armazenadas para esta área e ano."
                >
                  <Activity size={14} /> {requestingArea ? "Solicitando…" : "Processar dados existentes"}
                </button>
                <button
                  className="request-button"
                  type="button"
                  onClick={() => requestAreaData(true)}
                  disabled={requestingArea || estimateLoading || !downloadEstimate || Boolean(estimateError)}
                >
                  <Download size={14} /> {requestingArea ? "Solicitando…" : `Baixar + analisar ${downloadYear}`}
                </button>
              </div>
            </div>
            <p className="request-footnote">
              “Processar dados existentes” não faz chamadas FIRMS e usa somente registros já armazenados. Para áreas sem dados, escolha “Baixar + analisar”. A série harmonizada começa em jul/2002 (MODIS-Aqua); Terra é armazenado, mas não usado na série.
            </p>
          </section>

          {error && <div role="alert" className="notice notice-error">{error}</div>}
          {ingestionError && <div role="alert" className="notice notice-error">{ingestionError}</div>}
          {uploadMessage && <div role="status" className="notice notice-success">{uploadMessage}</div>}
          {areaRequestMessage && <div role="status" className="notice notice-info">{areaRequestMessage}</div>}
          {areaRequests.length > 0 && (
            <div className="area-request-list" aria-live="polite">
              <strong>Solicitações de outras áreas</strong>
              {areaRequests.slice(0, 3).map((item) => (
                <span key={item.id} title={item.last_error || undefined}>
                  #{item.id} · {item.start}–{item.end} · {item.west}, {item.south} → {item.east}, {item.north} · {areaRequestLabel(item.status)}
                  {item.mode === "stored" ? " · dados existentes" : " · coleta FIRMS"}
                  {["downloading", "harmonizing"].includes(item.status) && ` · desde ${item.next_date}`}
                  {["queued", "downloading"].includes(item.status) && item.estimate && ` · estimativa ${estimateDuration(item.estimate)}`}
                  {["error", "partial"].includes(item.status) && item.last_error && ` · ${item.last_error}`}
                </span>
              ))}
            </div>
          )}
          {ingestion?.status === "waiting_for_key" && (
            <div role="status" className="notice notice-info">
              Novos downloads aguardam a chave gratuita NASA FIRMS. Dados já armazenados ainda podem ser processados. Para baixar, configure <code>FIRMS_MAP_KEY</code> no arquivo <code>.env</code> e reinicie o Compose.
            </div>
          )}
          {ingestion?.last_error && ingestion.status === "error" && (
            <div role="alert" className="notice notice-error">{ingestion.last_error}</div>
          )}
          {ingestion?.status === "backfilling" && ingestion.sources?.length > 0 && (
            <div role="status" className="notice notice-info">
              Carga histórica em andamento; o progresso é salvo por produto e retomado após reinícios.
              {" "}{ingestion.sources.map((source) => `${source.source}: desde ${source.next_date}`).join(" · ")}
            </div>
          )}
          {ingestion?.status === "on_demand" && (
            <div role="status" className="notice notice-info">
              Coleta nacional automática pausada para controlar o armazenamento. Os dados já baixados foram preservados; solicite outros anos e regiões acima.
            </div>
          )}

          {analytics && applied.start < analytics.harmonized_start && (
            <div className="notice notice-info" role="status">
              A série harmonizada começa em jul/2002 (MODIS-Aqua).
            </div>
          )}

          <section className="stats-grid">
            <StatCard
              icon={Flame}
              label="Detecções eq. Aqua"
              value={loading ? "…" : formatNullable(analytics?.total)}
              note={`${analytics?.start || applied.start} — ${analytics?.end || applied.end}`}
              badge={calibrationBadge}
              accent
            />
            <StatCard icon={Activity} label="Mediana histórica" value={loading ? "…" : comparison?.historical_median == null ? "—" : formatNumber(comparison.historical_median)} note={comparison?.historical_median == null ? `Histórico insuficiente · ${comparison?.historical_years || 0} anos com registros` : `Mesmo mês · ${comparison.historical_years} anos com registros`} />
            <StatCard
              icon={Layers3}
              label={comparison?.anomaly_reliable ? "Anomalia vs. mediana" : "Diferença absoluta"}
              value={loading
                ? "…"
                : comparison?.anomaly_reliable
                  ? comparison.anomaly_percent == null
                    ? "—"
                    : `${comparison.anomaly_percent > 0 ? "+" : ""}${comparison.anomaly_percent}%`
                  : comparison?.anomaly_absolute == null
                    ? "—"
                    : `${comparison.anomaly_absolute > 0 ? "+" : ""}${formatNumber(comparison.anomaly_absolute)}`}
              note={comparison?.anomaly_reliable
                ? "Mês selecionado vs. histórico disponível"
                : comparison?.historical_median == null
                  ? "Histórico insuficiente para comparar"
                  : "Mediana baixa: percentual omitido"}
            />
          </section>
          <AnomalyHistory comparison={comparison} />

          <section className={`panel calibration-panel${calibrationRelation === "outside" ? " calibration-muted" : ""}`} aria-labelledby="calibration-title">
            <div className="panel-heading">
              <div>
                <h2 id="calibration-title">Calibração regional · {calibrationMonth ? MONTHS[calibrationMonth - 1] : "Fator anual"}</h2>
                <p>{calibration?.scope_label || "Altinópolis–Pitangueiras · Cerrado/interior de SP"} · H3 res. {calibration?.h3_resolution || 7}</p>
              </div>
              <span className={`scope-badge scope-${calibrationRelation}`}>
                {calibrationRelation === "inside"
                  ? "Dentro da área"
                  : calibrationRelation === "partial"
                    ? "Parcialmente sobre a área"
                    : "Fora da área"}
              </span>
            </div>
            {calibrationError ? (
              <div className="notice notice-error" role="alert">{calibrationError}</div>
            ) : !calibration ? (
              <div className="empty-inline">Carregando os fatores regionais…</div>
            ) : (
              <>
                <div className="calibration-metrics">
                  <article>
                    <span>Contagem · Aqua / SNPP · {calibrationMonth ? "fator mensal" : "fator anual"}</span>
                    <strong>{countCalibration?.calibrated || (!calibrationMonth && countCalibration?.factor != null) ? formatFactor(countCalibration.factor) : "Não calibrado"}</strong>
                    <small>{countCalibration?.sample_size || 0} estratos · {formatInterval(countCalibration)}</small>
                  </article>
                  <article>
                    <span>FRP · Aqua / SNPP · {calibrationMonth ? "fator mensal" : "fator anual"}</span>
                    <strong>{frpCalibration?.calibrated || (!calibrationMonth && frpCalibration?.factor != null) ? formatFactor(frpCalibration.factor) : "Não calibrado"}</strong>
                    <small>{frpCalibration?.sample_size || 0} estratos · {formatInterval(frpCalibration)}</small>
                  </article>
                </div>
                <div className="fusion-comparison">
                  <strong>{calibrationMonth ? "Fusões do mês agrupadas entre anos" : "Fusões disponíveis somente por mês"}</strong>
                  <span>Preenchimento por zero (diagnóstico histórico): {formatNullable(fusionComparison?.zero_filled_mean)}</span>
                  <span>Média das detecções presentes: {formatNullable(fusionComparison?.average)}</span>
                  <span>
                    Máximo: {formatNullable(fusionComparison?.maximum)}
                    {maximumIncrease == null ? "" : ` · +${formatNumber(maximumIncrease)}% vs média`}
                  </span>
                  <span>União: {formatNullable(fusionComparison?.union_parent_days)} células H3</span>
                </div>
                <p className="calibration-note">
                  {calibration.series_method && <span>Versão {calibration.series_method}. </span>}
                  {calibration.calibration_method === "monthly_shrunk_union" && (
                    <span>Calibração por razão mensal de totais, regularizada pela razão anual (k = {calibration.shrinkage_prior_pairs}). </span>
                  )}
                  <span>Detecções equivalentes Aqua são um índice de atividade registrada. A composição dos sensores pode alterar a magnitude do índice. </span>
                  {calibrationRelation === "outside"
                    ? "Sem calibração para esta área: série em base Aqua (somente MODIS-Aqua)."
                    : "O fator ajusta a escala das detecções VIIRS à do Aqua. A série atual usa a média quando ambos detectaram no mesmo estrato. Quando há detecção de um único sensor, usa esse valor na escala Aqua. Os registros FIRMS de focos ativos deixam a cobertura desconhecida."}
                  {calibrationMonth == null && " A série usa fatores de cada mês. O fator anual serve de referência."}
                  {calibration && ` Fonte: ${calibration.source === "recalculated" ? "Recalculado a partir dos dados armazenados" : "Snapshot versionado"}.`}
                  {" Cobertura por célula e turno desconhecida nos registros FIRMS."}
                  {calibration && " Escopo avaliado " + calibration.assessment_start_year + "–" + calibration.assessment_end_year + ". Aplicações fora desses anos são extrapoladas."}
                  {calibration?.overlap_start && calibration?.overlap_end && ` Dados do ajuste ${calibration.overlap_start}–${calibration.overlap_end}.`}
                </p>
              </>
            )}
          </section>

          <div className="dashboard-grid">
            <section className="panel map-panel">
              <div className="panel-heading">
                <div><h2>Células de atividade</h2><p>{formatNullable(mapTotal)} detecções eq. Aqua · {points.length < mapRecords ? `exibindo ${points.length.toLocaleString("pt-BR")} células` : "todas exibidas"}</p></div>
                <div className="map-actions">
                  <button
                    className={`request-button map-draw-button${areaDrawing ? " map-draw-active" : ""}`}
                    type="button"
                    aria-pressed={areaDrawing}
                    onClick={() => {
                      setAreaDrawing((active) => !active);
                      setAreaDrawingMessage(areaDrawing ? "Desenho cancelado." : "Clique em dois cantos opostos do mapa; Esc cancela.");
                    }}
                  >
                    <MapPin size={14} /> {areaDrawing ? "Cancelar desenho" : "Desenhar área"}
                  </button>
                  <button className="icon-button" onClick={downloadCsv} title="Baixar CSV filtrado" aria-label="Baixar CSV de hotspots"><Download size={16} /></button>
                </div>
              </div>
              <div className="map-wrap">
                <MapContainer center={[-14, -53]} zoom={4} scrollWheelZoom preferCanvas className={`leaflet-map${areaDrawing ? " draw-mode" : ""}`}>
                  <FitMap bounds={bounds} />
                  <TileLayer
                    attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
                    url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                  />
                  {points.map((point) => (
                    <CircleMarker
                      key={point.id}
                      center={[point.latitude, point.longitude]}
                      radius={5}
                      pathOptions={{ color: "#ffc857", weight: 1, fillColor: "#ff7048", fillOpacity: 0.78 }}
                    >
                      <Tooltip direction="top" offset={[0, -4]}>
                        {formatNumber(point.harmonized_count)} detecções eq. Aqua
                        {point.harmonized_frp != null && ` · FRP ${formatNumber(point.harmonized_frp)} MW`}
                        {" · "}{point.acquired_at.slice(0, 10)}
                      </Tooltip>
                    </CircleMarker>
                  ))}
                  <MapAreaDrawer
                    active={areaDrawing}
                    onComplete={completeAreaDrawing}
                    onCancel={cancelAreaDrawing}
                  />
                </MapContainer>
                {!loading && mapRecords === 0 && <div className="map-empty"><MapPin size={20} /><span>Sem registros nesta área e período.<br />Cobertura de observação desconhecida.</span></div>}
              </div>
              {areaDrawingMessage && <p className="map-draw-status" role="status">{areaDrawingMessage}</p>}
              <div className="map-legend"><span><i className="legend-dot" /> Célula harmonizada · H3 res. {analytics?.h3_resolution ?? calibration?.h3_resolution ?? "—"}</span><span>MODIS-Aqua + VIIRS-SNPP (onde calibrado)</span></div>
            </section>

            <section className="panel season-panel">
              <div className="panel-heading">
                <div><h2>Sazonalidade</h2><p>Detecções registradas; ausência de dados não confirma ausência de fogo</p></div>
                <button className="icon-button subtle" title="Soma mensal para a área e período selecionados" aria-label="Como são calculados os totais mensais"><CircleHelp size={15} /></button>
              </div>
              {analytics ? <SeasonBars totals={analytics.monthly_totals} /> : <div className="empty-inline">Carregando…</div>}
              <div className="season-summary"><span><i className="legend-dot" /> Contagem de hotspots</span><span>Jan — Dez</span></div>
            </section>
          </div>

          <section className="panel calendar-panel">
            <div className="panel-heading calendar-heading">
              <div><h2>Calendário de atividade de queima</h2><p>Distribuição mensal por ano · comparação de intensidade relativa</p></div>
              <div className="calendar-actions">
                <button className="request-button calendar-download-button" type="button" onClick={downloadCalendarCsv}>
                  <Download size={14} /> Baixar calendário CSV
                </button>
                <div className="calendar-period"><CalendarDays size={14} /> {applied.start.slice(0, 4)} — {applied.end.slice(0, 4)}</div>
              </div>
            </div>
            <Heatmap years={analytics?.years || []} />
          </section>

          <section className="panel fire-imagery-panel" id="fire-imagery" aria-labelledby="fire-imagery-title">
            <div className="panel-heading fire-imagery-heading">
              <div><h2 id="fire-imagery-title">Visualização da queimada</h2><p>Imagens VIIRS/Suomi-NPP · região de Ribeirão Preto · agosto de 2024</p></div>
              <div className="fire-imagery-tabs" role="group" aria-label="Selecionar imagem da queimada">
                {Object.entries(FIRE_VIEWS).map(([key, view]) => (
                  <button
                    className={`fire-imagery-tab${fireView === key ? " fire-imagery-tab-active" : ""}`}
                    type="button"
                    aria-pressed={fireView === key}
                    key={key}
                    onClick={() => setFireView(key)}
                  >
                    {view.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="fire-imagery-content">
              <a className="fire-imagery-frame" href={selectedFireView.src} target="_blank" rel="noreferrer" aria-label="Abrir imagem em tamanho original em uma nova aba">
                <img src={selectedFireView.src} alt={selectedFireView.alt} loading="lazy" decoding="async" />
              </a>
              <div className="fire-imagery-copy">
                <h3>{selectedFireView.title}</h3>
                <p>{selectedFireView.description}</p>
                <p>Anomalias térmicas não são perímetros de área queimada. Nuvens podem ocultar detecções.</p>
                <p className="fire-imagery-attribution">NASA Worldview/GIBS (ESDIS). <a href="https://worldview.earthdata.nasa.gov/" target="_blank" rel="noreferrer">Abrir NASA Worldview</a>.</p>
              </div>
            </div>
            <p className="fire-imagery-note">Esta visualização histórica é contextual e independente dos filtros. Não é uma camada georreferenciada sobre o mapa, nem representa a área queimada calculada pelo WebGIS.</p>
          </section>

          <section className="upload-panel">
            <div className="upload-icon"><Upload size={19} /></div>
            <div className="upload-copy"><strong>Atualize sua base harmonizada</strong><span>Importe um CSV com hotspots MODIS-Aqua + VIIRS-SNPP processados e prontos para análise.</span></div>
            <label className={`upload-button${uploading ? " button-disabled" : ""}`}>
              {uploading ? "Importando…" : <><Upload size={15} /> Importar CSV</>}
              <input type="file" accept=".csv,text/csv" onChange={importCsv} disabled={uploading} />
            </label>
            <a className="template-small" href="/api/template.csv">Ver formato <ChevronDown size={13} /></a>
          </section>

          <footer className="page-footer">
            <span>PyroHarmonix · Calendário harmonizado de atividade de fogo</span>
            <span>Standard Processing · <a href="https://firms.modaps.eosdis.nasa.gov/" target="_blank" rel="noreferrer">NASA FIRMS</a></span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export default App;
