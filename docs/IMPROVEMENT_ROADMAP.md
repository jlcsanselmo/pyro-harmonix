# Roteiro de melhorias

| Prioridade | Estado | Trabalho e dependência |
| --- | --- | --- |
| P0 | Entregue | Retirar preenchimento por zero do caminho padrão, distinguir ausência de registros e zero registrado, reproduzir circularidade e manter validação VIIRS fora do ano. |
| P0 | Entregue | Decomposição do viés por sensor, turno, dia e H3, comparação leave-one-year-out ampliada e piloto de validação local de evidência de cobertura. |
| P0 | Pendente | Parear máscaras MYD14 e VNP14IMG e geolocalização das passagens. Definir cobertura mínima, regra temporal, pixels válidos e tratamento de nuvens. Requer acesso Earthdata e dados de nível 2. |
| P0 | Pendente | Validar fusão com referência externa e desenhar estudo em outras regiões. Para associação com área queimada, tratar área queimada como desfecho distinto e alinhar geometria e datas. |
| P1 | Entregue | Idempotência, recibo e arquivo bruto por SHA-256, controle de janela e resolução, bootstrap diário e em blocos, análise do evento com 2024 retido. |
| P1 | Entregue | Limitar download e checkpoint ao intervalo SP oficial e sinalizar solicitações parciais. |
| P1 | Pendente | Registrar dias faltantes dentro da janela publicada e reavaliar lacunas e reprocessamentos. Integrar a listagem de lacunas e as máscaras de cobertura. |
| P1 | Pendente | Comparar transferências por região, bioma e turno e calibrar NOAA-20/21 individualmente. Ajustar o parâmetro de regularização só dentro dos dados de treino e ampliar o número de anos antes da seleção de modelo. |
| P2 | Entregue | Serializar alterações em registros derivados no PostgreSQL e limitar publicação Compose a loopback por padrão e atualizar Django 5.2 LTS. |
| P2 | Pendente | Garantir uma reivindicação exclusiva por job se forem usados múltiplos workers, introduzir auth/cotas para publicação, registrar versões de fatores por rebuild, medir memória da ingestão e tempo de consultas em volumes reais. |
| P2 | Pendente | Testar com PostgreSQL de tamanho representativo. Decidir índices/partições, cache do painel de calibração e PostGIS a partir de planos e carga concorrente medidos. |
| P3 | Entregue | Expor procedência, extrapolação e cobertura desconhecida e corrigir a contagem de marcadores. |
| P3 | Pendente | Testar leitores de tela, latência de mapa e UX em navegadores e dispositivos reais além do ensaio de DOM em Chrome headless. Adicionar visualização dos estados de cobertura quando as máscaras estiverem disponíveis. |

[Viés da fusão](FUSION_BIAS_ANALYSIS.md) · [Piloto de cobertura](OBSERVATION_COVERAGE_STUDY.md) · [Comparação de modelos](MODEL_COMPARISON_REPORT.md) · [Protocolo externo](EXTERNAL_VALIDATION_PROTOCOL.md)

A etapa 3 processou os quatro grânulos reais de 24/08/2024. A continuidade depende de pares com geometria adequada, verificação do efeito do QA e autorização para ampliar a amostra. [Cobertura orbital](REAL_OBSERVATION_COVERAGE_REPORT.md) · [Fusão condicionada](COVERAGE_AWARE_FUSION_REPORT.md)
