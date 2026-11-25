# PyroHarmonix 1.0 — relatório científico consolidado

## 1. Resumo executivo

O PyroHarmonix mantém `detection_conditioned_v1` com `monthly_shrunk_union` como **índice regional de atividade registrada**. Na caixa de calibração de Altinópolis–Pitangueiras, em 2019–2024, a regra somou **2.282,5484123068522 equivalentes Aqua**, ante **1.530 registros Aqua**. A diferença arredondada de **49,2%** depende da definição do índice e do conjunto de registros. A contribuição causal da disponibilidade de observações permanece indeterminada. Nos experimentos orbitais, seis das sete duplas atingiram o suporte principal. O efeito observado em 2019 ao admitir M13 sinalizada desapareceu na comparação de suporte fixo. A fusão condicionada à cobertura permanece **experimental**. [Métricas e referências por artefato](data/final-scientific-summary.json)

## 2. Contextualização científica

Sensores polares amostram a superfície em órbitas, resoluções, horários e geometrias distintos. Um foco registrado é uma anomalia térmica associada a um pixel e pode representar fontes subpixel, observações repetidas ou fontes térmicas distintas. A série WebGIS resume esses registros em células e períodos. Área queimada exige produtos de cicatrizes ou perímetros, com unidade de área, e responde a uma pergunta diferente. [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) · [Guia MODIS C6.1](https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf)

## 3. Problema de pesquisa

A diferença entre totais MODIS-Aqua e VIIRS-SNPP decorre conjuntamente da detectabilidade, da resolução, da amostragem temporal, da composição dos estratos positivos e da disponibilidade de observação. O silêncio de um CSV FIRMS é insuficiente para distinguir ausência de detecção e ausência de observação válida. A inclusão da referência Aqua na própria previsão examinada também produz uma redução mecânica do erro.

## 4. Objetivos

Documentar e reproduzir a escala histórica regional, comparar modelos temporais com anos retidos, identificar as consequências da seleção por detecções registradas e operacionalizar uma análise experimental de QA, cobertura e coincidência orbital. A comparação em suporte fixo procura isolar o contraste de QA sob a mesma área e os mesmos critérios de tempo.

## 5. Área de estudo

Altinópolis–Pitangueiras, interior de São Paulo, delimitada por W −48,433, S −21,215243, E −47,181633 e N −20,8087035. A avaliação FIRMS usa 2019–2024. O recorte maior de Ribeirão Preto e seu CSV legado H3 8 são materiais históricos de demonstração, com cobertura interrompida. Os exports históricos, o estudo de caixa bruta e a amostra orbital têm domínios observacionais próprios. [Proveniência](DATA_PROVENANCE.md)

## 6. Fontes de dados

O fluxo histórico usa FIRMS Standard Processing `MODIS_SP` e `VIIRS_SNPP_SP`, em 12 extratos regionais gzip. O inventário da etapa 1 registrou 9.383 detecções únicas. O fluxo orbital usa `MYD14` e `MYD03` C6.1 para Aqua e `VNP14IMG` e `VNP03IMG` C2 para S-NPP. O CMR é fonte de catálogo e verificação de candidatas. Imagens Worldview/GIBS pertencem à contextualização visual. NOAA-20/21, MapBiomas Fogo e MCD64A1 têm usos externos distintos. [Inventário da auditoria](data/scientific-audit.json) · [Protocolo externo](EXTERNAL_VALIDATION_PROTOCOL.md)

## 7. Características dos sensores

| Sensor e plataforma | Pixel nominal no nadir | Máscara científica | Geolocalização |
| --- | ---: | --- | --- |
| MODIS em Aqua | 1 km | MYD14 C6.1, órbita segmentada em 5 min | MYD03 C6.1 |
| VIIRS em Suomi-NPP | 375 m nas bandas I | VNP14IMG C2, órbita segmentada em 6 min | VNP03IMG C2 |

