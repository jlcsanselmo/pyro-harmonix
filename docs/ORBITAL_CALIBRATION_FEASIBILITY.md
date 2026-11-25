# Viabilidade de calibração orbital específica

## Correspondência com registros FIRMS

Usamos os arquivos Standard Processing locais, a mesma data UTC, sensor, turno e janela nominal de cada grânulo. A correspondência um a um foi avaliada a 10, 100 e 500 m. A coluna abaixo usa 100 m. Essa etapa compara identidade dos registros publicados e dos centros brutos, antes do suporte e QA orbitais.

| Data | Aqua máscara / FIRMS / pareados | VIIRS máscara / FIRMS / pareados |
| --- | --- | --- |
| 26/08/2019 | 4 / 4 / 4 | 9 / 9 / 9 |
| 23/02/2020 | 0 / 0 / 0 | 0 / 0 / 0 |
| 19/07/2021 | 0 / 0 / 0 | 2 / 2 / 2 |
| 18/09/2022 | 0 / 0 / 0 | 1 / 1 / 1 |
| 24/03/2023 | 0 / 0 / 0 | 0 / 0 / 0 |
| 18/05/2024 | 0 / 0 / 0 | 0 / 0 / 0 |
| 24/08/2024 | 67 / 67 / 67 | 363 / 363 / 363 |


## Razões no suporte comum, cenário principal

A razão observada é o total de centros Aqua dividido pelo total bruto VIIRS. A razão vale zero quando Aqua tem contagem zero e VIIRS tem positivos. Quando VIIRS soma zero ou não há suporte, fica indefinida. O fator FIRMS de cada mês foi congelado. As três colunas observadas são comparações de domínio e não reajustes.

| Data | Turno | Geometria | Fator histórico | Estrito próprio | M13 própria | M13 fixa |
| --- | --- | --- | ---: | --- | --- | --- |
| 26/08/2019 | Dia | ≤30° | 0,210 | 1/3 (0,333) | 3/7 (0,429) | 1/3 (0,333) |
| 23/02/2020 | Dia | ≤30° | 0,317 | 0/0 (—) | 0/0 (—) | 0/0 (—) |
| 19/07/2021 | Noite | 30–55° | 0,198 | 0/2 (0,000) | 0/2 (0,000) | 0/2 (0,000) |
| 18/09/2022 | Dia | 30–55° | 0,175 | 0/1 (0,000) | 0/1 (0,000) | 0/1 (0,000) |
| 24/03/2023 | Noite | 30–55° | 0,226 | 0/0 (—) | 0/0 (—) | 0/0 (—) |
| 18/05/2024 | Dia | 30–55° | 0,182 | 0/0 (—) | 0/0 (—) | 0/0 (—) |
| 24/08/2024 | Dia | >55° | 0,210 | — | — | — |


**Nenhuma dupla atingiu** pelo menos 10 centros de cada sensor no suporte fixo estrito. O protocolo exige seis para cogitar uma calibração experimental simples. Assim, mantivemos o fator histórico como baseline e nenhuma dupla foi usada para ajustar ou validar um fator novo. O JSON consolidado distingue massas agrupadas de médias, medianas e dispersão entre duplas. Variações associadas a turno, geometria ou QA nesta amostra não identificam dependência estável do fator, dada a escassez de positivos e os denominadores pequenos. O fator histórico foi desenvolvido para contagens registradas em estratos FIRMS. As máscaras orbitais filtram QA, horário, ângulo e área. A identidade de registros brutos fornece um controle de procedência, e a transferência do coeficiente exige amostra informativa e avaliação por duplas independentes. [Calibração histórica](FUSION_BIAS_ANALYSIS.md) · [Métricas e razões agrupadas por estrato](data/phase5/consolidated.json)
