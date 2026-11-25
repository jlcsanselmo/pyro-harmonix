# Fusão condicionada à cobertura válida

## Resultado e recomendação

O piloto processou os quatro grânulos reais de 24/08/2024. O limite angular pré-definido de **55°** deixou Aqua sem área válida na caixa. Assim, as métricas pareadas desse cenário ficaram indefinidas. Os cenários de **60° e 65°** são sensibilidades exploratórias após identificar a limitação angular. O fator VIIRS foi mantido como referência histórica e os métodos de produção permanecem os da fase 2. [Cobertura e procedência](REAL_OBSERVATION_COVERAGE_REPORT.md) · [Baseline da segunda etapa](FUSION_BIAS_ANALYSIS.md)

## Comparação implementada

| Método | Cálculo experimental no conjunto de grânulos |
| --- | --- |
| Aqua observado | Centros nativos de fogo aprovados, atribuídos uma vez pela célula que contém o centro |
| VIIRS bruto | Mesmo critério na resolução nativa de S-NPP |
| VIIRS calibrado | Contagem nativa multiplicada pelo fator mensal da fase 2, com checksum da fonte registrado |
| Zero-filled histórico | Média de Aqua e S-NPP ajustado nos estratos positivos da dupla, com silêncio preenchido por zero aritmético |
| Condicionado aos registros | Média se ambos registram centros de fogo; contribuição integral se só um registra |
| Condicionado à cobertura | Média dos centros Aqua e VIIRS ajustados **na interseção válida, pareada e qualificada por área e tempo** |

A comparação experimental usa contagem de centros nativos e o fator regional histórico, sem reamostrar máscaras em um grid de valores. O fator foi ajustado com o arquivo FIRMS em uma escala diferente de suporte observacional. Seu uso aqui é uma referência comparativa preliminar. Não se aplica calibração nova a FRP nesta etapa.

A interseção deve preencher ao menos 80% da célula de referência na análise principal. Os centros de fogo contam uma vez, inclusive quando o footprint cruza peças de interseção. Verifica-se se o centro nativo está dentro do suporte comum. Um zero significa ausência de detecção naquela parte observada. Células abaixo do limiar ficam nulas para o método de cobertura. A área avaliada pode ser menor que a célula inteira na borda da caixa. Podem ser executados cenários de 60% e 90% com `--minimum-joint-fraction`.

O JSON compara totais das cinco referências na região e nas células elegíveis, apresenta a fusão na área comum e separa células sem positivo, codetecções e registros exclusivos de Aqua ou VIIRS. Uma diferença entre o total nativo e o suporte comum também pode refletir redução de área amostrada. Contadores registram centros de fogo em que o outro sensor classificou o local como terra observada sem fogo. Esses casos permitem investigar a hipótese do silêncio em observação válida. Eles incluem efeitos de horário, footprint, localização de fogo subpixel e limiar do algoritmo. O outro sensor pode ter passado minutos antes ou depois. A decomposição por um dia não quantifica a contribuição causal de cobertura à variação histórica de 49,2%.

A execução com arquivos verificados produziu `coverage-cells.csv`, `coverage.geojson`, `summary.json` e os PNGs `coverage-maps.png` e `fusion-comparison.png`. As figuras mostram as áreas válidas, fração conjunta, detecções nativas, estimativa experimental e sensibilidade à tolerância temporal. Os mapas e as tabelas da execução real estão identificados pelo limite angular. As métricas pareadas ficam nulas quando a área comum não atinge o limiar.

## Expansão controlada e fonte externa

