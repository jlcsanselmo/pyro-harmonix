# Cobertura de observação MODIS e VIIRS

## Produtos e processamento

| Produto | Dados e período aplicável ao estudo | Uso |
| --- | --- | --- |
| MOD14 e MYD14 C6.1 | MODIS Terra e Aqua, swath L2, 5 min, 1 km nominal, HDF4/HDF-EOS. O arquivo Terra antecede Aqua, que tem detecções regulares a partir de julho de 2002. MYD14 cobre os anos 2019–2024 da avaliação. | Máscara de fogo e QA para cada posição no swath. Usar MYD14 na comparação com Aqua. |
| MOD03 e MYD03 C6.1 | Geolocalização Terra e Aqua, 1 km, HDF4, mesmos instantes das passagens; vértices estimados a partir da geometria e atenção ao efeito de borda de varredura. | Coordenadas, geometria e ângulos da observação. Relacionar pelo satélite, dia juliano e hora de aquisição. |
| VNP14IMG C2 | VIIRS S-NPP, swath L2 de 6 min, 375 m nominal, NetCDF4/HDF5. Guia indica 20/01/2012 como início efetivo. | Máscara de fogo, QA e tabela de pixels de fogo. Usar níveis de confiança como análise de sensibilidade. |
| VNP03IMG C2 | Geolocalização VIIRS no mesmo grid de imagem, 375 m nominal; NetCDF4. | Geolocalização das máscaras, ângulo zenital solar e do sensor, geometria de faixa, controles de qualidade. |
| MYD35_L2 e CLDMSK_L2_VIIRS_SNPP | Máscaras de nuvens MODIS Aqua (camadas a 1 km e 250 m) e VIIRS S-NPP (750 m nominal). | Conferência complementar de nuvens. Manter a classificação primária da máscara de fogo e documentar qualquer regra de combinação. |

