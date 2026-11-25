# Proveniência dos dados e resultados

| Origem | Dados e escopo | Controle de integridade |
| --- | --- | --- |
| FIRMS Standard Processing | `MODIS_SP` e `VIIRS_SNPP_SP`, 12 extratos de 2019–2024 na caixa regional | Arquivos gzip locais e SHA-256 em `provenance.provided_sample_sha256` do [JSON de auditoria](data/scientific-audit.json). Terra pode estar na ingestão, enquanto a série comparável usa MODIS-Aqua. |
| Histórico WebGIS | CSV de Ribeirão Preto H3 8 pré-calibração, séries congeladas Altinópolis–Pitangueiras H3 7 zero-filled e janela de agosto | Arquivos de [reprodução histórica](SCIENTIFIC_ARTIFACT_INDEX.md). O recorte do export e o da caixa bruta de ajuste têm diferenças documentadas. |
| Ciência orbital | MYD14/MYD03 C6.1, VNP14IMG/VNP03IMG C2 e catálogo CMR | Manifests por dupla com produto, coleção, arquivo, hora UTC, bytes, provedor e SHA-256. Assinaturas HDF4 e HDF5 e cabeçalhos conferidos. |
| Imagens contextuais | 24/08/2024 e animação de agosto, Worldview/GIBS | Crédito NASA GIBS/ESDIS. Artefatos de comunicação preservados em `docs/assets/`. |
| Comparadores externos | FIRMS NOAA-20/21, MapBiomas Fogo, MCD64A1 e possíveis observações de campo | O teste NOAA existente usa apenas registros positivos. Critérios e grau de independência estão no [protocolo externo](EXTERNAL_VALIDATION_PROTOCOL.md). |

O CMR forneceu metadados e candidatos. Os quatro produtos de cada dupla foram obtidos por rotas oficiais LAADS DAAC e LP DAAC do Earthdata Cloud, com binários conservados em `.orbital-data/`. A versão publicada guarda resultados, manifests e hashes em vez do conteúdo HDF/NetCDF. O token Earthdata fica fora do repositório. A chave FIRMS de operação fica em `.env` local. O exemplo de variáveis tem campo FIRMS vazio e somente valores ilustrativos.

### Manifestos e localizadores

- [Piloto 24/08/2024, fase 3](data/phase3/orbital-2024-08-24/granule-manifest.json) e [metadados internos](data/phase3/orbital-2024-08-24/embedded-metadata.json).
- [Piloto 26/08/2019, fase 4](data/phase4/2019-08-26/granule-manifest.json) e [procedência revisitada de 2024](data/phase4/2024-08-24/granule-manifest.json).
- [Amostra congelada](data/phase5/sample-plan.json), [recibos de aquisição](data/phase5/acquisition.json) e [recibos de processamento](data/phase5/processing.json). Diretórios por data trazem manifesto, cabeçalhos, métricas, células e conferência FIRMS.
- [Dicionário com versão e contexto por métrica](data/final-scientific-summary.json) e [inventário completo](SCIENTIFIC_ARTIFACT_INDEX.md).

[Coleção NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/content/active_fire/) · [CMR](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) · [MYD14](https://doi.org/10.5067/MODIS/MYD14.061) · [VNP14IMG](https://doi.org/10.5067/VIIRS/VNP14IMG.002)
