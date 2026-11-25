# Comparação de QA no próprio suporte e no suporte fixo

A partição espacial é calculada uma vez. A política M13 promove apenas os estados que passam pelos demais critérios, de modo que o suporte estrito é subconjunto do suporte M13. Os fragmentos estritos de área, horário e iluminação são reutilizados no suporte fixo. Em ambas as políticas os centros precisam estar nesse suporte e atender à condição temporal usando seu próprio horário. Igualdade de área, células elegíveis e centros Aqua na modalidade fixa foi verificada em todas as tolerâncias e limiares. As colunas de fração individual no CSV de células descrevem a área de cada política na região. A coluna conjunta é a comparação da modalidade indicada.

## Retenção e área no cenário principal

| Data | Aqua bruto / aprovado / retido | VIIRS bruto / retido estrito / retido M13 | Área válida VIIRS estrito → M13 (km²) | Comum estrito/fixo (km²) | Comum M13 próprio (km²) |
| --- | --- | --- | ---: | ---: | ---: |
| 26/08/2019 | 4 / 4 / 4 | 9 / 3 / 8 | 5.797,95 → 5.800,48 | 5.778,93 | 5.781,45 |
| 23/02/2020 | 0 / 0 / 0 | 0 / 0 / 0 | 916,25 → 916,25 | 467,43 | 467,43 |
| 19/07/2021 | 0 / 0 / 0 | 2 / 2 / 2 | 5.800,67 → 5.800,67 | 5.772,36 | 5.772,36 |
| 18/09/2022 | 0 / 0 / 0 | 1 / 1 / 1 | 5.777,56 → 5.777,56 | 5.759,20 | 5.759,20 |
| 24/03/2023 | 0 / 0 / 0 | 0 / 0 / 0 | 5.798,23 → 5.798,23 | 5.774,13 | 5.774,13 |
| 18/05/2024 | 0 / 0 / 0 | 0 / 0 / 0 | 5.794,40 → 5.794,40 | 5.776,87 | 5.776,87 |
| 24/08/2024 | 67 / 0 / 0 | 363 / 82 / 347 | 5.526,16 → 5.629,88 | 0,00 | 0,00 |


| Data | VIIRS no suporte comum estrito → M13 própria → M13 fixa | Codetecções estrita → M13 própria → M13 fixa | Jaccard estrito → M13 próprio → M13 fixo |
| --- | --- | --- | --- |
| 26/08/2019 | 3 → 7 → 3 | 0 → 2 → 0 | 0,000 → 0,500 → 0,000 |
| 23/02/2020 | 0 → 0 → 0 | 0 → 0 → 0 | — → — → — |
| 19/07/2021 | 2 → 2 → 2 | 0 → 0 → 0 | 0,000 → 0,000 → 0,000 |
| 18/09/2022 | 1 → 1 → 1 | 0 → 0 → 0 | 0,000 → 0,000 → 0,000 |
| 24/03/2023 | 0 → 0 → 0 | 0 → 0 → 0 | — → — → — |
| 18/05/2024 | 0 → 0 → 0 | 0 → 0 → 0 | — → — → — |
| 24/08/2024 | — → — → — | — → — → — | — → — → — |


Em 26/08/2019, a mudança de Jaccard de 0 para 0,50 no suporte próprio desapareceu na comparação fixa. No conjunto de 6 duplas com suporte fixo a 80%, nenhuma apresentou mudança na contagem VIIRS dentro do suporte fixo. Essa decomposição separa o efeito da regra radiométrica dentro da área comum da entrada de áreas novas na análise. O contraste é descritivo e a acurácia permanece sem referência independente. O campo de FRP dos produtos foi mantido apenas na trilha de proveniência e não entra na elegibilidade, presença ou concordância. [Desfechos por cenário e suporte](data/phase5/qa-support-decomposition.csv) · [Rastreio de entradas, retenção e exclusões](data/phase5/native-center-audit-summary.csv) · [Fundamentação do bit 6](VIIRS_QA_SENSITIVITY_REPORT.md)
