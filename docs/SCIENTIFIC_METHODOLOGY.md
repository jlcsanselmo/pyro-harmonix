# Metodologia científica

## Dados, observações e estratos

A coleção local usa `MODIS_SP` (filtrado a `satellite=Aqua` para a série) e `VIIRS_SNPP_SP` (`satellite=N`). MODIS SP também contém Terra e o ETL preserva esses registros. As datas iniciais nominais no código são 01/11/2000 para MODIS SP, 04/07/2002 para Aqua e 20/01/2012 para VIIRS S-NPP. A janela efetivamente publicada pode diferir de uma janela operacional e conter interrupções. O produto SP é processado para arquivo científico com atraso em relação a NRT. O pipeline não mistura SP e NRT. Confiança é metadado bruto. MODIS usa uma escala diferente das classes VIIRS. A amostra não estabelece limiares equivalentes, portanto não se aplica corte comum de confiança. FRP é armazenada em MW e pode ser nula. [Área NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/area/) · [Disponibilidade por produto](https://firms.modaps.eosdis.nasa.gov/api/data_availability/) · [Lacunas publicadas](https://firms.modaps.eosdis.nasa.gov/api/missing_data/)

O estrato agrupa centro da detecção em coordenadas geográficas WGS84 na ordem latitude, longitude, pai H3 res. 7 da célula de ingestão res. 8, dia UTC e classe dia/noite. A classe vem do produto. Um turno vazio permanece desconhecido. Na fusão um grupo sem turno conhecido prioriza Aqua quando ambos os sensores têm registros naquele grupo. Agregações espaciais de resolução mais baixa somam estratos compatíveis. A área média global de H3 res. 7 é cerca de 5,16 km² e a área real varia. O agrupamento espacial aproxima detecções de pixels com tamanhos, horários e geometrias distintos. Resolução 7 foi preservada. [Áreas H3 por resolução](https://h3geo.org/docs/core-library/restable/)

## Ajuste dos fatores

A caixa regional é delimitada por S −21,215243, N −20,8087035, W −48,433 e E −47,181633. O período de avaliação vai de 2019 a 2024. A versão regional ajusta a razão de totais registrados `f_m = ΣM_m / ΣV_m` e a razão conjunta `f_a = ΣM / ΣV`. Aplica `f = w f_m + (1 − w) f_a` com `w = n / (n + 30)`. `n` conta estratos elegíveis do mês, somados entre os anos. Essa é uma regularização empírica. O parâmetro 30 foi mantido como referência fixa e não mede o número de amostras independentes. Denominador mensal zero ou ausência de pares usa a razão anual. Sem denominador anual válido, não há fator estimável.

No ajuste regional `union`, as somas consideram registros de cada sensor dentro do mesmo conjunto de estratos. Um estrato sem registro de um sensor não adiciona valor ao total gravado desse sensor. Logo a razão descreve totais de detecções disponíveis, sujeitos a exposição desigual e seleção. `codetect` condiciona aos dois sensores terem detectado no mesmo estrato de turno conhecido. A correção de FRP usa agregados completos de FRP por sensor participante e exclui pares cujas duas somas sejam zero. A FRP harmonizada fica nula se faltar FRP em uma detecção contribuinte. A razão de somas é sensível aos grandes eventos. A amostra oferece apenas seis anos regionais. Não há transferência demonstrada por área, bioma ou regime de fogo. Fatores regionais aplicados em outras datas são rotulados como extrapolação. Fora da região ou quando o fator está indisponível, a série comparável usa Aqua observado.

## Estados de observação e fusão

| Estado | Evidência e uso |
| --- | --- |
| Detectou | Há valor registrado do sensor para o estrato. |
| Observou sem detecção | Cobertura válida demonstrada por máscara de pixels. O valor observado é zero. |
| Sem observação válida | Máscara ou geometria indicou ausência de observação válida. |
| Indisponível | Janela oficial de disponibilidade exclui o sensor. |
| Desconhecido | Faltam registros e evidência de cobertura. É o estado padrão de um silêncio nos CSVs FIRMS. |

Para medir contribuição conjunta, a produção calcula `(M + fV)/2` quando os dois registraram detecções no mesmo estrato. Com apenas Aqua, usa `M`, e com apenas SNPP elegível, usa `fV`. Sem contribuição medida, a produção não cria o registro. Os estratos são somados por pai e dia. O módulo de observação admite zero sustentado por cobertura válida. Os CSVs pontuais atuais não fornecem a evidência para alimentar esse estado. A regra evita reduzir automaticamente a contribuição isolada, mas ainda seleciona sobre detecções e pode gerar inflação quando os sensores amostram eventos diferentes. Ela é uma composição descritiva exploratória. Comparação ponderada requer máscaras, tempos e geometria de passagem, cobertura válida e estimativa dos pesos com dados independentes.

A cobertura por célula e turno pode ser estimada com máscaras de fogo e cobertura de `MYD14` e `VNP14IMG` de nível 2, geolocalização por pixel e qualidade. Para validação de detecção, parear passagens e usar uma referência externa com horários e footprints compatíveis. Para continuidade, incorporar NOAA-20 e NOAA-21 por produto e avaliar cada transferência com sobreposição e anos retidos. [Guia MODIS C6.1](https://www.earthdata.nasa.gov/s3fs-public/2023-09/MODIS_C6_C6.1_Fire_User_Guide_1.0.pdf) · [Guia VIIRS C2](https://www.earthdata.nasa.gov/s3fs-public/2025-06/VIIRS_C2_AF-375m_User_Guide_1.2.pdf)

## Validação e incerteza

O teste fora do ano ajusta todos os fatores usando apenas os outros anos e compara VIIRS com Aqua, condicionado à codetecção. O relatório histórico usa comparação mensal de totais de detecções e mantém a fusão circular apenas para diagnóstico. Pearson e Spearman medem associação e dependem da escala. MAE, RMSE e MedAE usam a unidade da medida. WAPE usa a soma de referências absolutas no denominador. MAPE ignora alvos iguais a zero e informa a amostra restante. No sMAPE, o par (0,0) contribui com 0 e apenas um zero contribui com 200%. Com denominador zero, a métrica aplicável fica indefinida. R² usa a média observada como referência.

O bootstrap agrega todos os estratos de cada dia ou bloco de até sete dias de calendário, dentro de mês e ano. Mantém os dois sensores no mesmo agrupamento, reamostra blocos ocupados dentro de cada mês e recalcula a razão anual em cada réplica. Usa os tamanhos originais para os pesos de shrinkage. A semente é 2024 para contagem e 2025 para FRP. Intervalos de percentis 2,5 e 97,5% do fator são exploratórios. O intervalo propagado de agosto varia só o fator de agosto e mantém as detecções fixas. Faltam cobertura válida, um modelo espacial e avaliação de previsão para inferir incerteza total ou significância do evento.

## Evidência posterior

A comparação descritiva sobre a caixa de calibração reproduziu um total 49,2% maior que o Aqua observado. A diferença entre regras é atribuível às contribuições exclusivas, com viés frente à atividade real ainda não identificável. Na comparação de anos retidos, o ajuste mensal regularizado na união apresentou menor erro mensal e anual dos totais registrados que a regressão pela origem ajustada nas codetecções, em H3 7. A versão de produção permanece `detection_conditioned_v1` com `monthly_shrunk_union`. [Viés da fusão](FUSION_BIAS_ANALYSIS.md) · [Modelos](MODEL_COMPARISON_REPORT.md) · [Cobertura](OBSERVATION_COVERAGE_STUDY.md)
