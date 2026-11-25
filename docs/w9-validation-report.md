# Relatório final W9 — validação do pipeline Aqua-eq (atualizado em W10)

> Registro histórico da regra com preenchimento por zero. A reavaliação e a metodologia atual estão no [relatório de validação científica](VALIDATION_REPORT.md).

## Escopo

Este relatório registra a validação das fases W1–W9 e as correções pós-validação W10. A calibração é exploratória, limitada à caixa Altinópolis–Pitangueiras; não constitui validação científica independente nem produto operacional. Os resultados são snapshots dos registros disponíveis no banco local.

## Resultado por fase

| Fase | Resultado |
| --- | --- |
| W1 — disponibilidade dos sensores | Harmonização sensível às janelas de operação de MODIS-Aqua e VIIRS-SNPP, com fallback Aqua-basis. |
| W2 — bordas da área | Pais H3 cortados pelos limites recuperam detecções de filhos armazenados fora do retângulo. |
| W3 — reconstrução | `rebuild_harmonized` reconstrói Hotspots derivados em intervalo opcional e restringe a purga a Hotspots automatizados selecionados. |
| W4 — validação | Relatório inclui sensibilidade de fatores/fusões, correlações, continuidade e folds leave-one-year-out. |
| W5 — API | API expõe calibração, resultados de série, cobertura, CSVs e calendário. |
| W6 — interface | Itens implementados estão discriminados individualmente abaixo. |
| W7 — reprodução offline | Comandos para exportar/carregar amostras FIRMS, executar pipeline demonstrativo e exportar série. |
| W8 — documentação | README documenta limitações, API, reconstrução, reprodução e os dados exportados. |
| W9 — validação final | Testes, dados demonstrativos, snapshot de calibração e relatórios executados. |
| W10 — correções pós-validação | Unidade MAPE corrigida e testada; diagnósticos por janela executados; resumo anual regenerado; Ribeirão Preto rotulado como legado. |

## Verificações executadas

| Verificação | Resultado |
| --- | --- |
| `docker compose run --rm --no-deps -v "<repo>\backend:/app" api python manage.py test api.tests --keepdb` | **56 testes passaram**; system check sem problemas. |
| `git diff --check` | Passou após as alterações finais. |
| `npm --prefix frontend ci` | 70 pacotes instalados do lockfile; auditoria informou zero vulnerabilidades. |
| `npm --prefix frontend run build` | Passou com Vite 6.4.6; 1.622 módulos transformados. |
| Exportação regional de amostra FIRMS | 12 arquivos `.csv.gz` (MODIS-Aqua e VIIRS-SNPP, 2019–2024), 170.097 bytes (~0,162 MB). |
| `validate_calibration --summary-only --output ... --markdown ...` | JSON e Markdown regenerados; o Markdown tem 29 linhas (limite: 40). |
| `calculate_calibration()` e `export_calibration_snapshot()` | Snapshot regional com 24 registros, calculado a partir de 3.028 estratos. |

## Diagnósticos por janela (2019–2024)

`series_diagnostics` compara detecções FIRMS brutas com Hotspots automatizados para as mesmas datas de calendário em cada ano:

| Janela | Ano | Aqua raw | SNPP raw | Hotspots | Soma `harmonized_count` |
| --- | ---: | ---: | ---: | ---: | ---: |
| 21–31 ago. | 2019 | 6 | 32 | 19 | 6,257397 |
| 21–31 ago. | 2020 | 15 | 45 | 30 | 12,228479 |
| 21–31 ago. | 2021 | 66 | 392 | 104 | 70,664921 |
| 21–31 ago. | 2022 | 9 | 52 | 27 | 9,964020 |
| 21–31 ago. | 2023 | 0 | 9 | 6 | 0,945696 |
| 21–31 ago. | 2024 | 465 | 2.116 | 411 | 450,162361 |
| agosto | 2019 | 38 | 154 | 72 | 33,156520 |
| agosto | 2020 | 108 | 402 | 147 | 95,030926 |
| agosto | 2021 | 103 | 592 | 175 | 109,575306 |
| agosto | 2022 | 15 | 60 | 36 | 13,804639 |
| agosto | 2023 | 1 | 36 | 21 | 4,282783 |
| agosto | 2024 | 479 | 2.289 | 481 | 474,630582 |
| ago.–set. | 2019 | 77 | 385 | 164 | 72,778592 |
| ago.–set. | 2020 | 216 | 990 | 330 | 197,661132 |
| ago.–set. | 2021 | 234 | 1.493 | 423 | 250,501541 |
| ago.–set. | 2022 | 18 | 74 | 48 | 16,529461 |
| ago.–set. | 2023 | 10 | 103 | 66 | 14,644430 |
| ago.–set. | 2024 | 617 | 2.944 | 651 | 598,272486 |

A menor janela solicitada, **21–31 de agosto**, tem Hotspots nos cinco anos históricos. A condição para rebuild corretivo não ocorreu; `rebuild_harmonized --purge-automated` não foi executado. A causa do resumo anterior sem histórico era o exporter consultar as datas reais de 2024 em vez de projetar a mesma janela de calendário para cada ano. Os registros históricos já existiam; o exporter foi corrigido e o resumo regenerado.

## Dados demonstrativos

Os CSVs preservam os pesos fracionários em `harmonized_count`:

