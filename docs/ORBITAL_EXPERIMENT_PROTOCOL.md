# Protocolo experimental orbital — etapa 5

Versão 1.0, registrada antes da aquisição. Região fixa de Altinópolis–Pitangueiras, caixa W −48,433, S −21,215243, E −47,181633, N −20,8087035. Os pilotos de 24/08/2024 e 26/08/2019 entram como casos históricos da etapa 4, identificados separadamente. A unidade amostral é a dupla orbital. A amostra é intencionalmente estratificada e não representa probabilisticamente a série.

## Hipóteses e desfechos

1. Contar centros nativos sem usar a propriedade da área pode alterar a contagem, especialmente onde footprints de varreduras se sobrepõem, preservando a união de área por QA. Registrar diferenças entre contagem legada e independente, dimensões, centros rejeitados e resíduos de área.
2. Admitir M13 sinalizada pode alterar a presença relatada e o suporte. Medir o efeito em suporte próprio e no mesmo suporte fixo. Os dois contrastes são descritivos, sem pressupor aumento de acurácia.
3. A transferência do fator FIRMS ao domínio orbital depende de QA, turno e geometria. Comparar o fator mensal congelado às razões Aqua/VIIRS de centros sob o mesmo suporte, deixando denominador zero como indefinido. Avaliar a disponibilidade de duplas informativas antes de qualquer ajuste.
4. A diferença entre as regras de fusão depende de zeros observados e centros exclusivos. Comparar as regras no mesmo suporte e decompor seleção de células, recorte espacial, QA e regra. O fator é fixo dentro de cada par. O contraste não identifica o viés causal da série.

## Amostragem e exclusões

Selecionar até uma dupla em cada janela abaixo. Consultas ao CMR limitam-se a metadados da caixa. Usar somente FIRMS Standard Processing local, somando registros de Aqua e S-NPP na caixa por data UTC e turno. Baixa atividade corresponde a contagem no máximo igual à mediana do turno por estação em 2019–2024. Alta atividade exige contagem positiva e pelo menos o percentil empírico 75 dessa distribuição. Os demais dias levam a classe intermediária. A estação seca operacional é maio–setembro e a chuvosa outubro–abril. Os rótulos são estratos de amostragem e não uma classificação meteorológica diária.

| Janela UTC inclusiva | Turno | Estação | Atividade visada | Separação nominal visada |
| --- | --- | --- | --- | --- |
| 10–25/02/2020 | Dia | Chuvosa | Baixa | Até 15 min |
| 10–25/07/2021 | Noite | Seca | Alta | Mais de 15 min |
| 08–23/09/2022 | Dia | Seca | Alta | Até 15 min |
| 10–25/03/2023 | Noite | Chuvosa | Baixa | Mais de 15 min |
| 08–23/05/2024 | Dia | Seca | Baixa | Mais de 15 min |
| 08–23/11/2024 | Noite | Chuvosa | Alta | Até 15 min |

Requerer mesma data UTC, turno de catálogo concordante, caixa contida nos dois polígonos e ângulos zenitais estimados de até 55° em ambos. Requerer os quatro produtos MYD14/MYD03 Collection 6.1 e VNP14IMG/VNP03IMG Collection 2. Recusar separação nominal superior a 45 min. Ordenar pelos critérios de atividade-alvo, intervalo-alvo, menor ângulo máximo estimado, menor intervalo e data. Candidatas até 30 min têm prioridade sobre 31–45 min. Se o estrato visado estiver vazio, registrar o desvio e usar a primeira elegível na mesma janela e turno. Registrar candidatas rejeitadas, datas sem combinação, falhas de aquisição e duplas adquiridas sem suporte utilizável. Uma dupla adquirida ocupa a vaga mesmo se ficar inelegível. Proibir seleção por coincidência de incêndios, Jaccard ou FRP.

