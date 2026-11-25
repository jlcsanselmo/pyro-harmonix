# Histórico de alterações

## 1.0.0 — candidata à revisão

### Da versão original às cinco etapas

| Marco | Evolução |
| --- | --- |
| Protótipo Space Apps | WebGIS com mapa, calendário, consultas e exports FIRMS. Materiais e CSV antigo de Ribeirão Preto preservados. |
| Etapa 1 | Auditoria técnica, rastreabilidade da ingestão, revisão da circularidade e avaliação em anos retidos. |
| Etapa 2 | Decomposição do contraste de 49,2%, comparação de modelos em codetecção e união, proposta de validação externa. |
| Etapa 3 | Primeiro par orbital real, leitura HDF4/NetCDF4 e cobertura válida comum em H3. Ausência de suporte no cenário principal a 55° em 24/08/2024. |
| Etapa 4 | Auditoria dos 35 centros Aqua, separação da contagem e da partição de área, QA VIIRS revisado e segundo par real. |
| Etapa 5 | Cinco novas duplas sob protocolo estratificado, QA comparado em suporte próprio e fixo, avaliação de calibração e escala geométrica. |
| Encerramento | Relatório final, índice, documentação técnica, rascunho de manuscrito e revisão de release. Vinculação de `WEB_BIND_ADDR` efetivada no Compose e ambientes virtuais locais excluídos do Git e do build do backend. |

### Componentes

- **Produção** · WebGIS, ingestão FIRMS, API, persistência, série regional `detection_conditioned_v1` com `monthly_shrunk_union`.
- **Experimental** · Pipeline orbital e fusão condicionada à cobertura. Resultados, inclusive cenários inconclusivos, mantidos em seus caminhos.
- **Trabalhos futuros** · Referência independente de presença, comparação de cantos, transferência NOAA-20/21 e associação com cicatrizes sob desenho próprio.

[Notas da candidata 1.0.0](docs/RELEASE_NOTES_V1.0.0.md) · [Relatório consolidado](docs/FINAL_SCIENTIFIC_REPORT.md)