Arquivos de nível 2 preservam o instante e o swath. Composições diárias podem ajudar na triagem, mas misturam passagens. Ler HDF4 com GDAL compatível e NetCDF4 com GDAL ou netCDF4, observando dimensões, valores de preenchimento e convenções de QA. O tamanho nominal do pixel não deve ser tratado como área constante fora do nadir. O acesso é gratuito, com Earthdata Login para os arquivos protegidos. A política da NASA prevê divulgação aberta e condições no catálogo, com atribuição e citação de produto. [MYD14 C6.1](https://doi.org/10.5067/MODIS/MYD14.061) · [Guia MODIS](https://landweb.modaps.eosdis.nasa.gov/data/userguide/MODIS_C6_Fire_User_Guide_C.pdf) · [Guia VIIRS C2](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf) · [Geolocalização VIIRS](https://doi.org/10.5067/VIIRS/VNP03IMG.002) · [Máscaras de nuvens](https://ladsweb.modaps.eosdis.nasa.gov/learn/modis-to-viirs-transition/MODIS-VIIRS_Transition.pdf) · [Política LAADS](https://ladsweb.modaps.eosdis.nasa.gov/learn/)

## Busca limitada em Altinópolis–Pitangueiras

A consulta ao CMR usou a caixa W −48,433, S −21,215243, E −47,181633, N −20,8087035, com intervalo UTC de 24/08/2024 e limite de quinze metadados por produto. Cada busca de máscara retornou dois grânulos. Os catálogos LAADS confirmaram os quatro grânulos de geolocalização no dia juliano 237.

| Sensor | Horas UTC dos grânulos | Tamanhos das máscaras, metadados CMR | Tamanhos da geolocalização, LAADS |
| --- | --- | --- | --- |
| Aqua | 04:50 e 17:00 | 0,25 e 0,40 na unidade de tamanho do catálogo | 30,86 e 33,36 MB |
| S-NPP | 04:00 e 16:30 | 0,89 e 2,30 na unidade de tamanho do catálogo | 168,11 e 149,48 MB |

A dupla diurna de 16:30–17:00 exige cerca de **186 MB** de máscaras e geolocalização. A dupla de 04:00–04:50 fica perto de **200 MB**. As diferenças nominais de 30 e 50 min devem ser refinadas com o horário local das linhas da varredura. Em metadados, a caixa do grânulo é indício de interseção, com cobertura local a verificar pelos pixels. Dois pedidos HEAD sem login aos assets de máscaras retornaram HTTP 403. O ensaio executado nesta etapa abrangeu metadados. O processamento regional de conteúdo aguarda acesso autenticado aos quatro arquivos de uma dupla. [API CMR](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) · [MYD03 no LAADS](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/61/MYD03/2024/237/) · [VNP03IMG no LAADS](https://ladsweb.modaps.eosdis.nasa.gov/archive/allData/5200/VNP03IMG/2024/237/)

Para repetir a consulta use `/search/granules.json` com `short_name=MYD14&version=061` ou `short_name=VNP14IMG&version=002`, `bounding_box=-48.433,-21.215243,-47.181633,-20.8087035`, `temporal=2024-08-24T00:00:00Z,2024-08-24T23:59:59Z` e `page_size=15`. Relacione geolocalização e máscara pelo início de aquisição no nome do grânulo.

## Piloto local

O comando `study_coverage` classifica e agrega evidência produzida pela interseção de máscaras geolocalizadas. As classes 7–9 representam fogo detectado, 5 superfície terrestre observada sem fogo detectado e 4 nuvem. O piloto exclui água, classes 0–3, QA reprovado e redundância identificada. A classe 6, falta de QA e falta de informação de faixa são desconhecidas. Fora da faixa exige geometria comprovada. Pixels encobertos e desconhecidos ficam fora do denominador de área válida conjunta. A fração desconhecida inclui porções da célula sem geometria de entrada.

1. Fixar um par de passagens sobre a mesma caixa. Converter a geometria de pixels de cada sensor para uma projeção de área equivalente. Fazer união espacial de duplicatas, retirar pixels redundantes e intersectar os dois swaths com a malha H3 7, formando peças disjuntas. Guardar coleção, IDs dos grânulos, horários locais, QA, versão do leitor e parâmetros.
2. Exportar uma linha por peça com cabeçalho `pair_id,cell,piece_id,fraction,aqua_mask,aqua_in_swath,aqua_qa_ok,snpp_mask,snpp_in_swath,snpp_qa_ok`. `fraction` é a área da peça dividida pela área da célula inteira, com soma ≤ 1 para cada par e célula. Máscara em branco indica ausência de valor. Indicadores de faixa e QA recebem `1`, `0` ou vazio. O QA deve incluir geolocalização e regra de duplicatas e pode ser refinado pelas máscaras de nuvens complementares. O comando verifica unicidade de IDs e soma de frações. A construção das geometrias e verificação de sobreposição ocorrem antes do CSV.
3. Executar `python manage.py study_coverage caminho/pecas.csv --minimum-joint-fraction 0.8`. O resultado contém frações por estado, área conjunta válida e presença em cada sensor no suporte comum. Repetir com 0,6 e 0,9 como análise de sensibilidade. O limite 0,8 é um parâmetro de desenho, ainda sem calibração empírica.
4. Comparar a detecção binária somente na área conjunta válida. Uma presença falsa no resultado significa ausência de detecção dentro do suporte observado. Áreas externas a esse suporte ficam desconhecidas. O piloto trabalha com fração de área e presença; contagem de pixels nativos exigirá identificar pixels únicos e definir uma regra para os que cruzam fronteiras.

Os testes da prova de conceito usam dados sintéticos identificados para verificar estados e o limiar. Nenhuma fração real ou estimativa de fusão condicionada à cobertura foi inferida dos CSVs FIRMS.

A execução posterior com os quatro grânulos autenticados está no [relatório de cobertura real](REAL_OBSERVATION_COVERAGE_REPORT.md).
