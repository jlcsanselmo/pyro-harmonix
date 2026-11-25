# Metodologia vigente e experimental

## Série de produção

**Versão congelada** `detection_conditioned_v1` com `monthly_shrunk_union`. As detecções FIRMS Standard Processing são indexadas em H3 8. A unidade de harmonização usa o pai H3 7, dia UTC e turno. A calibração histórica usa a caixa Altinópolis–Pitangueiras e os anos de 2019 a 2024. O fator mensal é uma combinação da razão mensal e anual de totais na união com peso `n/(n+30)`. Há fallback anual e tratamento de fator indefinido. Contagem e FRP são calculadas separadamente.

Se ambos os sensores registram no mesmo estrato conhecido, aplica-se a média de Aqua e VIIRS escalado. Um único sensor contribui pelo seu valor elegível. Um estrato de turno desconhecido prioriza Aqua quando ambos têm registro. Fora da região ou sem fator disponível a série comparável usa Aqua observado. O valor retornado representa índice de atividade registrada. As classes de procedência distinguem o dado observado, ajustado, combinado, extrapolado, histórico ou importado. [Definição científica e fórmulas originais](SCIENTIFIC_METHODOLOGY.md)

## Avaliação temporal

Cada um dos seis anos foi retido, e os fatores foram estimados com os outros cinco. O produto observado Aqua é uma referência entre sensores. A comparação de codetecções e a comparação na união têm domínios distintos. O MAPE da média histórica de Aqua com o estimador VIIRS é um indicador circular e fica arquivado como diagnóstico. [Validação](VALIDATION_REPORT.md) · [Modelos](MODEL_COMPARISON_REPORT.md)

## Fusão condicionada à cobertura

| Elemento | Cenário principal |
| --- | --- |
| Granulados | MYD14/MYD03 C6.1 e VNP14IMG/VNP03IMG C2 autenticados |
| Unidade | H3 7, célula inteira como denominador e parcela na caixa declarada |
| Geometria | Footprints de meios passos, projeção equivalente e centros nativos avaliados separadamente |
| Suporte | Terra válida nos dois sensores, iluminação concordante, zenital ≤55°, área comum ≥80%, diferença ≤60 min |
| Qualidade VIIRS | Estrita com bits 0–6 nominais e presença com M13 sinalizada com bits 0–5 nominais |
| Comparação | Suporte de cada política e interseção fixa entre suportes |
| Zero | Ausência de detecção demonstrada na área observada |
| Unidade amostral | Dupla orbital para resumos não ponderados |

O QA, a união de áreas e os centros deduplicados por índice nativo permitem comparar estimadores e testar sensibilidade. O efeito do filtro angular, a mudança de suporte e a inclusão de zeros são apresentados separadamente. A calibração nova e a validação de FRP ficam fora desta versão. [Protocolo congelado](ORBITAL_EXPERIMENT_PROTOCOL.md) · [Resultados finais](FINAL_SCIENTIFIC_REPORT.md)
