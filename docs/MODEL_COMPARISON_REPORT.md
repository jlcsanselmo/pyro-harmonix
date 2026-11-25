# Comparação de calibração fora do ano de treino

## Desenho

Cada um dos seis anos foi retido uma vez. Os fatores anual e mensais, a regressão pela origem e a robusta de Huber são ajustados exclusivamente nos cinco anos restantes. O modelo bruto é uma referência sem ajuste. A razão mensal desregularizada tem fallback anual quando necessário. O peso de regularização `n/(n+30)` e o corte de Huber `1,345` são fixos. Esta etapa não selecionou parâmetros com o ano de teste. Ajustes futuros usam validação interna com outro ano retido, dentro de cada treino externo.

Comparamos duas populações de registros. Na codetecção, ambos os sensores têm medição no mesmo estrato de turno conhecido. Na união, os estratos exclusivos são incluídos nos totais de registros de cada sensor. O valor do outro sensor permanece nulo. Em cada escala, MAE e WAPE podem ser calculados nas unidades de agregação em que ambos registraram valores. O JSON mostra quantas unidades têm um único sensor, o desvio agregado sobre todos os registrados e as métricas no subconjunto comparável. Um dia com registros de ambos pode reunir células ou turnos diferentes. Esse cotejo de totais não demonstra cobertura conjunta.

A razão mensal da versão de produção é ajustada aos totais da união. As alternativas emparelhadas, entre elas a razão mensal regularizada de MAE 1,319 da primeira etapa, são ajustadas apenas nas codetecções. Os dois ajustes têm coeficientes e populações diferentes. As regressões pela origem usam um coeficiente anual. Para avaliar o efeito do suporte de treino, repetimos OLS e Huber com os totais regionais diários da união nos dias com registro de ambos os sensores. Nenhuma fusão que incorpora Aqua participa como preditor em métricas que usam Aqua como referência.

## Resultados

| Contagem, H3 7 | MAE por estrato com codetecção | WAPE diário na união | WAPE mensal na união | WAPE anual na união | Desvio agregado na união |
| --- | ---: | ---: | ---: | ---: | ---: |
| VIIRS bruto | 4,152 | 308,57% | 411,13% | 413,27% | +413,27% |
| Razão mensal regularizada, codetecção | 1,319 | 75,20% | 79,77% | 76,85% | +76,85% |
| Razão mensal regularizada, união | 1,058 | 52,64% | 21,98% | 15,07% | +1,79% |
| Regressão pela origem, codetecção | 1,085 | 50,89% | 27,20% | 19,15% | +12,79% |
| Huber pela origem, codetecção | 1,096 | 50,85% | 29,93% | 21,77% | +16,28% |
| Regressão pela origem, união diária | 1,020 | 53,23% | 30,05% | 20,38% | +6,08% |
| Huber pela origem, união diária | 1,028 | 54,13% | 30,29% | 22,10% | +7,05% |

A vantagem observada inicialmente da regressão pela origem sobre a razão regularizada **ajustada na codetecção** persiste no MAE por estrato em H3 6, 7 e 8. Nos totais registrados da união, o desvio agregado da regressão em contagem varia de cerca de **+19,1%** em H3 6 a **+75,1%** em H3 8, com **+12,8%** em H3 7. Para a razão regularizada da união esses desvios são de aproximadamente **+1,7%, +1,8% e +1,9%**. Em H3 7, o MAE diurno/noturno é **1,155/0,768** para a regressão, **1,404/0,935** para a razão regularizada de codetecção e **1,121/0,770** para a razão da união. As métricas por célula e turno estão no JSON. A resolução altera o suporte da codetecção.

Na janela de agosto de 2024, ajustada sem 2024 em H3 7, Aqua registrou **459**. VIIRS ajustado somou **443,89** com a razão regularizada da união, **530,62** com a regressão, **550,45** com Huber e **834,13** com a razão regularizada da codetecção. OLS e Huber treinados na união diária estimaram 372,21 e 388,31. O maior total VIIRS continua em 2024 nos oito ajustes e no bruto. Isso mede preservação da ordenação naquela janela, sem transformar Aqua em verdade de campo. A repetição por ano, as somas da janela e os coeficientes mensais constam em `folds` e `pooled` no JSON.

Para FRP em H3 7, OLS reduz MAE do estrato com codetecção de **224,42 MW** bruto para **205,29 MW**, mas eleva WAPE mensal da união de **24,48%** para **43,56%** e apresenta desvio agregado de **−39,5%** na união. Já o VIIRS bruto aparece perto de **−3,1%** no total registrado. A razão regularizada da união, usada em produção, apresentou **−4,67%** de desvio agregado e **30,73%** de WAPE mensal na união. FRP depende de geometria, agregação e algoritmo por sensor. A avaliação pressupõe valores completos dentro do estrato de cada sensor.

## Decisão

Manter a razão mensal regularizada na união como padrão regional descritivo de contagem. A decisão privilegia erro mensal/anual, estabilidade entre resoluções e proximidade do extremo retido. A regressão pela origem e Huber permanecem experimentais para escalas finas e análises com suporte pareado. A fusão de produção continua identificada como índice descritivo. A seleção de um estimador de presença de fogo ou de continuidade entre plataformas requer suporte comprovado por máscaras e validação externa. FRP também deve permanecer exploratória e acompanhada do VIIRS bruto como referência.

[Dados e fatores por fold](data/phase2/fusion-study.json) · [Comandos de reprodução](FUSION_BIAS_ANALYSIS.md#reproduzir) · [Protocolo externo](EXTERNAL_VALIDATION_PROTOCOL.md)
