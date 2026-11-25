# Influência da geometria orbital, dos indicadores de qualidade e da cobertura observacional na harmonização multissensor de focos ativos de fogo MODIS e VIIRS

**Influence of orbital geometry, quality flags, and observational coverage on multisensor harmonization of MODIS and VIIRS active-fire detections**

Rascunho para revisão humana. Confirmar a lista e ordem de autores, afiliações, contribuições, autor correspondente, financiamento, conflitos de interesse, agradecimentos, termos de distribuição e disponibilidade pública do código antes de preparar submissão.

## Resumo

Investigamos como calibração regional, qualidade e suporte observacional afetam a harmonização de detecções MODIS-Aqua e VIIRS-SNPP em Altinópolis–Pitangueiras, Brasil. Com registros FIRMS Standard Processing de 2019–2024, comparamos fatores em anos retidos e duas regras de fusão. Em sete duplas orbitais, estimamos suporte comum com máscaras científicas, aproximações dos footprints e duas políticas de QA que diferem no tratamento de M13. Na caixa bruta de calibração, a regra de registros somou 2.282,55 equivalentes Aqua ante 1.530 registros Aqua. A regularização na união obteve WAPE mensal de 21,98% e anual de 15,07% frente a Aqua nos anos retidos. Seis duplas foram elegíveis sob o cenário de 55°, interseção de pelo menos 80% de H3 7 e diferença temporal de até 60 min. Em 2019, o Jaccard positivo subiu de 0 para 0,50 em suporte próprio com M13 sinalizada e foi 0 em suporte fixo. A amostra sustenta o uso descritivo do índice e a avaliação experimental de cobertura. A validação independente e o ajuste de uma calibração orbital exigem evidência adicional.

**Palavras-chave** · Fogo ativo, sensoriamento remoto, MODIS, VIIRS, H3, suporte observacional.

## Abstract

We examined how regional calibration, quality flags, and observational support affect the harmonization of MODIS-Aqua and VIIRS-SNPP detections in Altinópolis–Pitangueiras, Brazil. We evaluated factors in held-out years with 2019–2024 FIRMS Standard Processing records and compared two fusion rules. For seven orbital pairs, we estimated common support using science masks, approximate footprints, and two policies for the M13 quality flag. In the calibration region, the detection-conditioned rule yielded 2,282.55 Aqua-equivalent detections compared with 1,530 recorded Aqua detections. The regularized recorded-union calibration yielded monthly and annual WAPE values of 21.98% and 15.07% against observed Aqua counts in held-out years. Six pairs attained common support under the primary criteria of a 55-degree zenith limit, at least 80% of a resolution-7 H3 cell, and a 60-minute tolerance. In the 2019 pair, positive Jaccard increased from 0 to 0.50 under the M13-flagged policy on its own support and remained 0 on fixed support. The regional index remains descriptive, and coverage-conditioned fusion remains experimental. Independent accuracy and orbital recalibration require further evidence.

**Keywords** · Active fire, remote sensing, MODIS, VIIRS, H3, observational support.

## Introdução

