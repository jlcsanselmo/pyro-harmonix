# Cobertura orbital com observações reais

## Execução com grânulos reais

A dupla diurna de 24/08/2024 foi processada com quatro grânulos autenticados. O lote totaliza **194.555.073 bytes (185,54 MiB)**. Verificamos as assinaturas HDF4 ou HDF5, a transferência integral, o tamanho, os SHA-256 e os metadados internos de aquisição. A máscara e a geolocalização Aqua compartilham a grade **2.040 × 1.354** e começam às **17:00 UTC**. Os dois produtos S-NPP compartilham a grade **6.464 × 6.400** e começam às **16:30 UTC**. As matrizes e os relógios de varredura foram lidos dos arquivos, além da conferência do nome de catálogo. [Manifesto verificado](data/phase3/orbital-2024-08-24/granule-manifest.json) · [Metadados internos](data/phase3/orbital-2024-08-24/embedded-metadata.json)

A resposta HTML observada sem credencial pertencia ao fluxo de acesso. Com o token local, o caminho legado do LAADS ainda redirecionou ao login. A aquisição funcionou nos endereços oficiais de nuvem publicados para os mesmos arquivos. O LP DAAC Earthdata Cloud forneceu as duas máscaras, e o LAADS Earthdata Cloud forneceu as geolocalizações confirmadas pelo CMR. O cliente enviou Bearer apenas ao provedor inicial de cada arquivo, manteve cookies em memória e seguiu redirecionamentos HTTPS para destinos verificados sem encaminhar o Bearer ao CDN. O programa valida o corpo binário antes da gravação. [Estado e rotas em JSON](data/phase3/access-status.json) · [Guia LAADS para token Earthdata](https://ladsweb.modaps.eosdis.nasa.gov/learn/download-files-using-edl-tokens/) · [Acesso LP DAAC](https://github.com/nasa/LPDAAC-Data-Resources/blob/main/guides/NASA_LPDAAC_Data_Access_Guide.md)

## Autenticação e execução

1. Acesse o [perfil Earthdata Login](https://urs.earthdata.nasa.gov/profile), autentique-se e use **Generate Token** e **Show Token**. Se a conta pedir autorização para o LAADS, autorize o aplicativo no portal ou abra um link de dados enquanto estiver autenticado.
2. Em PowerShell, salve o token fora do repositório por um prompt oculto. Alternativamente, disponibilize `EARTHDATA_TOKEN` no ambiente do processo, ou aponte `PYRO_EARTHDATA_TOKEN_FILE` para um arquivo privado já criado.

```powershell
$dir = Join-Path $env:LOCALAPPDATA 'PyroHarmonix'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$secret = Read-Host 'Token Earthdata' -AsSecureString
[IO.File]::WriteAllText((Join-Path $dir 'earthdata-token'), [Net.NetworkCredential]::new('', $secret).Password)
Remove-Variable secret
```

3. Execute a aquisição limitada na raiz do repositório. Se preferir o download pelo navegador, coloque os quatro arquivos do plano em `.orbital-data/nasa` e acrescente `--local-only`.

```powershell
python backend/api/services/orbital_download.py docs/data/phase3/2024-08-24-granule-plan.json .orbital-data/nasa
```

4. Execute o processamento em contêiner. O token fica com o processo de aquisição no host. O contêiner recebe apenas os arquivos científicos e o manifesto. Os pacotes opcionais de análise são instalados no contêiner descartável.

```powershell
docker compose run --rm --no-deps -v "${PWD}/backend:/app:ro" -v "${PWD}/docs:/reference:ro" -v "${PWD}/.orbital-data:/work" api sh -c 'set -e; pip install --target /tmp/orbital -r requirements-orbital.txt; export PYTHONPATH=/tmp/orbital; python orbital_pilot.py /work/nasa/granule-manifest.json /reference/data/phase2/fusion-study.json /work/output; python plot_orbital_pilot.py /work/output'
```

A validação dos leitores e o processamento real foram executados em Linux no Docker. Os testes de regressão com fixtures sintéticas verificam o software separadamente. Neste host, o wheel Windows do `pyhdf` falhou ao carregar uma DLL ao importar HDF4. O diretório de dados experimental é ignorado pelo Git.

## Par regional de 24/08/2024

| Produto | Coleção e formato | Início UTC | Resolução nominal | Função |
| --- | --- | --- | --- | --- |
| MYD14 | 061, HDF4/HDF-EOS | 17:00 | 1 km | Máscara de fogo e QA no swath Aqua |
| MYD03 | 061, HDF4/HDF-EOS | 17:00 | 1 km | Lat/lon, ângulos, QA geométrico e tempo de varredura |
| VNP14IMG | 002, NetCDF4/HDF5 | 16:30 | 375 m | Máscara de fogo e QA no swath S-NPP |
| VNP03IMG | 002, NetCDF4/HDF5 | 16:30 | 375 m | Lat/lon, ângulos, QA geométrico e tempo de varredura |

O plano corresponde ao par diurno, com cerca de 186 MB em metadados. Cada máscara é pareada com o arquivo de geolocalização da mesma plataforma, coleção e data/hora. O leitor exige matrizes de mesma forma, quantidade consistente de varreduras e tempo compatível com o manifesto. Todos esses controles passaram nesta execução. [Plano dos quatro grânulos](data/phase3/2024-08-24-granule-plan.json) · [MYD14](https://doi.org/10.5067/MODIS/MYD14.061) · [MODIS Geolocation](https://ladsweb.modaps.eosdis.nasa.gov/filespec/MODIS/61/MOD03) · [Guia VIIRS C2](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf) · [VNP03IMG](https://doi.org/10.5067/VIIRS/VNP03IMG.002)

## Área, QA e classes

| Classes de máscara | Interpretação neste piloto |
| --- | --- |
| 0–2 | Entrada faltante ou processamento inadequado. Em VIIRS, a classe 1 é descarte bow-tie e a 2 sinaliza reflexo solar |
| 3 | Água, excluída do denominador de validade terrestre |
| 4 | Nuvem, quantificada separadamente onde a geometria é aceitável |
| 5 | Terra válida sem fogo detectado, quando atende ao QA |
| 6 | Classe indeterminada |
| 7–9 | Fogo detectado com confiança baixa, nominal ou alta, quando atende ao QA |

O piloto exige QA geométrico nominal, ângulo zenital do sensor até 55° e classificação terrestre para fogo e terra sem detecção. Em Aqua usa `gflags` e bits 0–1 do QA de fogo. Em S-NPP usa `quality_flag`, `land_water_mask` e bits 0–6 do QA de fogo. A classe 1 e o bit 22 de redundância VIIRS são excluídos. Uma classe sem qualidade suficiente não autoriza zero para toda a célula. [Guia MODIS](https://landweb.modaps.eosdis.nasa.gov/data/userguide/MODIS_C6_Fire_User_Guide_C.pdf) · [Guia VIIRS C2](https://www.earthdata.nasa.gov/s3fs-public/2024-07/VIIRS_C2_AF-375m_User_Guide_1.0.pdf)

Os footprints são aproximados por meios passos entre centros vizinhos dentro da mesma varredura. O piloto projeta os vértices em Lambert azimutal equivalente local, recorta-os à caixa e intersecta-os com H3 7. Em possíveis sobreposições do mesmo sensor, prioriza a observação mais próxima do nadir e conserva as áreas como partes disjuntas. Uma geometria ausente dentro de um envelope orbital conservador permanece desconhecida. Fora do envelope é reportado separadamente. O envelope aproximado, a topografia e as bordas de varredura limitam a precisão da cobertura. Na execução real, a caixa geográfica foi segmentada antes de projetar os limites. As operações de interseção e diferença usam precisão comum de 1 cm no plano projetado e conservam apenas superfícies. Essa correção resolveu excesso de área por sobreposição numérica detectado em dois hexágonos Aqua na primeira conferência. A taxa de retenção dos centros nos footprints reconstruídos deve ser verificada em outras geometrias antes da expansão.

O tempo vem do início da varredura TAI93, convertido para UTC para 2019–2024. O teste principal usa até 60 min, com sensibilidades em 30, 45 e 90 min. A interseção também exige iluminação concordante pelo ângulo solar. O denominador é a área inteira da célula e a área efetivamente avaliada é publicada em separado. [Tempo MODIS](https://atmosphere-imager.gsfc.nasa.gov/issues/cloud) · [Guia de nível 1 VIIRS](https://oceandata.sci.gsfc.nasa.gov/files/resources/docs/technical/VIIRS_Level-1_DataProductUsersGuide.pdf)


## Cobertura medida em H3 resolução 7

A caixa atravessa **1.175 células** e soma **5.855,67 km²** avaliados. Aqua apresentou ângulos zenitais de **59,03° a 63,16°** na região. S-NPP apresentou **22,82° a 31,52°**. O limite de 55°, definido antes do processamento, excluiu todos os footprints válidos de Aqua na caixa. Após observar esse resultado, repetimos a análise com 60° e 65°, mantendo os demais filtros.

| Limite zenital | Aqua válido (km²) | S-NPP válido (km²) | Interseção válida pareada (km²) | Células com ≥80% de suporte comum |
| --- | ---: | ---: | ---: | ---: |
| 55° | 0,00 | 5.568,57 | 0,00 | 0 |
| 60° | 1.062,92 | 5.568,57 | 981,88 | 148 |
| 65° | 5.627,63 | 5.568,57 | 5.380,48 | 910 |

A área de interseção soma as partes comuns de todas as células e a última coluna aplica o limiar de 80% à célula inteira. Os horários regionais das varreduras foram 17:00:28,586–17:00:37,449 UTC para Aqua e 16:34:45,976–16:34:56,652 UTC para S-NPP. Os extremos implicam separação de 25 min 32 s a 25 min 51 s. As tolerâncias de **30, 45, 60 e 90 minutos** produziram as mesmas áreas, classes e métricas em cada cenário angular. [Horários regionais](data/phase3/orbital-2024-08-24/regional-scan-times.json) · [Comparativo das 12 combinações](data/phase3/orbital-2024-08-24/comparacao.csv)

A área desconhecida foi de 2,49 km² em Aqua e 3,22 km² em S-NPP em cada cenário. A 65°, Aqua teve 79,54 km² sem observação válida e 146,00 km² de nuvens, além de 5.406,56 km² de terra observada sem detecção. S-NPP teve 222,33 km² sem observação válida, 61,55 km² de nuvens e 5.552,92 km² observados sem detecção em todos os cenários. Os CSVs registram separadamente essas frações e a classe de cada sensor por célula. Uma célula pode conter tanto área desconhecida quanto inválida. A checagem da soma das áreas por célula encontrou desvio máximo de 0,00035 ponto percentual. [Áreas por estado](data/phase3/orbital-2024-08-24/areas-by-coverage-state.json)

As máscaras brutas continham 67 centros Aqua e 363 S-NPP classificados como fogo na caixa. A 65°, os filtros de entrada mantiveram 67 Aqua e 82 S-NPP candidatos antes da resolução de footprints sobrepostos. Entre os 362 candidatos S-NPP com terra, geolocalização nominal e sem descarte bow-tie, 280 apresentaram o bit 6 do QA, relacionado a qualidade não nominal em M13. Depois da atribuição geométrica, as contagens regionais foram 32 Aqua e 80 S-NPP. A retenção de Aqua é sensível à geometria aproximada em ângulos altos. Recomenda-se revisar amostras dos footprints e o efeito das regras de QA antes de interpretar as diferenças como desempenho dos sensores. [Diagnóstico das máscaras e do QA](data/phase3/orbital-2024-08-24/qa-diagnostic.json)

| Cenário | Mapa | Tabela por H3 | Geometrias H3 | Resumo |
| --- | --- | --- | --- | --- |
| 55° | [PNG](assets/orbital-coverage-maps-z55.png) | [CSV.gz](data/phase3/orbital-2024-08-24/coverage-cells-z55.csv.gz) | [GeoJSON.gz](data/phase3/orbital-2024-08-24/coverage-z55.geojson.gz) | [JSON](data/phase3/orbital-2024-08-24/summary-z55.json) |
| 60° | [PNG](assets/orbital-coverage-maps-z60.png) | [CSV.gz](data/phase3/orbital-2024-08-24/coverage-cells-z60.csv.gz) | [GeoJSON.gz](data/phase3/orbital-2024-08-24/coverage-z60.geojson.gz) | [JSON](data/phase3/orbital-2024-08-24/summary-z60.json) |
| 65° | [PNG](assets/orbital-coverage-maps-z65.png) | [CSV.gz](data/phase3/orbital-2024-08-24/coverage-cells-z65.csv.gz) | [GeoJSON.gz](data/phase3/orbital-2024-08-24/coverage-z65.geojson.gz) | [JSON](data/phase3/orbital-2024-08-24/summary-z65.json) |

O piloto real analisou uma única dupla diurna. As métricas publicadas nesta seção vieram dos grânulos científicos. Os cenários sintéticos usados nos testes automatizados servem à verificação da implementação. A suíte completa passou com 94 testes no PostgreSQL. [Comparação das regras de fusão](COVERAGE_AWARE_FUSION_REPORT.md)
