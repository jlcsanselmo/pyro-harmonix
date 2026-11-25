# Índice de artefatos científicos

A metodologia vigente de produção é `detection_conditioned_v1` com `monthly_shrunk_union`. O resultado orbital vigente como evidência experimental está na etapa 5. Diagnósticos circulares, snapshots anteriores e comparações em domínio legado permanecem como controles históricos. Ausência de suporte a 55° em 24/08/2024, baixa disponibilidade de positivos e calibração orbital inconclusiva são resultados preservados.

| Etapa | Estado de interpretação | Relatórios e figuras vinculados |
| --- | --- | --- |
| 1 e histórico | Vigente para auditoria e validação; exports com zeros e CSV Ribeirão Preto arquivados | [TECHNICAL_AUDIT.md](TECHNICAL_AUDIT.md) · [SCIENTIFIC_METHODOLOGY.md](SCIENTIFIC_METHODOLOGY.md) · [VALIDATION_REPORT.md](VALIDATION_REPORT.md) · [w9-validation-report.md](w9-validation-report.md) · [calibration-summary.md](data/calibration-summary.md) · [scientific-audit.png](assets/scientific-audit.png) |
| 2 | Decomposição e comparação de modelos vigentes como evidência; validação externa como protocolo | [FUSION_BIAS_ANALYSIS.md](FUSION_BIAS_ANALYSIS.md) · [MODEL_COMPARISON_REPORT.md](MODEL_COMPARISON_REPORT.md) · [OBSERVATION_COVERAGE_STUDY.md](OBSERVATION_COVERAGE_STUDY.md) · [EXTERNAL_VALIDATION_PROTOCOL.md](EXTERNAL_VALIDATION_PROTOCOL.md) · [fusion-study.png](assets/fusion-study.png) |
| 3 | Piloto exploratório original, resultado principal sem suporte; cenários de 60° e 65° preservados | [REAL_OBSERVATION_COVERAGE_REPORT.md](REAL_OBSERVATION_COVERAGE_REPORT.md) · [COVERAGE_AWARE_FUSION_REPORT.md](COVERAGE_AWARE_FUSION_REPORT.md) · [noaa-positive-overlap.png](assets/noaa-positive-overlap.png) |
| 4 | Revisão experimental de geometria e QA, mais comparações legadas para reprodução | [FOOTPRINT_GEOMETRY_AUDIT.md](FOOTPRINT_GEOMETRY_AUDIT.md) · [VIIRS_QA_SENSITIVITY_REPORT.md](VIIRS_QA_SENSITIVITY_REPORT.md) · [SECOND_ORBITAL_PILOT_REPORT.md](SECOND_ORBITAL_PILOT_REPORT.md) · [ORBITAL_CALIBRATION_COMPATIBILITY.md](ORBITAL_CALIBRATION_COMPATIBILITY.md) |
| 5 | Protocolo congelado e comparação experimental em suporte fixo; calibração orbital inconclusiva | [ORBITAL_EXPERIMENT_PROTOCOL.md](ORBITAL_EXPERIMENT_PROTOCOL.md) · [FOOTPRINT_INDEPENDENT_VALIDATION.md](FOOTPRINT_INDEPENDENT_VALIDATION.md) · [STRATIFIED_ORBITAL_SAMPLE_REPORT.md](STRATIFIED_ORBITAL_SAMPLE_REPORT.md) · [QA_FIXED_SUPPORT_COMPARISON.md](QA_FIXED_SUPPORT_COMPARISON.md) · [ORBITAL_CALIBRATION_FEASIBILITY.md](ORBITAL_CALIBRATION_FEASIBILITY.md) · [FUSION_ROBUSTNESS_REPORT.md](FUSION_ROBUSTNESS_REPORT.md) |
| 1.0 | Consolidação vigente e manuscrito em revisão | [FINAL_SCIENTIFIC_REPORT.md](FINAL_SCIENTIFIC_REPORT.md) · [METHODOLOGY.md](METHODOLOGY.md) · [DATA_PROVENANCE.md](DATA_PROVENANCE.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [REPRODUCIBILITY.md](REPRODUCIBILITY.md) · [LIMITATIONS.md](LIMITATIONS.md) · [RELEASE_NOTES_V1.0.0.md](RELEASE_NOTES_V1.0.0.md) · [MANUSCRIPT_DRAFT.md](paper/MANUSCRIPT_DRAFT.md) · [final-scientific-summary.json](data/final-scientific-summary.json) |


## Quadros, mapas, gráficos e arquivos de máquina

Os links preservam os caminhos canônicos. Arquivos por data concentram o manifesto, metadados, rastreio e métricas da passagem. Artefatos geométricos de H3 e CSVs comprimidos podem ser lidos diretamente sem abrir os dados brutos.

<details>
<summary>Histórico, snapshots e auditoria · 10 arquivos</summary>

- [altinopolis-pitangueiras-2019-2024-harmonized.csv](data/altinopolis-pitangueiras-2019-2024-harmonized.csv)
- [altinopolis-pitangueiras-2022-2024-harmonized.csv](data/altinopolis-pitangueiras-2022-2024-harmonized.csv)
- [altinopolis-pitangueiras-2024-harmonized.csv](data/altinopolis-pitangueiras-2024-harmonized.csv)
- [calibration-summary.json](data/calibration-summary.json)
- [calibration-summary.md](data/calibration-summary.md)
- [current-window-harmonized.csv](data/current-window-harmonized.csv)
- [ribeirao-preto-2024-harmonized-snapshot.csv](data/ribeirao-preto-2024-harmonized-snapshot.csv)
- [scientific-audit.json](data/scientific-audit.json)
- [series-diagnostics-aug21-31.json](data/series-diagnostics-aug21-31.json)
- [series-summary.json](data/series-summary.json)

</details>

<details>
<summary>Entradas regionais FIRMS arquivadas para reprodução · 12 arquivos</summary>

- [MODIS_SP_2019.csv.gz](data/raw/MODIS_SP_2019.csv.gz)
- [MODIS_SP_2020.csv.gz](data/raw/MODIS_SP_2020.csv.gz)
- [MODIS_SP_2021.csv.gz](data/raw/MODIS_SP_2021.csv.gz)
- [MODIS_SP_2022.csv.gz](data/raw/MODIS_SP_2022.csv.gz)
- [MODIS_SP_2023.csv.gz](data/raw/MODIS_SP_2023.csv.gz)
- [MODIS_SP_2024.csv.gz](data/raw/MODIS_SP_2024.csv.gz)
- [VIIRS_SNPP_SP_2019.csv.gz](data/raw/VIIRS_SNPP_SP_2019.csv.gz)
- [VIIRS_SNPP_SP_2020.csv.gz](data/raw/VIIRS_SNPP_SP_2020.csv.gz)
- [VIIRS_SNPP_SP_2021.csv.gz](data/raw/VIIRS_SNPP_SP_2021.csv.gz)
- [VIIRS_SNPP_SP_2022.csv.gz](data/raw/VIIRS_SNPP_SP_2022.csv.gz)
- [VIIRS_SNPP_SP_2023.csv.gz](data/raw/VIIRS_SNPP_SP_2023.csv.gz)
- [VIIRS_SNPP_SP_2024.csv.gz](data/raw/VIIRS_SNPP_SP_2024.csv.gz)

</details>

<details>
<summary>Etapa 2, união de registros, modelos e evento · 3 arquivos</summary>

- [fusion-event-2024.csv](data/phase2/fusion-event-2024.csv)
- [fusion-scales.csv](data/phase2/fusion-scales.csv)
- [fusion-study.json](data/phase2/fusion-study.json)

</details>

<details>
<summary>Etapa 3, NOAA e primeiro par orbital · 18 arquivos</summary>

- [2024-08-24-granule-plan.json](data/phase3/2024-08-24-granule-plan.json)
- [access-status.json](data/phase3/access-status.json)
- [noaa-positive-overlap-2024-08-24.json](data/phase3/noaa-positive-overlap-2024-08-24.json)
- [areas-by-coverage-state.json](data/phase3/orbital-2024-08-24/areas-by-coverage-state.json)
- [comparacao.csv](data/phase3/orbital-2024-08-24/comparacao.csv)
- [coverage-cells-z55.csv.gz](data/phase3/orbital-2024-08-24/coverage-cells-z55.csv.gz)
- [coverage-cells-z60.csv.gz](data/phase3/orbital-2024-08-24/coverage-cells-z60.csv.gz)
- [coverage-cells-z65.csv.gz](data/phase3/orbital-2024-08-24/coverage-cells-z65.csv.gz)
- [coverage-z55.geojson.gz](data/phase3/orbital-2024-08-24/coverage-z55.geojson.gz)
- [coverage-z60.geojson.gz](data/phase3/orbital-2024-08-24/coverage-z60.geojson.gz)
- [coverage-z65.geojson.gz](data/phase3/orbital-2024-08-24/coverage-z65.geojson.gz)
- [embedded-metadata.json](data/phase3/orbital-2024-08-24/embedded-metadata.json)
- [granule-manifest.json](data/phase3/orbital-2024-08-24/granule-manifest.json)
- [qa-diagnostic.json](data/phase3/orbital-2024-08-24/qa-diagnostic.json)
- [regional-scan-times.json](data/phase3/orbital-2024-08-24/regional-scan-times.json)
- [summary-z55.json](data/phase3/orbital-2024-08-24/summary-z55.json)
- [summary-z60.json](data/phase3/orbital-2024-08-24/summary-z60.json)
- [summary-z65.json](data/phase3/orbital-2024-08-24/summary-z65.json)

</details>

<details>
<summary>Etapa 4, dois pares, diagnóstico, QA e referências · 55 arquivos</summary>

- [2019-08-26-granule-plan.json](data/phase4/2019-08-26-granule-plan.json)
- [cells-z55-independent_legacy_land.geojson.gz](data/phase4/2019-08-26/cells-z55-independent_legacy_land.geojson.gz)
- [cells-z55-independent_m13.geojson.gz](data/phase4/2019-08-26/cells-z55-independent_m13.geojson.gz)
- [cells-z55-independent_strict.geojson.gz](data/phase4/2019-08-26/cells-z55-independent_strict.geojson.gz)
- [cells-z55-legacy_strict.geojson.gz](data/phase4/2019-08-26/cells-z55-legacy_strict.geojson.gz)
- [centers-aqua-z55-presence_m13_flagged.csv](data/phase4/2019-08-26/centers-aqua-z55-presence_m13_flagged.csv)
- [centers-aqua-z55-strict.csv](data/phase4/2019-08-26/centers-aqua-z55-strict.csv)
- [centers-viirs-z55-presence_m13_flagged.csv](data/phase4/2019-08-26/centers-viirs-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-strict.csv](data/phase4/2019-08-26/centers-viirs-z55-strict.csv)
- [comparison.csv](data/phase4/2019-08-26/comparison.csv)
- [comparison.json](data/phase4/2019-08-26/comparison.json)
- [embedded-metadata.json](data/phase4/2019-08-26/embedded-metadata.json)
- [firms-aqua-center-comparison.csv](data/phase4/2019-08-26/firms-aqua-center-comparison.csv)
- [firms-compatibility.json](data/phase4/2019-08-26/firms-compatibility.json)
- [firms-viirs-center-comparison.csv](data/phase4/2019-08-26/firms-viirs-center-comparison.csv)
- [geometry-and-qa-diagnostics.json](data/phase4/2019-08-26/geometry-and-qa-diagnostics.json)
- [granule-manifest.json](data/phase4/2019-08-26/granule-manifest.json)
- [regional-metadata.json](data/phase4/2019-08-26/regional-metadata.json)
- [cells-z55-independent_legacy_land.geojson.gz](data/phase4/2024-08-24/cells-z55-independent_legacy_land.geojson.gz)
- [cells-z55-independent_m13.geojson.gz](data/phase4/2024-08-24/cells-z55-independent_m13.geojson.gz)
- [cells-z55-independent_strict.geojson.gz](data/phase4/2024-08-24/cells-z55-independent_strict.geojson.gz)
- [cells-z55-legacy_strict.geojson.gz](data/phase4/2024-08-24/cells-z55-legacy_strict.geojson.gz)
- [cells-z60-independent_legacy_land.geojson.gz](data/phase4/2024-08-24/cells-z60-independent_legacy_land.geojson.gz)
- [cells-z60-independent_m13.geojson.gz](data/phase4/2024-08-24/cells-z60-independent_m13.geojson.gz)
- [cells-z60-independent_strict.geojson.gz](data/phase4/2024-08-24/cells-z60-independent_strict.geojson.gz)
- [cells-z60-legacy_strict.geojson.gz](data/phase4/2024-08-24/cells-z60-legacy_strict.geojson.gz)
- [cells-z65-independent_legacy_land.geojson.gz](data/phase4/2024-08-24/cells-z65-independent_legacy_land.geojson.gz)
- [cells-z65-independent_m13.geojson.gz](data/phase4/2024-08-24/cells-z65-independent_m13.geojson.gz)
- [cells-z65-independent_strict.geojson.gz](data/phase4/2024-08-24/cells-z65-independent_strict.geojson.gz)
- [cells-z65-legacy_strict.geojson.gz](data/phase4/2024-08-24/cells-z65-legacy_strict.geojson.gz)
- [centers-aqua-z55-presence_m13_flagged.csv](data/phase4/2024-08-24/centers-aqua-z55-presence_m13_flagged.csv)
- [centers-aqua-z55-strict.csv](data/phase4/2024-08-24/centers-aqua-z55-strict.csv)
- [centers-aqua-z60-presence_m13_flagged.csv](data/phase4/2024-08-24/centers-aqua-z60-presence_m13_flagged.csv)
- [centers-aqua-z60-strict.csv](data/phase4/2024-08-24/centers-aqua-z60-strict.csv)
- [centers-aqua-z65-presence_m13_flagged.csv](data/phase4/2024-08-24/centers-aqua-z65-presence_m13_flagged.csv)
- [centers-aqua-z65-strict.csv](data/phase4/2024-08-24/centers-aqua-z65-strict.csv)
- [centers-viirs-z55-presence_m13_flagged.csv](data/phase4/2024-08-24/centers-viirs-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-strict.csv](data/phase4/2024-08-24/centers-viirs-z55-strict.csv)
- [centers-viirs-z60-presence_m13_flagged.csv](data/phase4/2024-08-24/centers-viirs-z60-presence_m13_flagged.csv)
- [centers-viirs-z60-strict.csv](data/phase4/2024-08-24/centers-viirs-z60-strict.csv)
- [centers-viirs-z65-presence_m13_flagged.csv](data/phase4/2024-08-24/centers-viirs-z65-presence_m13_flagged.csv)
- [centers-viirs-z65-strict.csv](data/phase4/2024-08-24/centers-viirs-z65-strict.csv)
- [comparison.csv](data/phase4/2024-08-24/comparison.csv)
- [comparison.json](data/phase4/2024-08-24/comparison.json)
- [embedded-metadata.json](data/phase4/2024-08-24/embedded-metadata.json)
- [firms-aqua-center-comparison.csv](data/phase4/2024-08-24/firms-aqua-center-comparison.csv)
- [firms-compatibility.json](data/phase4/2024-08-24/firms-compatibility.json)
- [firms-viirs-center-comparison.csv](data/phase4/2024-08-24/firms-viirs-center-comparison.csv)
- [geometry-and-qa-diagnostics.json](data/phase4/2024-08-24/geometry-and-qa-diagnostics.json)
- [granule-manifest.json](data/phase4/2024-08-24/granule-manifest.json)
- [regional-metadata.json](data/phase4/2024-08-24/regional-metadata.json)
- [candidate-selection.json](data/phase4/candidate-selection.json)
- [cobertura-duas-duplas.png](data/phase4/cobertura-duas-duplas.png)
- [diagnostico-centros-aqua.png](data/phase4/diagnostico-centros-aqua.png)
- [sensibilidade-suporte-e-qa.png](data/phase4/sensibilidade-suporte-e-qa.png)

</details>

<details>
<summary>Etapa 5, amostra congelada, agregados e sete duplas · 82 arquivos</summary>

- [cells.csv.gz](data/phase5/2019-08-26/cells.csv.gz)
- [centers-aqua-z55-presence_m13_flagged.csv](data/phase5/2019-08-26/centers-aqua-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-presence_m13_flagged.csv](data/phase5/2019-08-26/centers-viirs-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-strict.csv](data/phase5/2019-08-26/centers-viirs-z55-strict.csv)
- [embedded-metadata.json](data/phase5/2019-08-26/embedded-metadata.json)
- [firms-aqua-center-comparison.csv](data/phase5/2019-08-26/firms-aqua-center-comparison.csv)
- [firms-compatibility.json](data/phase5/2019-08-26/firms-compatibility.json)
- [firms-viirs-center-comparison.csv](data/phase5/2019-08-26/firms-viirs-center-comparison.csv)
- [granule-manifest.json](data/phase5/2019-08-26/granule-manifest.json)
- [metrics.csv](data/phase5/2019-08-26/metrics.csv)
- [performance.json](data/phase5/2019-08-26/performance.json)
- [summary.json](data/phase5/2019-08-26/summary.json)
- [2020-02-23-granule-plan.json](data/phase5/2020-02-23-granule-plan.json)
- [cells.csv.gz](data/phase5/2020-02-23/cells.csv.gz)
- [embedded-metadata.json](data/phase5/2020-02-23/embedded-metadata.json)
- [firms-compatibility.json](data/phase5/2020-02-23/firms-compatibility.json)
- [granule-manifest.json](data/phase5/2020-02-23/granule-manifest.json)
- [metrics.csv](data/phase5/2020-02-23/metrics.csv)
- [performance.json](data/phase5/2020-02-23/performance.json)
- [summary.json](data/phase5/2020-02-23/summary.json)
- [2021-07-19-granule-plan.json](data/phase5/2021-07-19-granule-plan.json)
- [cells.csv.gz](data/phase5/2021-07-19/cells.csv.gz)
- [centers-viirs-z55-presence_m13_flagged.csv](data/phase5/2021-07-19/centers-viirs-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-strict.csv](data/phase5/2021-07-19/centers-viirs-z55-strict.csv)
- [embedded-metadata.json](data/phase5/2021-07-19/embedded-metadata.json)
- [firms-compatibility.json](data/phase5/2021-07-19/firms-compatibility.json)
- [firms-viirs-center-comparison.csv](data/phase5/2021-07-19/firms-viirs-center-comparison.csv)
- [granule-manifest.json](data/phase5/2021-07-19/granule-manifest.json)
- [metrics.csv](data/phase5/2021-07-19/metrics.csv)
- [performance.json](data/phase5/2021-07-19/performance.json)
- [summary.json](data/phase5/2021-07-19/summary.json)
- [2022-09-18-granule-plan.json](data/phase5/2022-09-18-granule-plan.json)
- [cells.csv.gz](data/phase5/2022-09-18/cells.csv.gz)
- [centers-viirs-z55-presence_m13_flagged.csv](data/phase5/2022-09-18/centers-viirs-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-strict.csv](data/phase5/2022-09-18/centers-viirs-z55-strict.csv)
- [embedded-metadata.json](data/phase5/2022-09-18/embedded-metadata.json)
- [firms-compatibility.json](data/phase5/2022-09-18/firms-compatibility.json)
- [firms-viirs-center-comparison.csv](data/phase5/2022-09-18/firms-viirs-center-comparison.csv)
- [granule-manifest.json](data/phase5/2022-09-18/granule-manifest.json)
- [metrics.csv](data/phase5/2022-09-18/metrics.csv)
- [performance.json](data/phase5/2022-09-18/performance.json)
- [summary.json](data/phase5/2022-09-18/summary.json)
- [2023-03-24-granule-plan.json](data/phase5/2023-03-24-granule-plan.json)
- [cells.csv.gz](data/phase5/2023-03-24/cells.csv.gz)
- [embedded-metadata.json](data/phase5/2023-03-24/embedded-metadata.json)
- [firms-compatibility.json](data/phase5/2023-03-24/firms-compatibility.json)
- [granule-manifest.json](data/phase5/2023-03-24/granule-manifest.json)
- [metrics.csv](data/phase5/2023-03-24/metrics.csv)
- [performance.json](data/phase5/2023-03-24/performance.json)
- [summary.json](data/phase5/2023-03-24/summary.json)
- [2024-05-18-granule-plan.json](data/phase5/2024-05-18-granule-plan.json)
- [cells.csv.gz](data/phase5/2024-05-18/cells.csv.gz)
- [embedded-metadata.json](data/phase5/2024-05-18/embedded-metadata.json)
- [firms-compatibility.json](data/phase5/2024-05-18/firms-compatibility.json)
- [granule-manifest.json](data/phase5/2024-05-18/granule-manifest.json)
- [metrics.csv](data/phase5/2024-05-18/metrics.csv)
- [performance.json](data/phase5/2024-05-18/performance.json)
- [summary.json](data/phase5/2024-05-18/summary.json)
- [cells.csv.gz](data/phase5/2024-08-24/cells.csv.gz)
- [centers-aqua-z55-presence_m13_flagged.csv](data/phase5/2024-08-24/centers-aqua-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-presence_m13_flagged.csv](data/phase5/2024-08-24/centers-viirs-z55-presence_m13_flagged.csv)
- [centers-viirs-z55-strict.csv](data/phase5/2024-08-24/centers-viirs-z55-strict.csv)
- [embedded-metadata.json](data/phase5/2024-08-24/embedded-metadata.json)
- [firms-aqua-center-comparison.csv](data/phase5/2024-08-24/firms-aqua-center-comparison.csv)
- [firms-compatibility.json](data/phase5/2024-08-24/firms-compatibility.json)
- [firms-viirs-center-comparison.csv](data/phase5/2024-08-24/firms-viirs-center-comparison.csv)
- [granule-manifest.json](data/phase5/2024-08-24/granule-manifest.json)
- [metrics.csv](data/phase5/2024-08-24/metrics.csv)
- [performance.json](data/phase5/2024-08-24/performance.json)
- [summary.json](data/phase5/2024-08-24/summary.json)
- [acquisition.json](data/phase5/acquisition.json)
- [consolidated.json](data/phase5/consolidated.json)
- [coverage-maps.png](data/phase5/coverage-maps.png)
- [instrument-scale-comparison.csv](data/phase5/instrument-scale-comparison.csv)
- [instrument-scale-summary.json](data/phase5/instrument-scale-summary.json)
- [instrument-scale.png](data/phase5/instrument-scale.png)
- [native-center-audit-summary.csv](data/phase5/native-center-audit-summary.csv)
- [paired-metrics.png](data/phase5/paired-metrics.png)
- [per-pair-metrics.csv](data/phase5/per-pair-metrics.csv)
- [processing.json](data/phase5/processing.json)
- [qa-support-decomposition.csv](data/phase5/qa-support-decomposition.csv)
- [sample-plan.json](data/phase5/sample-plan.json)

</details>

<details>
<summary>Figuras, mapas, contexto GIBS e interface histórica · 16 arquivos</summary>

- [fusion-study.png](assets/fusion-study.png)
- [noaa-positive-overlap.png](assets/noaa-positive-overlap.png)
- [orbital-coverage-maps-z55.png](assets/orbital-coverage-maps-z55.png)
- [orbital-coverage-maps-z60.png](assets/orbital-coverage-maps-z60.png)
- [orbital-coverage-maps-z65.png](assets/orbital-coverage-maps-z65.png)
- [orbital-fusion-comparison-z55.png](assets/orbital-fusion-comparison-z55.png)
- [orbital-fusion-comparison-z60.png](assets/orbital-fusion-comparison-z60.png)
- [orbital-fusion-comparison-z65.png](assets/orbital-fusion-comparison-z65.png)
- [pyroharmonix-2024-calendar.png](assets/pyroharmonix-2024-calendar.png)
- [pyroharmonix-2024-map-seasonality.png](assets/pyroharmonix-2024-map-seasonality.png)
- [pyroharmonix-ribeirao-preto-2024-08-calendario.png](assets/pyroharmonix-ribeirao-preto-2024-08-calendario.png)
- [pyroharmonix-ribeirao-preto-2024-08-webgis.png](assets/pyroharmonix-ribeirao-preto-2024-08-webgis.png)
- [pyroharmonix-ribeirao-preto-2024-current.png](assets/pyroharmonix-ribeirao-preto-2024-current.png)
- [ribeirao-preto-2024-08-24-viirs.jpg](assets/ribeirao-preto-2024-08-24-viirs.jpg)
- [ribeirao-preto-fire-2024-aug.gif](assets/ribeirao-preto-fire-2024-aug.gif)
- [scientific-audit.png](assets/scientific-audit.png)

</details>


## Procedimentos e scripts

- [Guia de reprodução](REPRODUCIBILITY.md), [auditoria histórica](../backend/api/management/commands/audit_science.py), [comparação de fusão](../backend/api/management/commands/study_fusion.py), [caso sintético de cobertura](../backend/api/management/commands/study_coverage.py), [gráficos da auditoria](plot_science_audit.py) e [gráficos de fusão](plot_fusion_study.py).
- [Primeiro piloto](../backend/orbital_pilot.py), [figuras](../backend/plot_orbital_pilot.py) e [comparação NOAA](../backend/orbital_external.py).
- [Seleção da segunda dupla](../backend/orbital_candidate.py), [auditoria geométrica e QA](../backend/orbital_phase4.py), [correspondência FIRMS](../backend/orbital_calibration_check.py) e [figuras de diagnóstico](../backend/plot_orbital_phase4.py).
- [Seleção estratificada](../backend/orbital_sample_plan.py), [aquisição limitada](../backend/orbital_sample_acquire.py), [execução serial](../backend/orbital_sample_batch.py), [comparação em suporte fixo](../backend/orbital_phase5.py), [consolidação](../backend/orbital_sample_summary.py) e [controle instrumental](../backend/orbital_geometry_reference.py).
- [Roadmap histórico](IMPROVEMENT_ROADMAP.md) e [apresentação arquivada do projeto](pyroharmonix-spaceapps-demo.pdf).