- Só expandir após revisar as geometrias da primeira dupla, verificar ordem de grandeza da área e comparar amostras de footprints com a geometria documentada. Testar, antes do desenho final, a sensibilidade ao ângulo de visada e a limiares de área comum.
- Definir seis datas candidatas, uma por ano de 2019–2024, com janelas fora de agosto e pares diurno/noturno. Usar atividade registrada apenas para estratificar a seleção de dias altos e baixos. Contabilizar também datas sem aquisição utilizável. A dupla diurna piloto estima cerca de 186 MB e a noturna cerca de 200 MB. Seis pares ficam em cerca de 1,1–1,2 GB. Usar ambos os turnos em seis datas pode passar de 2 GB. Reservar inicialmente 2–3 GiB de RAM por processamento de uma dupla. O tempo e o pico de memória em dados reais devem ser medidos no primeiro processamento. Solicitar autorização antes da expansão.
- NOAA-20 e NOAA-21 são candidatos a **transferência entre plataformas** e concordância entre produtos. O catálogo da segunda etapa já identificou aquisições em 24/08/2024. Para estimar concordância há dependência de suas máscaras, geolocalização e evidência de suporte válido compatível. A confirmação do comportamento de detecção em campo requer uma referência com desenho e cobertura independentes.
- Em MCD64A1, o tile de agosto registrado no protocolo serve para **concordância espacial com um produto derivado em parte de MODIS**. MapBiomas Fogo fornece um desfecho Landsat distinto para associação espacial mensal. O acesso por Range ao link nacional de 2024 candidato retornou 403. A alternativa oficial de recorte usa a plataforma Google Earth Engine. Um raster regional recortado é o insumo indicado para uma futura comparação de presença e área queimada. O ensaio de associação com área queimada aguarda um recorte adequado. [Protocolo externo](EXTERNAL_VALIDATION_PROTOCOL.md) · [Recortes oficiais MapBiomas](https://brasil.mapbiomas.org/downloads/baixe-mapas-recortados-geotiff-via-google-earth-engine/)

## Prova complementar com NOAA-20 e NOAA-21

Executamos duas consultas FIRMS Standard Processing para a mesma caixa e dia. NOAA-20 retornou 636 registros e NOAA-21, 652, incluindo os turnos. O ensaio agrupou as linhas diurnas por horário UTC e célula H3 7 e comparou a interseção e a união dos conjuntos positivos. A cada linha do resultado, um registro exclusivo pode decorrer de cobertura, horário, sensibilidade ou diferença de localização. O denominador do Jaccard é a união de células com detecção registrada. A cobertura dos demais locais permanece desconhecida. [API FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/) · [Resultados e checksums](data/phase3/noaa-positive-overlap-2024-08-24.json)

| Referência | Comparador UTC | Diferença temporal | Células positivas em comum | Jaccard dos positivos |
| --- | --- | ---: | ---: | ---: |
| Aqua 17:00 | NOAA-20 16:58 | 2 min | 32 | 0,356 |
| Aqua 17:00 | NOAA-21 16:09 | 51 min | 29 | 0,354 |
| Aqua 17:00 | NOAA-21 17:49 | 49 min | 6 | 0,102 |
| S-NPP 16:34 | NOAA-20 16:58 | 24 min | 67 | 0,827 |
| S-NPP 16:34 | NOAA-21 16:09 | 25 min | 57 | 0,713 |
| S-NPP 16:34 | NOAA-21 17:49 | 75 min | 11 | 0,138 |

Com tolerância de 30 min, entram um par de Aqua e dois de S-NPP. A 60 min, entram mais dois de Aqua. A 90 min, entram os seis, inclusive S-NPP ↔ NOAA-21 às 17:49. A sobreposição de S-NPP com NOAA-20 foi maior que a de Aqua com NOAA-20 apesar do maior intervalo. Diferenças de plataforma, resolução, geometria e dinâmica do fogo podem contribuir. Este resultado é descritivo e não estima sensibilidade, especificidade ou acurácia.

![Comparação de registros positivos NOAA-20/21 com Aqua e S-NPP.](assets/noaa-positive-overlap.png)

Reprodução no worker com a configuração FIRMS já existente. O script registra o SHA-256 das respostas e produz exclusivamente JSON agregado.

```powershell
docker compose run --rm --no-deps -v "${PWD}/backend:/app:ro" -v "${PWD}/docs/data/raw:/raw:ro" -v "${PWD}/docs/data/phase3:/reports" firms-sync python orbital_external.py /raw /reports/noaa-positive-overlap-2024-08-24.json
python backend/plot_orbital_pilot.py docs/assets --external-json docs/data/phase3/noaa-positive-overlap-2024-08-24.json
```
