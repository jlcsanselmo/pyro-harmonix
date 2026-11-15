import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CircleMarker, MapContainer, TileLayer, Tooltip, useMap } from "react-leaflet";
import {
  Activity,
  CalendarDays,
  ChevronDown,
  CircleHelp,
  Download,
  Flame,
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
const INITIAL_FILTERS = {
  start: `${ANALYSIS_YEAR}-01-01`,
  end: `${ANALYSIS_YEAR}-12-31`,
  south: "-23",
  north: "-20",
  west: "-50",
  east: "-46",
};

function areaRequestLabel(status) {
  return {
    queued: "na fila",
    downloading: "baixando",
    harmonizing: "processando dados",
    ready: "concluído",
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

function StatCard({ icon: Icon, label, value, note, accent = false }) {
  return (
    <article className={`stat-card${accent ? " stat-card-accent" : ""}`}>
      <div className="stat-label"><span>{label}</span><Icon size={16} aria-hidden="true" /></div>
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
              const strength = count ? Math.max(1, Math.ceil((count / max) * 5)) : 0;
              const label = count == null
                ? `${MONTHS[index]} ${year.year}: sem registros`
                : `${MONTHS[index]} ${year.year}: ${formatNumber(count)} detecções equivalentes`;
              return (
                <span
                  className={`heat-cell${count == null ? " heat-no-data" : strength ? ` heat-${strength}` : ""}`}
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
        <span>Menos</span>
        {[1, 2, 3, 4, 5].map((level) => <i className={`heat-cell heat-${level}`} key={level} />)}
        <span>Mais detecções</span>
      </div>
    </div>
  );
}

function SeasonBars({ totals }) {
  const max = Math.max(1, ...totals);
  return (
    <div className="season-chart" aria-label="Total de detecções por mês">
      {totals.map((count, index) => (
        <div className="season-column" key={MONTHS[index]} title={`${MONTHS[index]}: ${count} detecções`}>
          <div className="season-track">
            <span style={{ height: `${count ? Math.max(4, (count / max) * 100) : 0}%` }} />
          </div>
          <small>{MONTHS[index]}</small>
        </div>
      ))}
    </div>
  );
}

function App() {
  const [filters, setFilters] = useState(INITIAL_FILTERS);
  const [applied, setApplied] = useState(INITIAL_FILTERS);
  const [analytics, setAnalytics] = useState(null);
  const [points, setPoints] = useState([]);
  const [mapTotal, setMapTotal] = useState(0);
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
            (item) => item.status === "ready" && previousStatuses[item.id] && previousStatuses[item.id] !== "ready",
          );
          areaRequestStatusesRef.current = Object.fromEntries(
            areaResult.requests.map((item) => [item.id, item.status]),
          );
          setIngestion(result);
          setAreaRequests(areaResult.requests);
          setIngestionError("");
          if (completedRequest) {
            setAreaRequestMessage(`Solicitação #${completedRequest.id} concluída; os dados da área foram carregados.`);
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

  function updateFilter(event) {
    setFilters((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

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
        <div className="sidebar-bottom">
          <div className="data-status"><span className="status-dot" /><span>Base harmonizada<br /><small>MODIS + VIIRS</small></span></div>
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
              “Processar dados existentes” não faz chamadas FIRMS e usa somente registros já armazenados. Para áreas sem dados, escolha “Baixar + analisar”. MODIS desde nov. 2000; VIIRS-Suomi NPP desde jan. 2012.
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
                  {item.status !== "ready" && item.estimate && ` · estimativa ${estimateDuration(item.estimate)}`}
                  {item.status === "error" && item.last_error && ` · ${item.last_error}`}
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

          <section className="stats-grid">
            <StatCard icon={Flame} label="Detecções harmonizadas (eq.)" value={loading ? "…" : formatNumber(analytics?.total)} note={`${analytics?.start || applied.start} — ${analytics?.end || applied.end}`} accent />
            <StatCard icon={Activity} label="Mediana histórica" value={loading ? "…" : comparison?.historical_median == null ? "—" : formatNumber(comparison.historical_median)} note={comparison?.historical_median == null ? `Histórico insuficiente · ${comparison?.historical_years || 0} anos com registros` : `Mesmo mês · ${comparison.historical_years} anos com registros`} />
            <StatCard icon={Layers3} label="Anomalia vs. mediana" value={loading ? "…" : comparison?.anomaly_percent == null ? "—" : `${comparison.anomaly_percent > 0 ? "+" : ""}${comparison.anomaly_percent}%`} note={comparison?.anomaly_percent == null ? "Requer mediana de ao menos 2 anos" : "Mês selecionado vs. histórico disponível"} />
          </section>

          <div className="dashboard-grid">
            <section className="panel map-panel">
              <div className="panel-heading">
                <div><h2>Células de atividade</h2><p>{formatNumber(mapTotal)} detecções equivalentes · {points.length < mapTotal ? `exibindo ${points.length.toLocaleString("pt-BR")} células` : "todas exibidas"}</p></div>
                <button className="icon-button" onClick={downloadCsv} title="Baixar CSV filtrado"><Download size={16} /></button>
              </div>
              <div className="map-wrap">
                <MapContainer center={[-14, -53]} zoom={4} scrollWheelZoom className="leaflet-map">
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
                        {formatNumber(point.harmonized_count)} detecções equivalentes · {point.acquired_at.slice(0, 10)}
                      </Tooltip>
                    </CircleMarker>
                  ))}
                </MapContainer>
                {!loading && mapTotal === 0 && <div className="map-empty"><MapPin size={20} /><span>Sem detecções para esta área e período.<br />A coleta FIRMS pode ainda estar em andamento.</span></div>}
              </div>
              <div className="map-legend"><span><i className="legend-dot" /> Célula ativa · H3 res. 8</span><span>MODIS + VIIRS-SNPP</span></div>
            </section>

            <section className="panel season-panel">
              <div className="panel-heading">
                <div><h2>Sazonalidade</h2><p>Detecções registradas; ausência de dados não confirma ausência de fogo</p></div>
                <button className="icon-button subtle" title="Soma mensal para a área e período selecionados"><CircleHelp size={15} /></button>
              </div>
              {analytics ? <SeasonBars totals={analytics.monthly_totals} /> : <div className="empty-inline">Carregando…</div>}
              <div className="season-summary"><span><i className="legend-dot" /> Contagem de hotspots</span><span>Jan — Dez</span></div>
            </section>
          </div>

          <section className="panel calendar-panel">
            <div className="panel-heading calendar-heading">
              <div><h2>Calendário de atividade de queima</h2><p>Distribuição mensal por ano · comparação de intensidade relativa</p></div>
              <div className="calendar-period"><CalendarDays size={14} /> {applied.start.slice(0, 4)} — {applied.end.slice(0, 4)}</div>
            </div>
            <Heatmap years={analytics?.years || []} />
          </section>

          <section className="upload-panel">
            <div className="upload-icon"><Upload size={19} /></div>
            <div className="upload-copy"><strong>Atualize sua base harmonizada</strong><span>Importe um CSV com hotspots MODIS + VIIRS processados e prontos para análise.</span></div>
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
