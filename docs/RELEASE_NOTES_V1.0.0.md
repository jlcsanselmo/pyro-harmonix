# PyroHarmonix v1.0.0 — candidata à revisão humana

## Escopo da versão

O WebGIS local mantém a ingestão FIRMS e a série regional de atividade registrada. Os relatórios distinguem o resultado histórico zero-filled, a série vigente e a análise experimental de órbita, QA e cobertura. A etapa científica se encerra com sete duplas reais, sem alteração de fatores nem dos critérios científicos.

**Produção** inclui a API Django, o mapa/calendário React, a persistência PostgreSQL, o trabalhador FIRMS e a série `detection_conditioned_v1` com `monthly_shrunk_union`. **Experimental** inclui as máscaras orbitais, aproximações geométricas e fusão condicionada à cobertura. **Trabalho futuro** inclui validação independente, avaliação de cantos e estudos de transferência. Esses itens são perspectivas de continuidade.

## Integridade e revisão

- [x] Suíte em PostgreSQL com 101 testes.
- [x] Consistência das migrations e verificação de dependências Python.
- [x] Builds das imagens API e web e build Vite no host com Node 24. Docker reproduziu o frontend com Node 22.
- [x] Compose com publicação padrão em loopback e serviços de dados internos.
- [x] Relatórios, manifests, protocolo e evidência negativa ou inconclusiva preservados.
- [x] Resultados derivados separados dos grânulos locais e credenciais. Conferidos os 12 hashes de extratos FIRMS, 28 SHA-256 e assinaturas de grânulos locais e os links internos.
- [ ] Revisão humana do manuscrito, autoria e termos de licença antes de publicação.
- [ ] Revisão do diff, criação do commit, tag e publicação por responsável autorizado.

O primeiro build direto do frontend esbarrou na restrição de leitura de diretórios do ambiente de verificação. A execução com acesso de leitura adequado e o build Docker passaram sem alterar o frontend. Nesta versão o Compose serve um ambiente local. A exposição pública requer infraestrutura e controles próprios de autenticação, servidor e segredos. O repositório está sem licença explícita para distribuição de código.

## Git sugerido

Commit `chore(release): consolidate PyroHarmonix v1.0.0 scientific baseline` e tag anotada `v1.0.0` após a revisão do conjunto de mudanças. A base da revisão é `7dbc9dd`. A árvore contém alterações das etapas anteriores, os artefatos adicionados ao longo do trabalho e a consolidação desta candidata. O diff completo precisa integrar a revisão do commit. Os passos de commit, tag, push e publicação ficam reservados à decisão do responsável.

[Changelog](../CHANGELOG.md) · [Relatório científico](FINAL_SCIENTIFIC_REPORT.md) · [Manuscrito para revisão](paper/MANUSCRIPT_DRAFT.md)