Registros de focos ativos representam observações térmicas por pixel. Resolução nominal, horário de passagem, ângulo, nuvens e algoritmos de detecção determinam quais observações entram no registro. Combinar MODIS-Aqua e VIIRS-SNPP pode ampliar registros disponíveis, mas o silêncio do arquivo pontual tem cobertura desconhecida. Neste estudo, distinguimos a escala de atividade registrada, a concordância orbital com cobertura pareada e a questão ainda aberta da acurácia independente. [FIRMS](https://firms.modaps.eosdis.nasa.gov/content/active_fire/) · [MYD14 C6.1](https://doi.org/10.5067/MODIS/MYD14.061) · [VNP14IMG C2](https://doi.org/10.5067/VIIRS/VNP14IMG.002)

## Materiais e métodos

### Área, série histórica e fatores

A caixa incluiu W −48,433, S −21,215243, E −47,181633 e N −20,8087035. Usamos MODIS_SP filtrado para Aqua e VIIRS_SNPP_SP de 2019 a 2024. O estrato foi célula H3 7, data UTC e turno. A razão mensal de somas foi regularizada à razão anual com peso n/(n+30). Em cada fold, o ano retido foi reservado para comparação contra Aqua registrado. Comparamos contagem bruta, razões anual e mensal, regularização e regressões pela origem. Reportamos separadamente codetecção e união registrada, e mantivemos parâmetros de produção congelados. [Método e desenho](../METHODOLOGY.md) · [Estudo dos modelos](../MODEL_COMPARISON_REPORT.md)

### Duplas orbitais, geometria e QA

Usamos MYD14/MYD03 C6.1 e VNP14IMG/VNP03IMG C2. Footprints aproximados por meios passos foram projetados em Lambert azimutal equivalente. A partição por menor zenital atribuiu área disjunta. Os centros de fogo seguiram os índices dos pixels, com rastreabilidade própria. Comparamos QA estrito, que exige bits VIIRS 0–6 nominais, e QA de presença com M13 sinalizada, que exige bits 0–5 nominais. O critério principal combinou 55°, iluminação concordante, diferença de até 60 min e pelo menos 80% da área inteira de H3 7. Calculamos métricas em suporte próprio e na interseção fixa. A dupla foi a unidade amostral para médias simples. Métricas agrupadas foram descritivas. [Protocolo prévio](../ORBITAL_EXPERIMENT_PROTOCOL.md) · [Guia VIIRS C2](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf)

## Resultados

Na caixa bruta, 3.028 estratos incluíram 533 codetecções, 444 exclusivos Aqua e 2.051 exclusivos S-NPP. A estimativa condicionada a registros somou 2.282,5484 equivalentes Aqua e a regra histórica com zero somou 1.529,6348. O contraste de 49,2% frente a Aqua observado é específico desse domínio. No diagnóstico circular sobre suporte idêntico, o MAPE de 76,0630% do VIIRS ajustado passou a 38,0315% ao incluir a referência Aqua na média. Na avaliação fora do ano retido, a regularização na união obteve WAPE mensal de 21,98% e anual de 15,07%. [Auditoria](../VALIDATION_REPORT.md) · [Decomposição](../FUSION_BIAS_ANALYSIS.md)

No piloto exploratório de 24/08/2024 a 65°, a contagem Aqua passou de 32 centros para 67 ao desvincular sua retenção da propriedade da área. No cenário principal a 55°, essa dupla ficou sem suporte conjunto. Nas seis duplas utilizáveis, três tiveram positivos estritos. Na passagem de 26/08/2019, duas codetecções entraram no suporte próprio com M13 sinalizada. O suporte fixo conservou a contagem VIIRS e o Jaccard estrito. O Jaccard agrupado da amostra passou de 1/3 em suporte próprio M13 para 0 no suporte fixo. [Centro e área](../FOOTPRINT_GEOMETRY_AUDIT.md) · [Resultados por dupla](../STRATIFIED_ORBITAL_SAMPLE_REPORT.md) · [QA em suporte fixo](../QA_FIXED_SUPPORT_COMPARISON.md)

## Discussão

Separar aquisição, suporte e regras de fusão é necessário para interpretar métricas que mudam com QA. A decomposição por exclusividade explica o contraste aritmético no índice. A redução após usar zeros válidos mede a mudança de regra no suporte comparável. A contribuição causal da cobertura para a diferença histórica continua indeterminada. O controle instrumental sustenta a escala dimensional dos footprints. A posição geográfica precisa dos cantos permanece por verificar. [Robustez da fusão](../FUSION_ROBUSTNESS_REPORT.md) · [Controle de geometria](../FOOTPRINT_INDEPENDENT_VALIDATION.md)

## Limitações

As sete duplas constituem amostra intencional, com poucas células positivas e dependência espacial. Nenhuma atingiu o mínimo de dez centros de cada sensor no suporte fixo para considerar nova calibração. As métricas medem concordância entre produtos. Equivalentes Aqua são unidades do índice e não identificam incêndios físicos nem hectares queimados. A transferência da calibração, a acurácia e a interpretação radiométrica de FRP exigem referência independente.

## Conclusão

Mantemos a versão histórica como índice regional de atividade registrada e a fusão condicionada à cobertura como experimental. O contraste de QA precisa declarar o suporte. A próxima evidência científica pode combinar observações independentes de presença, passes retidos e avaliação dos contornos dos footprints.

## Disponibilidade de dados e código

O repositório de trabalho contém scripts, extratos FIRMS, manifests, checksums e resultados derivados. Os binários são produtos NASA com identificadores definidos nos manifests e foram mantidos localmente. Confirmar endereço público, versão identificável e termos de distribuição do código durante a revisão por autores. [Inventário](../SCIENTIFIC_ARTIFACT_INDEX.md) · [Proveniência](../DATA_PROVENANCE.md) · [Reprodução](../REPRODUCIBILITY.md)

## Referências

- NASA FIRMS. *Active Fire Data* e *Area API*. [Produtos](https://firms.modaps.eosdis.nasa.gov/content/active_fire/) · [API](https://firms.modaps.eosdis.nasa.gov/api/area/)
- Giglio, L. e Justice, C. (2021). *MODIS/Aqua Thermal Anomalies/Fire 5-Min L2 Swath 1km V061*. NASA LP DAAC. [DOI](https://doi.org/10.5067/MODIS/MYD14.061)
- NASA LAADS DAAC. *MODIS Geolocation C6.1*. [Especificação](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD03)
- NASA LP DAAC. *VIIRS/NPP Active Fires 6-Min L2 Swath 375m V002*. [DOI](https://doi.org/10.5067/VIIRS/VNP14IMG.002)
- NASA LAADS DAAC. *VIIRS/NPP Terrain Corrected Geolocation 375 m V002*. [DOI](https://doi.org/10.5067/VIIRS/VNP03IMG.002)
- NASA/Land SIPS. *Collection 2 VIIRS 375 m Active Fire Product User Guide*, v1.2. [Guia](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf)
- NOAA JPSS. *VIIRS Imagery ATBD*, §3.2.4. [ATBD](https://www.star.nesdis.noaa.gov/jpss/documents/ATBD/D0001-M01-S01-008_JPSS_ATBD_VIIRS-Imagery_E.pdf)
- NASA MODIS Dark Target. *ATBD Products*. [Geometria instrumental](https://darktarget.gsfc.nasa.gov/atbd-products)
- H3. *Tables of Cell Statistics Across Resolutions*. [Estatísticas H3](https://h3geo.org/docs/core-library/restable/)