O pixel aumenta fora do nadir. MODIS pode sobrepor varreduras adjacentes. VIIRS agrega amostras transversais em zonas e remove observações bow-tie identificadas. M13 é uma banda moderada de 750 m usada na recuperação de FRP. [MYD14](https://doi.org/10.5067/MODIS/MYD14.061) · [VNP14IMG](https://doi.org/10.5067/VIIRS/VNP14IMG.002) · [Guia VIIRS C2 v1.2](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf)

## 8. Metodologia histórica

O índice converge os registros para uma escala Aqua. Com dois sensores no estrato, usa a média entre Aqua e VIIRS multiplicado pelo fator congelado. Com contribuição de um sensor, mantém a contribuição observada ou ajustada elegível. Um turno desconhecido tem tratamento próprio e prioriza Aqua quando ambos os registros existem. Fora do domínio espacial elegível ou sem fator estimável, a série comparável usa Aqua. O armazenamento identifica valores observados, ajustados, fundidos, extrapolados, históricos e externos. Os snapshots com preenchimento aritmético por zero seguem arquivados. [Definição operacional](METHODOLOGY.md)

## 9. Indexação espacial H3

A ingestão indexa os centros em H3 8 e usa pais H3 7 para o estrato espacial. O estrato combina célula, dia UTC e turno. No orbital, o denominador é a área inteira de H3 7 em projeção equivalente, com a parcela avaliada na caixa gravada separadamente. A caixa do piloto intersecta 1.175 células e sua área avaliada da fase 3 foi aproximadamente 5.855,67 km². [Áreas por resolução H3](https://h3geo.org/docs/core-library/restable/) · [Cobertura do piloto](REAL_OBSERVATION_COVERAGE_REPORT.md)

## 10. Calibração e validação temporal

A razão mensal de somas registradas é regularizada para a razão anual por peso `n/(n+30)`. Há fallback anual quando a razão mensal é indefinida. Contagem e FRP têm fatores distintos. A calibração na união inclui a contribuição de cada sensor nas posições em que registrou e depende da exposição e seleção dos registros. A validação retém cada ano de 2019–2024 e ajusta os fatores com os cinco outros anos. O ajuste em toda a amostra fornece a referência regional de apresentação, enquanto as métricas fora do ano retido pertencem às avaliações de transferência temporal. [Metodologia original](SCIENTIFIC_METHODOLOGY.md) · [Validação](VALIDATION_REPORT.md)

## 11. Correção da validação circular

Na avaliação histórica sobre o mesmo suporte de 72 mês-anos, com 63 referências não nulas para MAPE, o VIIRS ajustado obteve **76,06302484434741%** e a média com Aqua obteve **38,031512422173705%**. Se `F = (A + V_ajustado)/2`, então `F − A = (V_ajustado − A)/2`. Essa redução é uma identidade, e a validação fora do ano compara o VIIRS estimado com Aqua registrado, sem inserir o alvo na estimativa. Aqua continua sendo referência observacional, e a acurácia em relação à verdade terrestre permanece fora desse desenho. [Auditoria, campo legacy_shared_reference_diagnostic](data/scientific-audit.json)

## 12. Comparação dos modelos de calibração

| Contagem H3 7, avaliações fora do ano | MAE por estrato de codetecção | WAPE mensal na união registrada | WAPE anual na união registrada |
| --- | ---: | ---: | ---: |
| VIIRS bruto | 4,152 | 411,13% | 413,27% |
| Razão mensal regularizada, codetecção | 1,319 | 79,77% | 76,85% |
| Razão mensal regularizada, união | 1,058 | 21,98% | 15,07% |
| OLS pela origem, codetecção | 1,085 | 27,20% | 19,15% |
| Huber pela origem, codetecção | 1,096 | 29,93% | 21,77% |
| OLS pela origem, união diária | 1,020 | 30,05% | 20,38% |
| Huber pela origem, união diária | 1,028 | 30,29% | 22,10% |

MAE e WAPE referem-se a suportes e escalas diferentes. A regressão diária OLS teve menor MAE fino que a regularização na união, cuja vantagem se observa nos totais mensais e anuais desta avaliação. Na avaliação anterior restrita às codetecções, foram 533 estratos H3 7, com WAPE mensal de contagem de 35,54% para a razão mensal regularizada e 25,21% para Huber. Esses WAPEs não são os da união. Resultados FRP têm unidade MW e não demonstram transferência independente. [Comparação ampliada](MODEL_COMPARISON_REPORT.md) · [Comparação em codetecção](VALIDATION_REPORT.md) · [Valores sem arredondamento](data/final-scientific-summary.json)

## 13. Desenvolvimento do pipeline orbital

A etapa 3 implementou aquisição limitada, manifests com assinatura binária e SHA-256, leitura HDF4/NetCDF4, pareamento por tempos de varredura e agregação H3. O piloto real de 24/08/2024 teve Aqua entre 59,03° e 63,16° e ficou sem interseção válida a 55°. Os cenários de 60° e 65° são sensibilidades. A etapa 4 acrescentou rastreabilidade dos centros, correção do filtro terrestre VIIRS e o par real de 26/08/2019. A etapa 5 usou as duas políticas de presença em suporte próprio e fixo, com sete duplas. [Fase 3](REAL_OBSERVATION_COVERAGE_REPORT.md) · [Fase 4](SECOND_ORBITAL_PILOT_REPORT.md) · [Fase 5](STRATIFIED_ORBITAL_SAMPLE_REPORT.md)

## 14. Reconstrução geométrica dos footprints

Os polígonos aproximados usam meios passos entre centros vizinhos na mesma varredura e projeção Lambert azimutal equivalente local. A partição exclusiva por menor ângulo evita contar a mesma área duas vezes. Entre os 67 centros Aqua aprovados a 65° em 24/08/2024, 35 perderam a propriedade do centro na regra legada por sobreposição com varredura adjacente. Em 22, a observação prioritária também tinha fogo e, em 13, terra sem detecção. Separar os centros da partição recuperou os 67 sem alterar a área para o mesmo QA. Nas quatro classes amostradas, as medianas da razão área reconstruída/IFOV variaram de 0,9932747290310869 a 1,0174773294518757. O controle valida a escala dimensional. A posição dos cantos e a identidade de focos físicos continuam em aberto. [Rastreio dos centros](FOOTPRINT_GEOMETRY_AUDIT.md) · [Referência instrumental](FOOTPRINT_INDEPENDENT_VALIDATION.md)

## 15. Políticas de QA

A revisão aplica geolocalização e terra válidas e exclui descartes e preenchimento. Para VIIRS, a política estrita exige bits 0–6 nominais e a política de presença com M13 sinalizada exige bits 0–5 nominais, preservando o bit 6 como informação. O bit 6 sinaliza M13 não nominal e não equivale por si só à rejeição da classificação de fogo. FRP tem critérios radiométricos próprios. Em 24/08/2024, o tratamento revisado manteve 82 centros estritos ou 347 com M13 sinalizada, entre 363 centros brutos na máscara. [Diagnóstico de QA](VIIRS_QA_SENSITIVITY_REPORT.md)

## 16. Cobertura observacional e zeros válidos

Um zero observado exige suporte demonstrado e nenhuma detecção na parcela válida. Classe inválida, nuvem, fora da varredura e geometria desconhecida permanecem distinguíveis. A regra experimental usa `(A + fV)/2` sobre a interseção válida sob o mesmo H3, iluminação e tolerância, incluindo zeros observados. As células sem suporte suficiente ficam indefinidas. O cenário principal fixa 55°, 80% da área inteira de H3 7 e 60 min. As sensibilidades usam 60% e 90% de área e 30, 45 e 90 min de tolerância. [Protocolo orbital](ORBITAL_EXPERIMENT_PROTOCOL.md)

## 17. Resultados das sete duplas orbitais

| Data UTC | Turno | Área comum estrita, km² | Células elegíveis | Células positivas estritas | Jaccard estrito |
| --- | --- | ---: | ---: | ---: | ---: |
| 26/08/2019 | Dia | 5.778,93 | 1.021 | 3 | 0 |
| 23/02/2020 | Dia | 467,43 | 23 | 0 | — |
| 19/07/2021 | Noite | 5.772,36 | 1.017 | 1 | 0 |
| 18/09/2022 | Dia | 5.759,20 | 1.016 | 1 | 0 |
| 24/03/2023 | Noite | 5.774,13 | 1.020 | 0 | — |
| 18/05/2024 | Dia | 5.776,87 | 1.023 | 0 | — |
| 24/08/2024 | Dia | 0 | 0 | — | — |

A tabela usa o QA estrito em suporte próprio, H3 7, 55°, 80% e 60 min. As áreas estão arredondadas. A separação local máxima ficou abaixo de 30 min em todas as duplas, e os quatro limites temporais renderam os mesmos resultados. Em fevereiro de 2020, nuvens restringiram a área comum. A etapa 5 acrescentou cinco duplas, 20 grânulos e 1.081.100.852 bytes verificados. Novembro de 2024 ficou sem par elegível no plano. [Amostra, desempenho e seleção](STRATIFIED_ORBITAL_SAMPLE_REPORT.md) · [Resultados exatos, matriz e métricas](data/phase5/consolidated.json)

## 18. Comparação em suporte fixo

Na regra M13 com suporte próprio, 26/08/2019 passou de 0 a 0,50 no Jaccard, com duas codetecções em quatro células positivas. Em suporte fixo, o Jaccard permaneceu 0. Nos sete pares, a política M13 teve Jaccard agrupado de 1/3 em suporte próprio (seis células positivas) e 0 no suporte fixo (cinco). A média simples por dupla, apenas entre valores definidos, foi 1/6 em suporte próprio e 0 em suporte fixo (três duplas). Nenhuma das seis duplas utilizáveis no cenário principal mudou a contagem VIIRS entre as políticas no suporte fixo. A redução por zeros confirmados mede uma diferença de regra de fusão, com acurácia absoluta ainda indeterminada. [QA fixo](QA_FIXED_SUPPORT_COMPARISON.md) · [Decomposição da fusão](FUSION_ROBUSTNESS_REPORT.md)

## 19. Viabilidade da calibração orbital

Os centros brutos dos dois produtos encontraram correspondência um a um com o FIRMS local no recorte, antes de QA e cobertura. Na fase 5, nenhuma dupla satisfez o requisito de dez centros de cada sensor no suporte fixo. As cinco novas duplas tiveram zero centros Aqua brutos de fogo na caixa e três centros VIIRS no suporte estrito. O fator histórico foi congelado. O pareamento dos centros verifica proveniência e compatibilidade nominal. A transferência de calibração exige suporte comparável e amostras independentes de treino e avaliação. [Viabilidade de calibração](ORBITAL_CALIBRATION_FEASIBILITY.md)

## 20. Discussão científica

Na caixa bruta em H3 7, 3.028 estratos da união FIRMS incluíram 533 codetecções, 444 registros exclusivos Aqua e 2.051 exclusivos S-NPP. Aqua teve 1.530 detecções e S-NPP 7.853. O total ajustado VIIRS foi 1.529,2696268011991. A estimativa histórica com zero somou 1.529,6348134005996 equivalentes Aqua e a condicionada aos registros 2.282,5484123068522. O contraste é de cerca de 49,2% frente a Aqua e 49,22% frente à regra histórica, com denominadores distintos.

Entre 21 e 31/08/2024, na mesma decomposição, a regra histórica somou 450,1623610924722 e a atual 591,883594418776. As contribuições adicionais foram 58,5 nos estratos exclusivos Aqua e 83,2212333263038 nos exclusivos VIIRS. A comparação do export histórico com o máximo anterior, razão 6,370379472667685, pertence ao export com zero. A diferença do índice não pode ser atribuída causalmente à cobertura. Em suporte orbital fixo, diferenças de resolução, QA e horário permanecem possíveis. [Decomposição da etapa 2](FUSION_BIAS_ANALYSIS.md) · [Validação do export](VALIDATION_REPORT.md)

## 21. Limitações

A série é regional e sua calibração carece de validação universal. Equivalentes Aqua são uma unidade de índice, sem correspondência demonstrada com incêndios físicos individuais ou área queimada. Jaccard, Dice, Kappa e erros pareados são métricas de concordância entre produtos com referência Aqua onde aplicável. A amostra orbital é intencional, com poucos positivos, dependência espacial entre células e ausência de verdade terrestre. O suporte muda com geometria, nuvens, QA e recorte. A validação dimensional não estabelece a posição exata dos footprints. [Limitações para uso e publicação](LIMITATIONS.md)

## 22. Conclusão

Preservar o índice regional vigente. Manter a fusão condicionada à cobertura como experimento. O desenho mediu diferenças por condição de observação e separou o papel do suporte e da regra de fusão. A amostra deixa em aberto a calibração orbital, a acurácia independente e a contribuição causal da cobertura para os 49,2% históricos.

## 23. Trabalhos futuros

Validação independente de presença, comparação dimensional e posicional com geometria de referência, transferência para NOAA-20/21 em passes retidos e associação espaço-temporal com cicatrizes MapBiomas Fogo ou MCD64A1 são perspectivas de pesquisa. Esses desfechos e as unidades de área queimada devem ser definidos separadamente. [Protocolo externo](EXTERNAL_VALIDATION_PROTOCOL.md)

## 24. Referências bibliográficas

- NASA FIRMS. *Area API* e arquivo de focos ativos Standard Processing. [API](https://firms.modaps.eosdis.nasa.gov/api/area/) · [Produtos](https://firms.modaps.eosdis.nasa.gov/content/active_fire/)
- Giglio, L. e Justice, C. (2021). *MODIS/Aqua Thermal Anomalies/Fire 5-Min L2 Swath 1km V061*. NASA LP DAAC. [DOI](https://doi.org/10.5067/MODIS/MYD14.061)
- NASA LAADS DAAC. *MODIS Geolocation C6.1* e *VIIRS/NPP Terrain Corrected Geolocation 375 m V002*. [MOD03/MYD03](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD03) · [VNP03IMG](https://doi.org/10.5067/VIIRS/VNP03IMG.002)
- NASA LP DAAC. *VIIRS/NPP Active Fires 6-Min L2 Swath 375m V002*. [DOI](https://doi.org/10.5067/VIIRS/VNP14IMG.002)
- NASA/Land SIPS. *Collection 2 VIIRS 375 m Active Fire Product User Guide*, v1.2. [Guia C2](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf)
- NASA MODIS Dark Target e NOAA JPSS. Referências de geometria angular e amostragem. [MODIS ATBD](https://darktarget.gsfc.nasa.gov/atbd-products) · [VIIRS Imagery ATBD](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/D0001-M01-S01-008_JPSS_ATBD_VIIRS-Imagery_E.pdf)
- H3. *Tables of Cell Statistics Across Resolutions*. [Áreas H3](https://h3geo.org/docs/core-library/restable/)

## 25. Reprodução

Os caminhos e comandos originais permanecem no [índice de artefatos](SCIENTIFIC_ARTIFACT_INDEX.md). Use os CSVs locais e os manifests congelados para conferir a evidência. O roteiro atualizado separa a suíte PostgreSQL, a reprodução histórica em base temporária e a reprodução orbital com os binários já obtidos. Os arquivos derivados da reprodução ficam em diretório separado. [Roteiro reproduzível](REPRODUCIBILITY.md)