A classe geométrica para sumarização usa o maior ângulo zenital medido na caixa entre os dois sensores, separando até 30°, maior que 30° até 55°, e acima de 55°. A seleção por catálogo estima ângulo via linha central do polígono e não garante nuvens, qualidade ou suporte de 80%.

## Suporte e QA

Cenário principal H3 resolução 7, ângulo zenital máximo 55°, pelo menos 80% da célula inteira com suporte terrestre comum e até 60 min entre varreduras, com iluminação concordante e geolocalização nominal. Usar partição de área da etapa 4 e registrar a contagem nativa separadamente. Aplicar em paralelo QA estrito (bits 0–6 nominais no VIIRS) e presença com M13 sinalizada (bits 0–5 nominais). Ambos exigem terra, excluem bow-tie e QA ausente e mantêm os mesmos critérios Aqua. FRP não entra nos desfechos de presença.

Na modalidade A cada QA define o próprio suporte. Na modalidade B ambas as contagens usam exatamente os polígonos de interseção válidos entre as duas políticas, correspondência de tempo/iluminação e o mesmo H3. Quando as partições coincidem e a política estrita é subconjunto da outra, sua interseção deve reproduzir o suporte estrito. Verificar isso nos dados e exigir que o total de células e a área sejam iguais entre as duas linhas fixas. Publicar também tolerâncias de 30, 45 e 90 min e limiares de 60% e 90%. Os cenários de 60°/65° já publicados para 2024 são sensibilidades históricas.

## Métricas e análise estatística

Principalmente cobertura comum em km², quantidade de células elegíveis, Jaccard positivo e diferença pareada das duas regras de fusão. Secundariamente matriz incluindo zeros observados, Dice/F1 simétrico, Kappa, concordância geral, MAE, RMSE, viés, centros brutos, aprovados e retidos, razão Aqua/VIIRS, estimativas e razões de perda. Geometrias e resultados ausentes ficam registrados como tais. Zero é ausência de detecção dentro de observação válida, e Jaccard, Dice ou Kappa indefinidos permanecem nulos.

Publicar média não ponderada por dupla, mediana, mínimo, máximo e número de estimativas definidas. Recalcular métricas separadamente por células agrupadas, usando somas dos denominadores e dos erros. As métricas agrupadas descrevem as células incluídas. Evitar inferência com células tratadas como réplicas e intervalos de confiança com até oito duplas. Relatar por turno, QA, atividade, geometria e fração mínima. Só considerar um ajuste exploratório se houver pelo menos seis duplas informativas com pelo menos 10 centros de cada sensor no suporte fixo e possibilidade de partição independente entre treino e avaliação. Nenhum modelo mensal novo será ajustado.

Verificar FIRMS contra centros brutos no mesmo turno, caixa e janela nominal. Parear espacialmente um a um a 100 m e repetir a 10 e 500 m. Comparar razões apenas onde definidas e identificar denominadores pequenos. Para decompor a fusão, medir em sequência o efeito da elegibilidade e recorte, o efeito de QA no suporte fixo, a mudança do suporte sob M13 e o efeito dos zeros observados no mesmo suporte. Mudança de fator será registrada apenas se um modelo de fato for treinado fora das duplas de avaliação.

## Aceitação e limites

Aceitar a execução se preservar a produção e os artefatos prévios, registrar protocolo e plano amostral antes de baixar, manter o limite de seis novas duplas e 1,5 GiB (1.610.612.736 bytes), verificar assinaturas, metadados e SHA-256, processar sequencialmente com tempo/memória/disco, reproduzir o suporte fixo nos dois QA e conservar áreas com resíduo por célula de até 2 × 10⁻⁵ da área inteira. Resultados nulos, baixa atividade, ausência de melhora, falhas e suporte insuficiente são desfechos válidos. As dimensões do footprint são aproximadas, deslocamentos e a resposta espacial ainda carecem de referência por pixel, FIRMS compartilha os produtos de origem, e as órbitas não são simultâneas. A validação independente de presença e área queimada permanece um ensaio externo com desenho próprio.
