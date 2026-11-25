# Compatibilidade entre a calibração FIRMS e o domínio orbital

## Pareamento por grânulo

A comparação usou os CSVs locais de processamento padrão FIRMS e os centros da máscara de cada grânulo, antes do QA de presença e da partição espacial. Selecionamos a mesma caixa, data, plataforma, iluminação diurna e a janela da aquisição em minutos UTC. Em seguida, fizemos correspondência espacial um a um em coordenadas projetadas, com limiar principal de 100 m e controles a 10 e 500 m. O relógio regional do grânulo vem do início da varredura. O CSV FIRMS registra HHMM. A diferença derivada tem resolução limitada por essa representação. [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) · [Protocolo do produto VIIRS C2 v1.2, p. 8](https://ladsweb.modaps.eosdis.nasa.gov/archive/Document%20Archive/Science%20Data%20Product%20Documentation/VIIRS_C2_AF-375m_User_Guide_1.2.pdf#page=8)

| Dupla | Sensor | FIRMS | Máscara | Pareados a 10/100/500 m | Distância mínima–máxima | Segundos desde o minuto FIRMS |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 24/08/2024 | Aqua | 67 | 67 | 67 / 67 / 67 | 0,67–7,52 m | 30,06–35,97 s |
| 24/08/2024 | S-NPP | 363 | 363 | 363 / 363 / 363 | 0,03–0,74 m | 47,76–53,09 s |
| 26/08/2019 | Aqua | 4 | 4 | 4 / 4 / 4 | 2,54–3,44 m | 9,01–10,49 s |
| 26/08/2019 | S-NPP | 9 | 9 | 9 / 9 / 9 | 0,17–0,50 m | 31,21–38,33 s |

Todas as linhas FIRMS do recorte tinham tipo 0 e não houve coincidências exatas de coordenadas a cinco casas decimais. As classes VIIRS 7, 8 e 9 corresponderam a l, n e h. Em Aqua, FIRMS traz confiança numérica e a máscara usa classes. Em 2024, Aqua teve 26 centros de classe 8 e 41 da classe 9. As versões declaradas no CSV Aqua foram 61.03 em 2024 e 6.03 em 2019, com paridade pontual neste recorte inclusive em 2019 frente ao grânulo Collection 6.1. A diferença de versão documental merece checagem caso o domínio seja ampliado. [Correspondência e SHA-256 em 2024](data/phase4/2024-08-24/firms-compatibility.json) · [Correspondência e SHA-256 em 2019](data/phase4/2019-08-26/firms-compatibility.json)

## Consequência para o fator

A reprodução dos centros brutos mostra forte compatibilidade de geolocalização, confiança e janela de aquisição no recorte dos dois dias. A compatibilidade do **fator mensal** exige suporte e estágio de filtragem comparáveis. O estudo histórico ajusta contagens FIRMS em estratos de célula e turno na união dos registros positivos. O piloto orbital usa máscaras e QA explícitos, identifica zeros em área observada, restringe centros à interseção e pareia horários de varredura. A resolução nativa também difere, 1 km nominal em Aqua e 375 m nominal em VIIRS, com crescimento fora do nadir. Um mesmo fogo pode produzir diferentes quantidades de pixels de cada resolução. O fator de agosto foi conservado em todos os tratamentos como referência e nenhuma recalibração foi ajustada às duas duplas. [Estudo da fase 2](FUSION_BIAS_ANALYSIS.md) · [Métricas no suporte comum da fase 4](SECOND_ORBITAL_PILOT_REPORT.md)

Os dados mostram por que os dois domínios divergem após a seleção. Em 2024, a correspondência FIRMS inclui todos os 280 centros com M13 sinalizada e todos os 35 centros Aqua retirados pela partição antiga. Usar apenas o QA estrito, remover centros pelo dono da área ou restringir à interseção altera as contagens e os denominadores de cada sensor. Para testar a transferência do fator, uma amostra futura deve estratificar por geometria, qualidade e turno, registrar pares sem cobertura e separar épocas de ajuste e avaliação. O número de pares e o desenho devem ser definidos antes de uma expansão histórica.
