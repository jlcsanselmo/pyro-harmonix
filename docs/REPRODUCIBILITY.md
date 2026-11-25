# Reprodução da versão 1.0

As instruções partem da raiz do repositório em PowerShell e usam Docker Compose v2. As rotinas científicas abaixo usam insumos arquivados. Resultados regenerados ficam em `.orbital-data/release-repro`. Para verificar números publicados sem executar ajuste, consulte os artefatos numerados no [índice](SCIENTIFIC_ARTIFACT_INDEX.md) e o [JSON final com localizadores](data/final-scientific-summary.json).

## Software e suíte PostgreSQL

```powershell
docker compose config --quiet
docker compose build api web
docker compose run --rm --no-deps web nginx -v
docker compose run --rm -v "${PWD}/docs:/docs:ro" api sh -c 'set -e; pip install --target /tmp/orbital -r requirements-orbital.txt; export PYTHONPATH=/tmp/orbital; python manage.py test; python manage.py makemigrations --check --dry-run; python -m pip check'
```

As dependências orbitais habilitam a suíte completa de **101 testes** no PostgreSQL. A instalação usa o arquivo opcional e separado do backend de produção. Quando as dependências científicas já estiverem no diretório local `.orbital-data/deps-linux`, é possível montá-lo como somente leitura e usar `PYTHONPATH` apontando para o destino no contêiner. O build do frontend pode ser verificado também com `npm ci` e `npm run build` em `frontend/`.

## Auditoria e comparação histórica

Use os 12 extratos gzip de `docs/data/raw`, a configuração SQLite descartável e os exports somente para leitura. O script reproduz os ajustes de auditoria com partições já definidas, sem atualizar os fatores operacionais.

```powershell
New-Item -ItemType Directory -Path .orbital-data/release-repro -Force | Out-Null
docker compose run --rm --no-deps -e DB_ENGINE=sqlite -e DATABASE_PATH=/tmp/release-audit.sqlite3 -v "${PWD}/docs/data:/archive:ro" -v "${PWD}/.orbital-data/release-repro:/out" api sh -c 'set -e; python manage.py migrate --noinput; python manage.py load_firms_sample --path /archive/raw; python manage.py audit_science --archive-dir /archive --output /out/scientific-audit-full.json; python manage.py study_fusion --output-dir /out/phase2'
```

Use o [relatório de validação](VALIDATION_REPORT.md) para a auditoria, o [relatório de modelos](MODEL_COMPARISON_REPORT.md) para os resultados de anos retidos e a [decomposição da fusão](FUSION_BIAS_ANALYSIS.md) para a caixa bruta no ajuste de toda a amostra. A reprodução arquivada inclui cenários intencionalmente obsoletos como controle histórico.

## Experimentos orbitais com os arquivos disponíveis

Os quatro grânulos de cada dupla precisam estar no mesmo diretório do manifesto verificado. Os caminhos locais do estudo foram `.orbital-data/nasa` para 24/08/2024, `.orbital-data/nasa-phase4-2019-08-26` para 26/08/2019 e `.orbital-data/nasa-phase5/AAAA-MM-DD` para as cinco outras duplas. Se os binários estiverem em outro local, ajuste as montagens. Compare tamanho, assinatura e SHA-256 com o manifesto antes de interpretar resultados. Uma instalação que só contenha o Git consegue verificar tabelas derivadas e precisa desses binários para reproduzir as geometrias.

Exemplo de reprocessamento da fase 3 a 55°. Alterar o limite para 60° e 65° reproduz as sensibilidades publicadas.

```powershell
docker compose run --rm --no-deps -v "${PWD}/docs:/reference:ro" -v "${PWD}/.orbital-data:/work" api sh -c 'set -e; pip install --target /tmp/orbital -r requirements-orbital.txt; export PYTHONPATH=/tmp/orbital; python orbital_pilot.py /work/nasa/granule-manifest.json /reference/data/phase2/fusion-study.json /work/release-repro/phase3-z55 --max-sensor-zenith 55; python plot_orbital_pilot.py /work/release-repro/phase3-z55'
```

Para a fase 4, use `orbital_phase4.py MANIFESTO CALIBRACAO SAIDA --angles 55 60 65` em 2024 e `--angles 55` em 2019. Verifique a correspondência FIRMS com `orbital_calibration_check.py MANIFESTO SAIDA RAW SAIDA --angle ANGULO` e use `plot_orbital_phase4.py SAIDA_2024 SAIDA_2019 FIGURAS`. Os formatos e o domínio estão no [relatório das duas duplas](SECOND_ORBITAL_PILOT_REPORT.md).

Para a fase 5, copie somente o recibo de aquisição congelado para a árvore de saída e execute em série. O roteiro abaixo reprocessa as duas duplas já armazenadas e depois as cinco novas da etapa 5. `orbital_sample_batch.py` lê o recibo, verifica metadados internos e grava o estado de cada dupla.

```powershell
New-Item -ItemType Directory -Path .orbital-data/release-repro/phase5 -Force | Out-Null
Copy-Item docs/data/phase5/acquisition.json .orbital-data/release-repro/phase5/acquisition.json
docker compose run --rm --no-deps -v "${PWD}/docs:/reference:ro" -v "${PWD}/.orbital-data:/work" api sh -c 'set -e; pip install --target /tmp/orbital -r requirements-orbital.txt; export PYTHONPATH=/tmp/orbital; OUT=/work/release-repro/phase5; FACTOR=/reference/data/phase2/fusion-study.json; RAW=/reference/data/raw; PLAN=/reference/data/phase5/sample-plan.json; python orbital_phase5.py /work/nasa-phase4-2019-08-26/granule-manifest.json "$FACTOR" "$RAW" "$OUT/2019-08-26" "$PLAN"; python orbital_phase5.py /work/nasa/granule-manifest.json "$FACTOR" "$RAW" "$OUT/2024-08-24" "$PLAN"; python orbital_sample_batch.py /work/nasa-phase5 "$FACTOR" "$RAW" "$OUT" "$PLAN"; python orbital_sample_summary.py "$OUT"; python orbital_geometry_reference.py "$OUT"'
```

O encadeamento usa as versões e o suporte congelados. Gráficos PNG, tempos, memória e envelopes gzip podem variar por ambiente. Compare SHA-256 dos binários de entrada, métricas numéricas e definições, e preserve as cópias publicadas.