| Arquivo | Linhas | Total equivalente |
| --- | ---: | ---: |
| `altinopolis-pitangueiras-2019-2024-harmonized.csv` | 2.750 | 1.497,102085 |
| `altinopolis-pitangueiras-2022-2024-harmonized.csv` | 1.254 | 797,796924 |
| `altinopolis-pitangueiras-2024-harmonized.csv` | 859 | 682,009250 |
| `current-window-harmonized.csv` — 21–31 ago. 2024 | 411 | 450,162361 |

Para a janela escolhida, a mediana histórica é 9,964020; P25 é 6,257397; P75 é 12,228479; o valor de 2024 está no percentil 100 dos cinco anos anteriores. A anomalia absoluta é 440,198341 e a percentual é 4.417,88%. Os totais não comprovam cobertura completa.

## Sensibilidade da calibração

O relatório completo está em [`data/calibration-summary.md`](data/calibration-summary.md). A validação cobre contagem, não FRP.

| Pair mode | H3 | Factor MAPE | Zero-filled MAPE | Present-average / MODIS | Maximum / MODIS | c |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| union | 7 | 76,06% | 38,03% | 1,492 | 1,675 | 0,508 |
| union | 6 | 75,78% | 37,89% | 1,388 | 1,596 | 0,612 |
| codetect | 7 | 139,13% | 69,57% | 1,991 | 2,188 | 0,472 |
| codetect | 6 | 133,22% | 66,61% | 1,824 | 2,043 | 0,575 |

O MAPE mensal é expresso em porcentagem uma única vez. No cenário union, o erro da fusão zero-filled é metade do erro do fator. O ratio in-sample próximo de 1 não é validação: sem shrinkage, é 1 por construção. Os diagnósticos mais informativos são `c`, as fusões present-average/maximum, os folds leave-one-year-out e a diferença entre union e codetect.

## TODO(numbers)

Nenhum placeholder numérico pendente para a amostra regional atual. Os dados e métricas nos CSVs/JSON são snapshots e devem ser regenerados após nova coleta ou rebuild.

## Desvios do contrato e riscos

- **Rebuild condicional:** não executado porque as janelas têm Hotspots históricos; a janela mínima tem cinco anos anteriores. O defeito estava no agrupamento temporal do resumo, não em ausência de Hotspots.
- **Cobertura:** os dados armazenados são incompletos; ausência de linhas em qualquer outra janela não significa ausência de fogo.
- **Generalização:** fatores derivam somente da caixa regional e não devem ser extrapolados para outras áreas ou biomas.
- **Validação científica:** não houve validação independente contra produto de referência; FRP não foi validado.
- **Reprodução:** `demo_pipeline` recalcula fatores e substitui Hotspots automatizados; executar apenas em banco descartável ou após proteger os dados derivados. As detecções FIRMS brutas não são removidas.
- **Commits:** não foram criados; as alterações permanecem no worktree para revisão e commit pelo usuário.

## W6 — itens feitos e não feitos (um por linha)

- Atalhos de seleção de períodos — **FEITO**.
- Painel de fatores e fusões mensais/anuais — **FEITO**.
- Exibição da área e da relação com a caixa de calibração — **FEITO**.
- Badge do estado de calibração/cobertura — **FEITO**.
- Comparação histórica e confiabilidade da anomalia — **FEITO**.
- Rampa de cores da atividade — **FEITO**.
- Desenho de retângulo no mapa e cancelamento com Escape — **FEITO**.
- Exportação de calendário em CSV — **FEITO**.
- Visualizador contextual da imagem e animação de queimadas — **FEITO**.
- Instalação com `npm ci` e build de produção — **FEITO** em W10.
- Validação visual manual em navegador após o build — **NÃO FEITO**.

## Arquivos alterados

- `README.md`
- `backend/api/management/commands/firms_scheduler.py`
- `backend/api/management/commands/demo_pipeline.py`
- `backend/api/management/commands/export_firms_sample.py`
- `backend/api/management/commands/export_harmonized_csv.py`
- `backend/api/management/commands/load_firms_sample.py`
- `backend/api/management/commands/rebuild_harmonized.py`
- `backend/api/management/commands/series_diagnostics.py`
- `backend/api/management/commands/validate_calibration.py`
- `backend/api/migrations/0007_regional_sensor_calibration.py`
- `backend/api/migrations/0008_regional_calibration_zero_filled_fusion.py`
- `backend/api/models.py`
- `backend/api/services/calibration_validation.py`
- `backend/api/services/firms.py`
- `backend/api/tests.py`
- `backend/api/urls.py`
- `backend/api/views.py`
- `backend/api/data/regional_sensor_calibration.json`
- `frontend/src/App.jsx`
- `frontend/src/styles.css`
- `frontend/public/imagery/ribeirao-preto-2024-08-24-viirs.jpg`
- `frontend/public/imagery/ribeirao-preto-fire-2024-aug.gif`
- `docs/data/altinopolis-pitangueiras-2019-2024-harmonized.csv`
- `docs/data/altinopolis-pitangueiras-2022-2024-harmonized.csv`
- `docs/data/altinopolis-pitangueiras-2024-harmonized.csv`
- `docs/data/calibration-summary.json`
- `docs/data/calibration-summary.md`
- `docs/data/current-window-harmonized.csv`
- `docs/data/series-summary.json`
- `docs/data/raw/MODIS_SP_2019.csv.gz` through `MODIS_SP_2024.csv.gz`
- `docs/data/raw/VIIRS_SNPP_SP_2019.csv.gz` through `VIIRS_SNPP_SP_2024.csv.gz`
- `docs/w9-validation-report.md`
